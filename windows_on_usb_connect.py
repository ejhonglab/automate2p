
import ctypes
import os
from os.path import join, split, exists, isdir, getmtime
import sys
import logging
import logging.handlers
import glob
import time
from shutil import copytree, copy2
import tkinter as tk
from tkinter import ttk

import win32serviceutil
import win32service
import win32event
import servicemanager
import win32gui
import win32gui_struct
struct = win32gui_struct.struct
pywintypes = win32gui_struct.pywintypes
import win32con
import yaml
import pytimeparse
import win32api

GUID_DEVINTERFACE_USB_DEVICE = "{A5DCBF10-6530-11D2-901F-00C04FB951ED}"
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004

# https://stackoverflow.com/questions/51194784
log_file = os.path.splitext(__file__)[0] + ".log"
l = logging.getLogger()
l.setLevel(logging.INFO)
f = logging.Formatter(
    '%(asctime)s %(process)d:%(thread)d %(name)s %(levelname)-8s %(message)s'
)
# TODO why this handler in addition to rotating file thing below?
h = logging.StreamHandler(sys.stdout)
h.setLevel(logging.NOTSET)
h.setFormatter(f)
l.addHandler(h)
h = logging.handlers.RotatingFileHandler(log_file, maxBytes=1024**2,
    backupCount=1
)
h.setLevel(logging.NOTSET)
h.setFormatter(f)
l.addHandler(h)
del h, f
# Hook to log unhandled exceptions
def excepthook(type,value,traceback):
    logging.error("Unhandled exception occured",exc_info=(type,value,traceback))
    #Don't need another copy of traceback on stderr
    if old_excepthook!=sys.__excepthook__:
        old_excepthook(type,value,traceback)
old_excepthook = sys.excepthook
sys.excepthook = excepthook
del log_file


'''
# Uncomment for interactive debugging of logged functions that do not involve
# Windows service calls, without actually writing to log file.
# Comment before actually installing / starting the service.
l.info = print
l.error = print
'''


def load_config():
    config_file = join(split(__file__)[0], 'config.yaml')
    with open(config_file, 'r') as f:
        data = yaml.load(f)
        
    ignore_drive_letters = [c + ':\\' for c in data['ignore_drive_letters']]
    copy_rules = {e['label']: e['rules'] for e in data['copy_rules']}
    max_age_s = pytimeparse.parse(data['ignore_files_older_than'])
    if max_age_s is None:
        raise ValueError('could not parse ignore_files_older_than value')
    l.info(f'max age for copy: {max_age_s} seconds')
    
    return ignore_drive_letters, copy_rules, max_age_s


