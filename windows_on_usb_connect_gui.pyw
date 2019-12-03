
"""
Communicates with windows_on_usb_connect.py service to display service status
graphically.
"""

import argparse
import getpass
import os
from os.path import split, join, splitext, abspath, normpath, exists
from multiprocessing.connection import Listener
from subprocess import Popen

import util


user = getpass.getuser()
startup_dir = ('C:\\Users\\' + user +
    r'\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup'
)
py_script_path = abspath(normpath(__file__))
startup_bat_path = join(startup_dir,
    splitext(split(py_script_path)[1])[0] + '.bat'
)


def gui_handle_msg(conn, gui, msg):
    if type(msg) is dict:
        key_set = set(msg.keys())
        update_rule_keys = {'rule_text', 'n_rule_items'}
        update_item_keys = {'itemname'}
        err_keys = {'err_str', 'err_src_item', 'formatted_traceback'}
        
        if key_set == update_rule_keys:
            if verbose:
                print('updating rule')

            rule_text = msg['rule_text']
            n_rule_items = msg['n_rule_items']
            gui.set_rule(rule_text, n_rule_items)
            
        elif key_set == update_item_keys:
            if verbose:
                print('updating item')

            itemname = msg['itemname']
            gui.set_item(itemname)
            
        elif key_set == err_keys:
            if verbose:
                print('received error information')

            src_item = msg['err_src_item']
            estr = msg['err_str']
            formatted_traceback = msg['formatted_traceback']
            gui.show_error(src_item, estr, formatted_traceback)

        else:
            raise ValueError(f'dict w/ unrecognized keys: {msg}')
            
    elif msg == 'step_progress':
        if verbose:
            print('stepping progress bar')

        gui.step_progress()
        
    elif msg == 'close_request':
        # may not be necessary...
        conn.send('close_ok')
        gui.all_copies_successful = True
        
    else:
        raise ValueError(f'unrecognized msg: {msg}')
        

def eject_drive(drive_letter):
    # Since there doesn't seem to be a way to do this w/ the pywin32 API.
    # There may be some other API that exposes ejection functions:
    # https://stackoverflow.com/questions/85649
    # ...but I'm not clear on how to call it from Python.
    
    # actually this doesn't seem to work when typed directly into a powershell
    # (at least the GUI option to eject the drive is still there, and it's 
    # still in file explorer under computer)
    # not sure what to try now.
    # (it does work for USB sticks though, which do appear a bit different
    # to some windows calls)
    # https://serverfault.com/questions/130887 (other uses experiencing diff)
    # and it isn't just a matter of not executing it as an administrator
    
    """
    # https://stackoverflow.com/questions/40285581
    powershell_script = f'''
    $Eject = New-Object -comObject Shell.Application;
    $Eject.NameSpace(17).ParseName(“{drive_letter}:”).InvokeVerb(“Eject”)
    '''
    #$Eject.NameSpace(17).ParseName(“F:”).InvokeVerb(“Eject”)
    print(powershell_script)
    
    args = powershell_script.split()
    
    print('before Popen call')
    #Popen(args)
    #Popen(powershell_script, shell=True)
    print('after Popen call')
    """
    """
    # also tried steps under:
    # https://mail.python.org/pipermail/python-win32/2002-November/000593.html
    # replacing his magic number with winioctlcon.IOCTL_STORAGE_EJECT_MEDIA,
    # and replacing the empty str arg to DeviceIoControl with an empty byte
    # string (b'')
    # did not work, either as admin / non-admin
    import win32file
    import winioctlcon
    import win32con as wc
    h = win32file.CreateFile(r'\\.\\' + drive_letter + ':', wc.GENERIC_READ,
        wc.FILE_SHARE_READ, None, wc.OPEN_EXISTING, 0, 0
    )
    print(winioctlcon.IOCTL_STORAGE_EJECT_MEDIA == 2967560)
    print(0x002d4808 == 2967560)
    '''
    r = win32file.DeviceIoControl(h, winioctlcon.IOCTL_STORAGE_EJECT_MEDIA,
        b'', 0
    )
    '''
    # This slightly diff set of args from:
    # https://www.programcreek.com/python/example/62737/win32file.CreateFile
    # example 20
    r = win32file.DeviceIoControl(h, winioctlcon.IOCTL_STORAGE_EJECT_MEDIA,
        b'', 0, None
    )
    win32file.CloseHandle(h)
    """
    
    
def main():
    # TODO maybe move address / port to config file so both can read it
    # (.py even...)
    address = ('localhost', 48673)
    authkey = b'automate2p'
    # TODO something more idiomatic than while True wrapping rest?
    
    # TODO make this loop response to ctrl-c or something for debugging.
    # some typical windows way to close shell apps?
    
    while True:
        print('making listener')
        with Listener(address, authkey=authkey) as listener:
            print('opening connection with listener')
            with listener.accept() as conn:
                print('connection open')
                
                drive_data = conn.recv()
                drive_letter = drive_data['drive_letter']
                drive_label = drive_data['drive_label']
                
                gui = util.ProgressGUI()
                gui.set_drive_label(drive_label)
                gui.set_drive_letter(drive_letter)
                
                # TODO TODO better way? test that this gets exited when 
                # service closes its side of the connection!
                while True:
                    try:
                        msg = conn.recv()
                        print(f'msg: {msg}')
                        gui_handle_msg(conn, gui, msg)
                        
                    # This indicates the connection was closed.
                    except EOFError:
                        break
        
            gui.final_notifications()
            del gui

            # TODO also gui.destroy()? factor into final_notifications?
            # (may come down to when i want popup to close?)
                
            # TODO delete. just for debugging, since i can't seem to ctrl-c
            # this terminal app on windows...
            #break
            #


# TODO do i want python script to run in background? modify stuff so
# it's invoked with pythonw.exe, or whatever the name of the background thing
# was? will that give me trouble making a gui?
def install():
    print('installing service GUI')
    assert exists(startup_dir)
    print(f'writing .bat file to {startup_bat_path}')
    # https://stackoverflow.com/questions/4438020
    with open(startup_bat_path, 'w') as f:
        f.write(r'start "" ' + py_script_path)

    
def remove():
    print('removing service GUI')
    assert exists(startup_dir)
    if not exists(startup_bat_path):
        print(f'startup script not found at {startup_bat_path}. '
            'already removed?'
        )
        return
    
    os.remove(startup_bat_path)


if __name__ == '__main__':
    # TODO assert windows 7 until testing startup + registry stuff on other
    # versions of windows?
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--install', action='store_true',
        help='Installs service GUI to run at startup'
    )
    group.add_argument('--remove', action='store_true',
        help='Uninstalls service GUI'
    )
    args = parser.parse_args()
    if args.install:
        install()
        # TODO maybe first detect if it is running? or maybe just don't do
        # automatically after install?
        #main()
    elif args.remove:
        remove()
    else:
        #eject_drive('F')
        main()
