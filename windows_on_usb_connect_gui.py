
"""
Communicates with windows_on_usb_connect.py service to display service status
graphically.
"""

import argparse
import getpass
import os
from os.path import split, join, splitext, abspath, normpath, exists
from multiprocessing.connection import Listener
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from subprocess import Popen


user = getpass.getuser()
startup_dir = ('C:\\Users\\' + user +
    r'\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup'
)
py_script_path = abspath(normpath(__file__))
startup_bat_path = join(startup_dir,
    splitext(split(py_script_path)[1])[0] + '.bat'
)


def init_gui():
    tk_root = tk.Tk()

    w = tk_root.winfo_screenwidth()
    h = tk_root.winfo_screenheight()
    ww = w // 4
    wh = h // 15
    x = w // 2 - ww // 2
    y = h // 2 - wh // 2
    tk_root.geometry('{}x{}+{}+{}'.format(ww, wh, x, y))

    # TODO maybe try to share this str w/ windows service description 
    # defined in windows_on_usb_connect (get over IPC? or shared config?)
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
    
    gui_elements = {
        'tk_root': tk_root,
        'rule_var': rule_var,
        'rule_label': rule_label,
        'itemname_var': itemname_var,
        'itemname_label': itemname_label,
        'progress_var': progress_var,
        'progress': progress
    }
    return gui_elements
   

progress_step = None
all_copies_successfull = False
def gui_handle_msg(conn, gui_elements, msg):
    global progress_step
    global all_copies_successfull
    
    tk_root = gui_elements['tk_root']
    rule_var = gui_elements['rule_var']
    rule_label = gui_elements['rule_label']
    itemname_var = gui_elements['itemname_var']
    itemname_label = gui_elements['itemname_label']
    progress_var = gui_elements['progress_var']
    progress = gui_elements['progress']
    
    if type(msg) is dict:
        key_set = set(msg.keys())
        update_rule_keys = {'rule_text', 'progress_step'}
        update_item_keys = {'itemname'}
        err_keys = {'err_str', 'err_src_item', 'formatted_traceback'}
        
        if key_set == update_rule_keys:
            print('updating rule')
            rule_text = msg['rule_text']
            progress_step = msg['progress_step']
            rule_var.set(rule_text)
            progress_var.set(0.0)
            rule_label.update()
            progress.update()
            tk_root.update()
            
        elif key_set == update_item_keys:
            print('updating item')
            itemname = msg['itemname']
            itemname_var.set(itemname)
            itemname_label.update()
            # tk_root update? just do once at end, regardless?
            
        elif key_set == err_keys:
            print('received error information')
            src_item = msg['err_src_item']
            estr = msg['err_str']
            formatted_traceback = msg['formatted_traceback']
            # TODO test this (shows up / looks reasonable / doesnt
            # block other things / closes appropriately / etc)
            # see this for way to maybe make this message more
            # friendly to the avg user:
            # https://stackoverflow.com/questions/49072942
            messagebox.showerror(
                # TODO maybe get title prefix from service desc
                title='USB Copy Utility Error',
                message=f'Error while copying {src_item}: {estr}.',
                detail=formatted_traceback
            )
            tk_root.update()
            # TODO want to quit original progressbar window here?
            # wait for messagebox to be closed, then do that?
            # (may not be able to just raise then...)
            
        else:
            raise ValueError(f'dict w/ unrecognized keys: {msg}')
            
    elif msg == 'step_progress':
        print('stepping progress bar')
        assert progress_step is not None
        progress.step(progress_step)
        progress.update()
        tk_root.update()
        
    elif msg == 'close_request':
        # may not be necessary...
        conn.send('close_ok')
        all_copies_successfull = True
        
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
    global progress_step
    global all_copies_successfull
    
    print('main')
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
                
                gui_elements = init_gui()
                
                all_copies_successfull = False
                
                # TODO TODO better way? test that this gets exited when 
                # service closes its side of the connection!
                while True:
                    try:
                        msg = conn.recv()
                        print(f'msg: {msg}')
                        gui_handle_msg(conn, gui_elements, msg)
                        
                    # This indicates the connection was closed.
                    except EOFError:
                        break
        
            tk_root = gui_elements['tk_root']
            # TODO does this close error? and do i want it to?
            tk_root.destroy()
            del tk_root
            del gui_elements
            progress_step = None
            
            if all_copies_successfull:
                print('all copies were successfull')
                tk_root = tk.Tk()
                tk_root.withdraw()
                
                messagebox.showinfo('USB Copy Done',
                    'All files copied successfully.\nPlease eject the drive '
                    f'{drive_letter[:-1]} ({drive_label})'
                )
                # since i haven't yet been able to figure out how to
                # programmatically eject the drive...
                '''
                msgbox = messagebox.askquestion('Eject',
                    'All files copied successfully.\nEject '
                    f'{drive_letter[0]} ({drive_label})?'
                )
                if msgbox == 'yes':
                    # TODO TODO TODO eject the drive
                    print('trying to eject the drive')
                '''
                    
                tk_root.destroy()   
            else:
                print('all copies were NOT successfull')
                
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
    # https://stackoverflow.com/questions/4438020
    with open(startup_bat_path, 'w') as f:
        # TODO need diff escaping in path put in bat file?
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