def copy_all_by_rules():
    ignore_drive_letters, copy_rules, max_age_s = load_config()
    
    all_drives = [d for d in win32api.GetLogicalDriveStrings().split('\x00')
        if d
    ]
    
    # TODO ideally, we would only check the connected drive for a matching 
    # label, but not sure how to find the volume from the information in the
    # device name string (has vendor/product IDs, some identifier I have not
    # yet figured out, and the same class GUID hardcoded above)
    
    drive_labels2roots = dict()
    for d in all_drives:
        l.info(f'checking label of drive at {d}')
        if d in ignore_drive_letters:
            l.info('skipping this drive because in ignore')
            continue
        
        try:
            # TODO will i ever get the drive not ready / other error for the
            # drives i actually care about? need to implement some retry logic
            # or some other checks?
            
            # GetVolumeInformation returns:
            # label, "serial number", max length of file name, bitmask of flags
            # , file system name (e.g. NTFS)
            label = win32api.GetVolumeInformation(d)[0]
            
        except win32api.error as e:
            # TODO why does this print to ipython console multiple (6) times
            # when debugging this function alone in ipython console
            # (not running this function as part of a service)?
            l.error(f'error when trying to GetVolumeInformation for drive {d}'
                f' {e}'
            )
            continue
        
        if label in copy_rules:
            drive_labels2roots[label] = d
            l.info(f'found label "{label}" (in config) mounted at {d}')
            
    current_time_s = time.time()
    
    # Trying to adapt progress bar stuff from here:
    # https://stackoverflow.com/questions/17777050
    
    # TODO ok to have this not at top level scope? if so, how am i supposed
    # to do this?
    tk_root = tk.Tk()
    # https://stackoverflow.com/questions/1892339
    tk_root.attributes('-topmost', True)
    
    # TODO add a label for the window
    # TODO say which drive is being copied to
    # TODO say which files are being copied
    
    # TODO maybe re-init this for each rule? (or probably just zero it somehow?)
    # https://stackoverflow.com/questions/41896879
    progress_var = tk.DoubleVar()
    progress = ttk.Progressbar(tk_root, variable=progress_var, maximum=100)
    progress.pack()
    tk_root.update()
    # TODO TODO TODO some way to mix gui into this code, or absolutely NEED
    # to have a callback that the GUI calls (w/ this after thing)?
    # see https://gordonlesti.com/use-tkinter-without-mainloop/ ?
    #progress.after(1, main_callback)
    
    # TODO compare copy time to native windows GUI copy
    # TODO and maybe use multiprocessing or something to speed up copy
    # TODO TODO ideally, have some GUI progressbar popup when copy is started
    # (may need to change service settings?)
    for label, rules in copy_rules.items():
        if label not in drive_labels2roots:
            continue
        
        root = drive_labels2roots[label]
        for rule in rules:
            src = rule['from']
            # TODO if i get gui progress working, maybe also show these errors
            if not isdir(src):
                l.error(f'rule source {src} was not an existing directory')
                continue
                
            dst = join(root, rule['to'])
            if not isdir(dst):
                l.error(f'rule destination {dst} was not an existing directory'
                )
                continue
                
            l.info(f'trying to copy items under {src} to {dst}, '
                f'for drive {label}'
            )
            
            if 'glob' in rule:
                globstr = rule['glob']
            else:
                globstr = '*'
                
            # TODO some nice call to recursively update (skip existing files,
            # or those w/ equally recent (m?)time?)
            
            # For now, only recursively copying over top-level items that do
            # not already exist at the destination.
            
            glob_items = glob.glob(join(src, globstr))
            
            progress_var.set(0.0)
            progress.update()
            tk_root.update()
            
            # TODO TODO this work when using progress_var? need to use set,
            # incrementing progress_var manually now? 
            # Not counting the fact that the items may take different amounts
            # of time to copy.
            progress_step = 100 / len(glob_items)
                
            for src_item in glob_items:
                src_item_age_s = current_time_s - getmtime(src_item)
                if src_item_age_s > max_age_s:
                    # TODO TODO filter these out in an earlier step so
                    # progress bar is more meaningful
                    l.info(f'skipping {src_item} because it was too old '
                        f'({src_item_age_s:.0f} > {max_age_s:.0f} seconds)'
                    )
                    progress.step(progress_step)
                    progress.update()
                    continue

                #  TODO compare mtimes here to decide whether to copy?
                dst_item = join(dst, split(src_item)[1])
                if not exists(dst_item):
                    l.info(f'{src_item} -> {dst_item}')
                    # TODO TODO TODO handle case where one of these calls
                    # would / does exceed the remaining space on the drive!!!!
                    # (does the service stop if there is an error?)
                    if isdir(src_item):
                        #copytree(src_item, dst_item)
                        pass
                    else:
                        # Assuming it was a file here.
                        #copy2(src_item, dst_item)
                        pass
                else:
                    l.info(f'{dst_item} already existed at destination')
                    
                # TODO delete. for testing progressbar.
                time.sleep(0.5)
                #
                    
                progress.step(progress_step)
                progress.update()
                
                tk_root.update()
                
    # TODO how to make the window close? are my problems unique to
    # interactively testing the code in anaconda for some reason?
    # maybe it will just work when using this as a service (assuming
    # I can get windows to show up at all...)?
    tk_root.quit()
    tk_root.update()
    del tk_root


