
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
'''
from multiprocessing.connection import Connection, answer_challenge, \
    deliver_challenge
import socket
import struct
'''
from multiprocessing.connection import Client

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

import util

GUID_DEVINTERFACE_USB_DEVICE = "{A5DCBF10-6530-11D2-901F-00C04FB951ED}"
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004

# TODO TODO test that this refactoring has not broken the logging
l = util.init_logging(__file__)
#

'''
# Uncomment for interactive debugging of logged functions that do not involve
# Windows service calls, without actually writing to log file.
# Comment before actually installing / starting the service.
l.info = print
l.error = print
'''

authkey = b'automate2p'
'''
# https://stackoverflow.com/questions/57817955
def ClientWithTimeout(address, timeout):
    with socket.socket(socket.AF_INET) as s:
        s.setblocking(True)
        s.connect(address)

        # We'd like to call s.settimeout(timeout) here, but that won't work.

        # Instead, prepare a C "struct timeval" to specify timeout. Note that
        # these field sizes may differ by platform.
        seconds = int(timeout)
        microseconds = int((timeout - seconds) * 1e6)
        timeval = struct.pack("@LL", seconds, microseconds)

        # And then set the SO_RCVTIMEO (receive timeout) option with this.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, timeval)

        # Now create the connection as normal.
        c = Connection(s.detach())
        
    # The following code will now fail if a socket timeout occurs.
    answer_challenge(c, authkey)
    deliver_challenge(c, authkey)

    return c
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


def client_conn(address, ret_dict):
    # is_alive check not working as i expected...
    l.info('inside client_conn, before attempt to open client connection')
    conn = Client(address, authkey=authkey)
    l.info(f'conn (inside client_conn): {conn}')
    ret_dict['conn'] = conn
    
    
def client_conn_timeout(address, timeout_s):
    # Adapted from:
    # https://stackoverflow.com/questions/47712093
    ret_dict = {
        'conn': None
    }
    thread = threading.Thread(target=client_conn, args=(address, ret_dict),
        daemon=True
    )
    l.info('starting thread to get client connection')
    thread.start()
    l.info('before join on client connection thread')
    thread.join(timeout_s)
    # From docs: "if the thread is still alive, the join() call timed out"
    # TODO why is this not working as expected? (at least I can just check
    # if it's None...)
    if thread.is_alive():
        l.info('is_alive indicated a timeout')
    else:
        l.info('is_alive indicated NO timeout')
    
    conn = ret_dict['conn']
    l.info(f'conn: {conn}')
    return conn


def copy_all_by_rules():
    use_gui = True
    l.info(f'entering copy_all_by_rules (use_gui={use_gui})')
    
    ignore_drive_letters, copy_rules, max_age_s = load_config()
    
    drive_labels2roots = \
        get_drive_labels2roots(ignore_drive_letters, copy_rules)
            
    current_time_s = time.time()
    
    address = ('localhost', 48673)
    
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
        
        # TODO TODO just check whether service is available at that address rather
        # than having some hardcoded flag... how?
        # + at least ensure correct timeout settings, so can still work w/o gui
        if use_gui:
            l.info(f'trying to open connection with GUI process at {address}')
            
            # TODO make sure this doesn't block if nothing is listening
            # on this address. want to just proceed w/o gui in that case.
            # (this does block, and the API doesn't seem to accept a something 
            # like a timeout...)
            # workaround? https://stackoverflow.com/questions/47712093 ?
            #conn = Client(address)
            # TODO fixable? doesn't seem to be working...
            # (log still only has line above as last line)
            #conn = ClientWithTimeout(address, 3)
            
            conn = client_conn_timeout(address, 3.0)
            if conn is None:
                l.error('could not open client connection within timeout. '
                    'disabling interaction with GUI for this drive connection.'
                )
                # TODO or just return (logging fact that we are)?
                use_gui = False
            else:
                # TODO may need to check it's not None or something
                l.info('opened connection with GUI process')
                
                # So that this drive can be ejected at the end, if everything is
                # successfull.
                conn.send({
                    'drive_letter': root,
                    'drive_label': label
                })
            
        for rn, rule in enumerate(rules):
            rule_start_time = time.time()
            
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
                
                # Not counting the fact that the items may take different
                # amounts of time to copy.
                progress_step = 100 / len(glob_items)
                
                conn.send({
                    'rule_text': rule_text,
                    'progress_step': progress_step
                })
                
            for src_item in glob_items:
                dst_item = join(dst, split(src_item)[1])
                l.info(f'{src_item} -> {dst_item}')

                if use_gui:
                    itemname = split(src_item)[1]
                    conn.send({'itemname': itemname})
                    
                before_copy = time.time()
                try:
                    assert not exists(dst_item), \
                        f'{dst_item} existed before copy'
                        
                    if isdir(src_item):
                        copytree(src_item, dst_item)
                    else:
                        # Assuming it was a file here.
                        copy2(src_item, dst_item)
                        
                    copy_duration_s = time.time() - before_copy
                    l.info(f'copying {src_item} took {copy_duration_s:.2f}s')
                    assert exists(dst_item), \
                        f'{dst_item} did not exist after copy'
                        
                # TODO maybe specifically check for IOError (and specific type
                # that indicates insufficient space?), and handle (by pausing?)
                # in that case, otherwise raise?
                except Exception as e:
                    formatted_traceback = traceback.format_exc()
                    if use_gui:
                        conn.send({
                            'err_str': str(e),
                            'err_src_item': src_item,
                            'formatted_traceback': formatted_traceback
                        })
                        # TODO should i also wait for reply from gui process
                        # before raising the error, to ensure this message
                        # and any preceding are handled?
                        # (or does not needed to here mean i don't need to
                        # below?)
                        
                    # TODO delete if err logging is otherwise working
                    l.error(f'error while copying {src_item}: {e}\n' +
                        formatted_traceback
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
                    #time.sleep(0.3)
                    #
                    conn.send('step_progress')
            
            # TODO compare copy duration to native windows GUI copy
            ruledur_s = time.time() - rule_start_time
            l.info(f'done processing rule {rn} (took {ruledur_s:.2f}s)')
    
    if use_gui:
        l.info('sending close_request to GUI process')
        conn.send('close_request')
        msg = conn.recv()
        l.info(f'got reply to close request: {msg}')
        assert msg == 'close_ok'
        
        l.info('closing connection with GUI process')
        conn.close()
        l.info('closed connection with GUI process')
    
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
                # (worker.is_alive() returns False) after target function
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
    # TODO automatically install (wrap w/ GUI installer?)
    # TODO + automatically set GUI use options if i want that
    # (it seems passing --interactive to install should handle this, but
    # doing this in powershell just yields a usage error... not sure how to
    # modify syntax, if possible. if fixable, should also allow changing user.)
    # TODO + change user it's installed under (?) to maybe have GUI behave
    # better?
    # TODO make service start on boot (+ restart on err if necessary)
    win32serviceutil.HandleCommandLine(DeviceEventService)
