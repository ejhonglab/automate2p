# -*- coding: utf-8 -*-

from os.path import join, splitext
from datetime import datetime
import logging
import logging.handlers
import sys
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox


data_root = r'D:\mb_team'
todays_dir = join(data_root, datetime.today().strftime('%Y-%m-%d'))


# TODO this all work just the same as if invoked from top-level scope?
# any weird state of logging stuff that would make that not the case?
def init_logging(_file):
    """
    _file should be the __file__ of the caller of init_logging
    """
    # https://stackoverflow.com/questions/51194784
    log_file = splitext(_file)[0] + ".log"
    l = logging.getLogger()
    l.setLevel(logging.INFO)
    f = logging.Formatter('%(asctime)s %(process)d:%(thread)d %(name)s '
        '%(levelname)-8s %(message)s'
    )
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
        logging.error("Unhandled exception occured",
            exc_info=(type,value,traceback)
        )
        #Don't need another copy of traceback on stderr
        if old_excepthook!=sys.__excepthook__:
            old_excepthook(type,value,traceback)

    old_excepthook = sys.excepthook
    sys.excepthook = excepthook
    del log_file

    return l


def service_unit_without_suffix(service_unit):
    suffix = '.mount'
    if service_unit.endswith(suffix):
        return service_unit[:-len(suffix)]
    else:
        return service_unit


def service_unit_config_file(service_unit):
    without_suffix = service_unit_without_suffix(service_unit)
    # The left str is what spaces in drive label get translated to in systemd,
    # but the right is something I'd prefer for filenames.
    config_prefix = without_suffix.replace(r'\x20', '_').replace(' ', '_')
    return f'{config_prefix}_config.yaml'


class ProgressGUI:
    def _init_state_vars(self):
        self.n_rule_items = None
        self.something_was_copied = False
        # TODO this make sense to have here? have show_error mark it false, and
        # start it true (or does that not track meaning of it in windows gui
        # daemon somehow?)
        self.all_copies_successful = False
        #

        self.drive_label = None
        # Should only be set in Windows case.
        self.drive_letter = None


    def __init__(self):
        self._init_state_vars()

        self.tk_root = tk.Tk()

        w = self.tk_root.winfo_screenwidth()
        h = self.tk_root.winfo_screenheight()
        ww = w // 4
        wh = h // 15
        x = w // 2 - ww // 2
        y = h // 2 - wh // 2
        self.tk_root.geometry('{}x{}+{}+{}'.format(ww, wh, x, y))

        # TODO maybe try to share this str w/ windows service description 
        # defined in windows_on_usb_connect (get over IPC? or shared config?)
        self.tk_root.title('USB file copy utility')
        # https://stackoverflow.com/questions/1892339
        self.tk_root.attributes('-topmost', True)

        self.rule_var = tk.StringVar()
        # TODO why does justify='left' seem to be ignored?
        self.rule_label = ttk.Label(self.tk_root, textvariable=self.rule_var,
            justify='left'
        )
        self.rule_label.pack()

        self.itemname_var = tk.StringVar()
        self.itemname_label = ttk.Label(self.tk_root,
            textvariable=self.itemname_var
        )
        self.itemname_label.pack()
        
        # TODO say which files are being copied (would need more granularity
        # than seems possible using copytree, in item=directory case)
        
        self.progress_var = tk.DoubleVar()
        self.progress = ttk.Progressbar(self.tk_root,
            variable=self.progress_var, maximum=100
        )
        self.progress.pack(expand=1, fill='both')
        self.tk_root.update()


    # TODO rename to mount point to support both linux and windows cases
    def set_drive_letter(self, drive_letter):
        self.drive_letter = drive_letter
        

    def set_drive_label(self, drive_label):
        self.drive_label = drive_label
        

    def set_rule(self, rule_text, n_rule_items):
        self.n_rule_items = n_rule_items

        self.rule_var.set(rule_text)
        self.progress_var.set(0.0)
        self.rule_label.update()
        self.progress.update()
        self.tk_root.update()


    def set_item(self, itemname):
        self.itemname_var.set(itemname)
        self.itemname_label.update()
        # tk_root update?

        self.something_was_copied = True


    def step_progress(self):
        assert self.n_rule_items is not None

        # TODO move hardcoded 100 to some var shared w/ other thing that made
        # 100 the right value here...

        # Not counting the fact that the items may take different
        # amounts of time to copy.
        progress_step = 100 / self.n_rule_items
        self.progress.step(progress_step)
        self.progress.update()
        self.tk_root.update()


    def final_notifications(self, verbose=False):
        self.tk_root.destroy()
        self.tk_root = None

        if self.something_was_copied:
            if self.all_copies_successful:
                if verbose:
                    print('all copies were successful')

                self.tk_root = tk.Tk()
                self.tk_root.withdraw()
                
                eject_msg = (
                    'All files copied successfuly.\n'
                    'Please eject the drive '
                )
                assert self.drive_label is not None
                # Linux case.
                if self.drive_letter is None:
                    # TODO maybe also get mount point here or something?
                    # rename drive_letter to that effect and delete this
                    # conditional?
                    eject_msg += f'{self.drive_label}'

                # Windows case.
                else:
                    assert self.drive_letter is not None
                    eject_msg += f'{self.drive_letter[0]} ({self.drive_label})'

                messagebox.showinfo('USB Copy Done', eject_msg)

                # TODO maybe take a callback arg or return something so this
                # can still be possible, if i do figure out programmatic eject?

                # since i haven't yet been able to figure out how to
                # programmatically eject the drive...
                '''
                msgbox = messagebox.askquestion('Eject',
                    'All files copied successfuly.\nEject '
                    f'{drive_letter[0]} ({drive_label})?'
                )
                if msgbox == 'yes':
                    # TODO TODO TODO eject the drive
                    if verbose:
                        print('trying to eject the drive')
                '''
                    
                # TODO want this? messagebox block until closed?
                #self.tk_root.destroy()   
            else:
                if verbose:
                    print('all copies were NOT successful')
        else:
            if verbose:
                print('nothing was copied')

        self._init_state_vars()


    def show_error(self, src_item, estr, formatted_traceback):
        # see this for way to maybe make this message more
        # friendly to the avg user:
        # https://stackoverflow.com/questions/49072942
        messagebox.showerror(
            # TODO maybe get title prefix from service desc
            title='USB Copy Utility Error',
            message=f'Error while copying {src_item}: {estr}.',
            detail=formatted_traceback
        )
        self.tk_root.update()
        # TODO want to quit original progressbar window here?
        # wait for messagebox to be closed, then do that?
        # (may not be able to just raise then...)

        self._init_state_vars()
        

    def destroy(self):
        self.tk_root.destroy()
        self.tk_root = None
        self._init_state_vars()

