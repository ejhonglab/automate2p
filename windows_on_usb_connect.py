
import ctypes
import os
from os.path import join, split, exists, isdir, getmtime
import sys
import logging
import logging.handlers
import glob
import time
from shutil import copytree, copy2
import traceback
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

import win32serviceutil
import win32service
import win32event
import servicemanager
import win32gui
import win32gui_struct
struct = win32gui_struct.struct
pywintypes = win32gui_struct.pywintypes
import win32con
import win32api
import yaml
import pytimeparse

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
    l.info(f'loading config at {config_file}')
    with open(config_file, 'r') as f:
        data = yaml.load(f)
        
    ignore_drive_letters = [c + ':\\' for c in data['ignore_drive_letters']]
    copy_rules = {e['label']: e['rules'] for e in data['copy_rules']}
    max_age_s = pytimeparse.parse(data['ignore_files_older_than'])
    if max_age_s is None:
        raise ValueError('could not parse ignore_files_older_than value')
    l.info(f'max age for copy: {max_age_s} seconds')
    
    return ignore_drive_letters, copy_rules, max_age_s


def get_drive_labels2roots(ignore_drive_letters, copy_rules):
    all_drives = [d for d in win32api.GetLogicalDriveStrings().split('\x00')
        if d
    ]
    
    # TODO ideally, we would only check the connected drive for a matching 
    # label, but not sure how to find the volume from the information in the
    # device name string (has vendor/product IDs, some identifier I have not
    # yet figured out, and the same class GUID hardcoded above)
    
    l.info(f'all drives whose labels will be checked: {all_drives}')
    
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
            
    if len(drive_labels2roots) == 0:
        l.error('no drives found with labels matching those in rules: ' +
            str(list(copy_rules.keys()))
        )

    return drive_labels2roots


