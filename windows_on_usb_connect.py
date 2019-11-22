
import ctypes
import os
import sys
import logging
import logging.handlers

import win32serviceutil
import win32service
import win32event
import servicemanager

import win32gui
import win32gui_struct
struct = win32gui_struct.struct
pywintypes = win32gui_struct.pywintypes
import win32con

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
del log_file, os


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

    _svc_name_ = "USBStorageOnConnectEventHandler"
    _svc_display_name_ = "USB Storage Connection Event Handler"
    _svc_description_ = "Handle USB storage device connection events"

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
        if control == win32service.SERVICE_CONTROL_DEVICEEVENT:
          info = win32gui_struct.UnpackDEV_BROADCAST(data)
          
          # This is the key bit here where you'll presumably
          # do something other than log the event. Perhaps pulse
          # a named event or write to a secure pipe etc. etc.
          if event_type == DBT_DEVICEARRIVAL:
            servicemanager.LogMsg(
              servicemanager.EVENTLOG_INFORMATION_TYPE,
              0xF000,
              ("Device %s arrived" % info.name, '')
            )
          elif event_type == DBT_DEVICEREMOVECOMPLETE:
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
    # TODO way to detect (successful) install, to automatically run postinstall
    # stuff, so service actually works (rather than 1053 error)?
    # post-install stuff suggested here:
    # https://stackoverflow.com/questions/13466053
    win32serviceutil.HandleCommandLine(DeviceEventService)