# Cut-down clone of UnpackDEV_BROADCAST from win32gui_struct, to be
# used for monkey-patching said module with correct handling
# of the "name" param of DBT_DEVTYPE_DEVICEINTERFACE
def _UnpackDEV_BROADCAST(lparam):
    if lparam == 0: return None
    hdr_format = "iii"
    hdr_size = struct.calcsize(hdr_format)
    hdr_buf = win32gui.PyGetMemory(lparam, hdr_size)
    size, devtype, reserved = struct.unpack("iii", hdr_buf)
    # Due to x64 alignment issues, we need to use the full format string over
    # the entire buffer.  ie, on x64:
    # calcsize('iiiP') != calcsize('iii')+calcsize('P')
    buf = win32gui.PyGetMemory(lparam, size)

    extra = {}
    if devtype == win32con.DBT_DEVTYP_DEVICEINTERFACE:
        fmt = hdr_format + "16s"
        _, _, _, guid_bytes = struct.unpack (fmt, buf[:struct.calcsize(fmt)])
        extra['classguid'] = pywintypes.IID (guid_bytes, True)
        extra['name'] = ctypes.wstring_at (lparam + struct.calcsize(fmt))
    else:
        raise NotImplementedError("unknown device type %d" % (devtype,))
        
    return win32gui_struct.DEV_BROADCAST_INFO(devtype, **extra)

win32gui_struct.UnpackDEV_BROADCAST = _UnpackDEV_BROADCAST


class DeviceEventService(win32serviceutil.ServiceFramework):

    _svc_name_ = "CopyOnUSBConnectHandler"
    _svc_display_name_ = "Copy On USB Connect Utility"
    _svc_description_ = "Follows rules to copy files to USB devices on connect"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
    
        # Specify that we're interested in device interface
        # events for USB devices
        filter = win32gui_struct.PackDEV_BROADCAST_DEVICEINTERFACE(
            GUID_DEVINTERFACE_USB_DEVICE
        )
        self.hDevNotify = win32gui.RegisterDeviceNotification(
            self.ssh, # copy of the service status handle
            filter,
            win32con.DEVICE_NOTIFY_SERVICE_HANDLE
        )

  
    # Add to the list of controls already handled by the underlying
    # ServiceFramework class. We're only interested in device events
    def GetAcceptedControls(self):
        rc = win32serviceutil.ServiceFramework.GetAcceptedControls(self)
        rc |= win32service.SERVICE_CONTROL_DEVICEEVENT
        return rc

  
    # Handle non-standard service events (including our device broadcasts)
    # by logging to the Application event log
    def SvcOtherEx(self, control, event_type, data):
        # TODO delete. for dev.
        def log_dev_info():
            l.info('device name: ' + str(info.name))
            l.info('device classguid: ' + str(info.classguid))
            l.info('device devicetype: ' + str(info.devicetype))
        #
        if control == win32service.SERVICE_CONTROL_DEVICEEVENT:
            info = win32gui_struct.UnpackDEV_BROADCAST(data)
          
            # This is the key bit here where you'll presumably
            # do something other than log the event. Perhaps pulse
            # a named event or write to a secure pipe etc. etc.
            if event_type == DBT_DEVICEARRIVAL:
                l.info(f'device {info.name} connected')
                # TODO delete
                log_dev_info()
                #
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    0xF000,
                    ("Device %s arrived" % info.name, '')
                )
            elif event_type == DBT_DEVICEREMOVECOMPLETE:
                l.info(f'device {info.name} removed')
                # TODO delete
                log_dev_info()
                #
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    0xF000,
                    ("Device %s removed" % info.name, '')
                )

  
    # Standard stuff for stopping and running service; nothing
    # specific to device notifications
    def SvcStop(self):
        l.info('stopping service')
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)


    def SvcDoRun(self):
        l.info('starting service')
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
        servicemanager.LogMsg(
          servicemanager.EVENTLOG_INFORMATION_TYPE,
          servicemanager.PYS_SERVICE_STOPPED,
          (self._svc_name_, '')
        )


if __name__=='__main__':
    #copy_all_by_rules()
    #'''
    # TODO way to detect (successful) install, to automatically run postinstall
    # stuff, so service actually works (rather than 1053 error)?
    # post-install stuff suggested here:
    # https://stackoverflow.com/questions/13466053
    win32serviceutil.HandleCommandLine(DeviceEventService)
    #'''