def copy_all_by_rules(use_gui=False):
    l.info(f'entering copy_all_by_rules (use_gui={use_gui})')
    
    ignore_drive_letters, copy_rules, max_age_s = load_config()
    
    drive_labels2roots = \
        get_drive_labels2roots(ignore_drive_letters, copy_rules)
        
    # TODO TODO TODO it seems that if service is left running, one second
    # drive connect, the drive label will still be found, but then nothing
    # else seems to happen. fix! gui related?
    # it does seem the issue was GUI related, because w/ use_gui=False,
    # there does not seem to be the same problem. not sure how to fix the issue
    # though...
            
    current_time_s = time.time()
    
    # TODO TODO TODO how to get GUI to just show up normally? impossible w/
    # a service? need some external non-service daemon and IPC?
    # (when i allow service to interact w/ desktop, windows still only show up
    # after a promprt, and then the service windows completely replace the 
    # desktop until the windows close. not what i want at all.)
    
    if use_gui:
        tk_root = tk.Tk()

        w = tk_root.winfo_screenwidth()
        h = tk_root.winfo_screenheight()
        ww = w // 4
        wh = h // 15
        x = w // 2 - ww // 2
        y = h // 2 - wh // 2
        tk_root.geometry('{}x{}+{}+{}'.format(ww, wh, x, y))
    
        # TODO maybe try to share this str w/ windows service description above
        tk_root.title('USB file copy utility')
        # https://stackoverflow.com/questions/1892339
        tk_root.attributes('-topmost', True)
    
        rule_var = tk.StringVar()
        # TODO why does justify='left' seem to be ignored?
        rule_label = ttk.Label(tk_root, textvariable=rule_var, justify='left')
        rule_label.pack()
    
        itemname_var = tk.StringVar()
        itemname_label = ttk.Label(tk_root, textvariable=itemname_var)
        itemname_label.pack()
        
        # TODO say which files are being copied (would need more granularity
        # than seems possible using copytree, in item=directory case)
        
        progress_var = tk.DoubleVar()
        progress = ttk.Progressbar(tk_root, variable=progress_var, maximum=100)
        progress.pack(expand=1, fill='both')
        tk_root.update()
    
    # TODO compare copy duration to native windows GUI copy
    # TODO and maybe use multiprocessing or something to speed up copy
    # TODO check if need to change service settings to get gui to display
    # from a windows service
    for label, rules in copy_rules.items():
        if label not in drive_labels2roots:
            continue
        
        l.info(f'processing rules for drive with label "{label}"')
        # TODO maybe format these bettter
        l.info(f'rules: {rules}')
        
        root = drive_labels2roots[label]
        for rn, rule in enumerate(rules):
            src = rule['from']
            dst = rule['to']
            l.info(f'starting on rule {rn} ({src} -> {dst})')
            # TODO maybe also show these errors in the gui
            if not isdir(src):
                l.error(f'rule source {src} was not an existing directory')
                continue
                
            dst = join(root, dst)
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

            # Filtering these out first so progress bar is more meaningful.
            filtered_glob_items = []
            for src_item in glob_items:
                src_item_age_s = current_time_s - getmtime(src_item)
                if max_age_s > 0 and src_item_age_s > max_age_s:
                    l.info(f'skipping {src_item} because it was too old '
                        f'({src_item_age_s:.0f} > {max_age_s:.0f} seconds)'
                    )
                    continue

                #  TODO compare mtimes here to decide whether to copy?
                dst_item = join(dst, split(src_item)[1])
                if not exists(dst_item):
                    filtered_glob_items.append(src_item)
                else:
                    l.info(f'{dst_item} already existed at destination')
                del dst_item
            glob_items = filtered_glob_items
            
            if len(glob_items) == 0:
                l.info(f'no items to copy for rule {rn}!')
                continue
            
            if use_gui:
                # or just '{src} -> {dst}'?
                rule_text = f'Copying files from {src} to {dst}'
                rule_var.set(rule_text)
                progress_var.set(0.0)
                rule_label.update()
                progress.update()
                tk_root.update()
                
                # Not counting the fact that the items may take different
                # amounts of time to copy.
                progress_step = 100 / len(glob_items)
                
            for src_item in glob_items:
                dst_item = join(dst, split(src_item)[1])
                l.info(f'{src_item} -> {dst_item}')

                if use_gui:
                    itemname_var.set(split(src_item)[1])
                    itemname_label.update()

                try:
                    assert not exists(dst_item), \
                        f'{dst_item} existed before copy'
                        
                    if isdir(src_item):
                        copytree(src_item, dst_item)
                    else:
                        # Assuming it was a file here.
                        copy2(src_item, dst_item)
                        
                    assert exists(dst_item), \
                        f'{dst_item} did not exist after copy'
                        
                # TODO maybe specifically check for IOError (and specific type
                # that indicates insufficient space?), and handle (by pausing?)
                # in that case, otherwise raise?
                except Exception as e:
                    if use_gui:
                        # TODO test this (shows up / looks reasonable / doesnt
                        # block other things / closes appropriately / etc)
                        # see this for way to maybe make this message more
                        # friendly to the avg user:
                        # https://stackoverflow.com/questions/49072942
                        messagebox.showerror(
                            # TODO maybe get title prefix from service desc
                            title='USB Copy Utility Error',
                            message=f'Error while copying {src_item}: {e}.',
                            detail=traceback.format_exc()
                        )
                        tk_root.update()
                    
                        # TODO want to quit original progressbar window here?
                        # wait for messagebox to be closed, then do that?
                        # (may not be able to just raise then...)
                        
                    # TODO delete if err logging is otherwise working
                    l.error(f'error while copying {src_item}: {e}\n' +
                        traceback.format_ext()
                    )
                    #
                    
                    # TODO log traceback appropriately
                    # (just leave logging to unhandled exception logging?
                    # that working?)
                    # TODO first just test what logging of error looks like w/o
                    # explicit handling
                    # (does the service stop if there is an error?)
                    raise
                
                if use_gui:
                    # TODO delete. for testing progressbar.
                    time.sleep(0.5)
                    #
                        
                    progress.step(progress_step)
                    progress.update()
                    
                    tk_root.update()
            
            l.info(f'done processing rule {rn}')
    
    if use_gui:
        # TODO how to make the window close? are my problems unique to
        # interactively testing the code in anaconda for some reason?
        # maybe it will just work when using this as a service (assuming
        # I can get windows to show up at all...)?
        # (they do seem to be, but check as a windows service)
        tk_root.quit()
        tk_root.update()
        del tk_root
    
    # TODO auto eject w/ message if copy completes successfully
    # (or at least prompt that will do so as one option)
    
    l.info('all rules processed')
    
    
    
def copy_after_delay():
    DELAY_FOR_USBDEVICE_MOUNT_S = 3.0
    l.info(f'waiting {DELAY_FOR_USBDEVICE_MOUNT_S:.1f} seconds for'
        ' USB device to be mounted'
    )
    time.sleep(DELAY_FOR_USBDEVICE_MOUNT_S)
    copy_all_by_rules()

    
# TODO TODO what happens if one thing we want to handle is connected while
# copy is in progress for another? service is single threaded, right?


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
            # These three attributes are all that exist under this info object.
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
                # TODO TODO TODO only start this if the thing connected was
                # actually of interest (ideally start on the particular
                # drive that was connected too, if there's some way to lookup
                # volume from other USB device identifiers)
                # TODO at least maybe store list of connected drives at last
                # remove/connect and check if any new ones should be handled?
                
                # TODO TODO this delay seems to be preventing the thing from 
                # gettting mounted. ways around that? register something to
                # happen in another thread after a certain delay?
                
                # From experimenting, it seems daemon worker thread is killed
                # (worker.isAlive() returns False) after target function
                # returns.
                worker = threading.Thread(target=copy_after_delay, daemon=True)
                l.info('starting worker thread to process rules')
                worker.start()
                l.info('worker thread started')
                
            elif event_type == DBT_DEVICEREMOVECOMPLETE:
                l.info(f'device {info.name} removed')
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
