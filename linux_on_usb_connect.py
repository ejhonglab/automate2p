#!/usr/bin/env python3

import getpass
import os
from os.path import split, join, exists, isdir, expanduser
import glob
from shutil import copy2, copytree
import traceback
import time
from subprocess import Popen, CalledProcessError

import yaml

import util


# systemctl should log this print
print('trying to start logging')
l = util.init_logging(__file__)

evar = 'DRIVE_SYSTEMCTL_UNIT'
try:
    # This should be set in the invokation of the service by systemd
    service_unit = os.environ[evar]
    l.info(f'service_unit: {service_unit}')
except KeyError as e:
    l.error(f'failed to lookup {evar}')
    raise

root = '/'.join([''] + service_unit[:-len('.mount')].split('-'))
l.info(f'mount_point: {root}')
'''
evar = 'DRIVE_MOUNT_POINT'
try:
    # This should be set in the invokation of the service by systemd
    root = os.environ[evar]
    l.info(f'mount_point: {root}')
except KeyError as e:
    l.error(f'failed to lookup {evar}')
    raise
'''
if not isdir(root):
    l.error('this mount point was not a directory!')


def info(msg):
    l.info(f'({service_unit}) ' + str(msg))


def error(msg):
    l.error(f'({service_unit}) ' + str(msg))


def load_config():
    config_file = util.service_unit_config_file(service_unit)
    config_file = join(split(__file__)[0], config_file)

    info(f'loading config at {config_file}')

    with open(config_file, 'r') as f:
        config = yaml.load(f)

    info(f'rules: {config["copy_rules"]}')
    if 'run_if_anything_copied' in config:
        info(f'run_if_anything_copied: {config["run_if_anything_copied"]}')

    return config


def main():
    user = getpass.getuser()
    info(f'script is being run as user={user}')
    if user == 'root':
        raise ValueError('we do not want this script triggered as root')

    config = load_config()

    gui = util.ProgressGUI()
    # not exactly same as label in other case, but this is ok
    gui.set_drive_label(root)

    # TODO somehow factor this loop out to share between this and
    # windows_on_usb_connect.py ?

    current_time_s = time.time()
    for rn, rule in enumerate(config['copy_rules']):
        rule_start_time = time.time()
        
        assert not rule['from'].startswith('/')
        src = join(root, rule['from'])
        dst = rule['to']
        assert dst.startswith('/')
        info(f'starting on rule {rn} ({src} -> {dst})')
        # TODO maybe also show these errors in the gui
        if not isdir(src):
            error(f'rule source {src} was not an existing directory')
            continue
            
        if not isdir(dst):
            error(f'rule destination {dst} was not an existing directory')
            continue
            
        info(f'trying to copy items under {src} to {dst}')
        
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
            #  TODO compare mtimes here to decide whether to copy?
            dst_item = join(dst, split(src_item)[1])
            if not exists(dst_item):
                filtered_glob_items.append(src_item)
            else:
                info(f'{dst_item} already existed at destination')
            del dst_item
        glob_items = filtered_glob_items
        
        if len(glob_items) == 0:
            info(f'no items to copy for rule {rn}!')
            continue
        
        # or just '{src} -> {dst}'?
        rule_text = f'Copying files from {src} to {dst}'
        gui.set_rule(rule_text, len(glob_items))
            
        for src_item in glob_items:
            dst_item = join(dst, split(src_item)[1])
            info(f'{src_item} -> {dst_item}')

            itemname = split(src_item)[1]
            gui.set_item(itemname)
            
            before_copy = time.time()
            try:
                assert not exists(dst_item), f'{dst_item} existed before copy'
                    
                if isdir(src_item):
                    copytree(src_item, dst_item)
                else:
                    # Assuming it was a file here.
                    copy2(src_item, dst_item)
                    
                copy_duration_s = time.time() - before_copy
                info(f'copying {src_item} took {copy_duration_s:.2f}s')
                assert exists(dst_item), f'{dst_item} did not exist after copy'
                    
            # TODO maybe specifically check for IOError (and specific type
            # that indicates insufficient space?), and handle (by pausing?)
            # in that case, otherwise raise?
            except Exception as e:
                formatted_traceback = traceback.format_exc()
                gui.show_error(src_item, str(e), formatted_traceback)
                raise
            
            gui.step_progress()
        
        # TODO compare copy duration to native linux copy
        ruledur_s = time.time() - rule_start_time
        info(f'done processing rule {rn} (took {ruledur_s:.2f}s)')

    # This gets destroyed in some of the next calls, so I'm copying it now
    # for use later.
    something_was_copied = gui.something_was_copied
    
    gui.all_copies_successful = True
    gui.final_notifications()
    # TODO destroy?
    del gui
    
    info('all rules processed')

    if something_was_copied and 'run_if_anything_copied' in config:
        info('something was copied AND had commands to run if anything copied')

        default_cmd_flags = {
            'in_new_terminal': False,
            'ignore_errors': False,
            'shell': False,
            'working_directory': '~',
            # see notes below
            #'terminal_geometry': None
        }
        for cmd_and_flags in config['run_if_anything_copied']:
            cmd = cmd_and_flags['cmd']
            info(f'cmd: {cmd}')

            cmd_flags = dict()
            for k, v in default_cmd_flags.items():
                if k in cmd_and_flags:
                    config_v = cmd_and_flags[k]
                    cmd_flags[k] = config_v
                    info(f'using {k}={config_v} from config')
                else:
                    cmd_flags[k] = v
                    info(f'using default {k}={v}')

            if cmd_flags['in_new_terminal']:
                if not cmd_flags['shell']:
                    info('forcing shell=True because in_new_terminal was True')

                cmd_flags['shell'] = True

            unrecognized_flags = ((set(cmd_flags.keys()) - set('cmd')) -
                set(default_cmd_flags.keys())
            )
            if len(unrecognized_flags) > 0:
                # TODO maybe change loglevel here to something more like warning
                # (or choose to fail here)
                error(f'this cmd had unrecognized flags: {unrecognized_flags}')

            wd = expanduser(cmd_flags['working_directory'])
            if not isdir(wd):
                error(f'working_directory {wd} was not a directory. '
                    'skipping cmd.'
                )
                continue

            if not cmd_flags['in_new_terminal']:
                # This should be equivalent to not passing env.
                env = None
                assert cmd_flags['terminal_geometry'] is None, (
                    'terminal_geometry argument is not defined unless '
                    'in_new_terminal is True'
                )
            else:
                # TODO get this to work? seems i may need more of a proper
                # environment for this to work...
                # it almost seems to work when the cmd is run from a terminal
                # , but the offset is still not exactly right

                #geom_str = cmd_flags['terminal_geometry']
                geom_str = None
                if geom_str is None:
                    cmd_prefix = 'gnome-terminal'
                else:
                    cmd_prefix = f'gnome-terminal --geometry={geom_str}'

                # The 'bash' at the end is necessary to keep the terminal open
                # (with a bash prompt), after the command finishes.
                cmd = f"{cmd_prefix} -x bash -i -c 'cd {wd}; {cmd}; bash'"
                info(f'modified cmd to start original in new terminal: {cmd}')

                env = os.environ.copy()
                # Setting either this or XDG_SEAT_PATH seemed to make GUI
                # behavior of opened terminal more reliable.
                # TODO is 'seat0' always gonna be valid, or do we need to look
                # this up somehow? i couldn't quickly figure out how XDG_*
                # variables are normally set (running same procedure in shell on
                # startup would seem to make sense, unless there is other state
                # changing how that startup is run) (i tried the -l (login
                # shell) option to bash, which seemed like it might source all
                # the right stuff from the man pages, but not sure...)
                # (i originally got this value by pickling the env in a normal
                # terminal, and then loading that env here)
                env['XDG_SEAT'] = 'seat0'

                # TODO note if terminal seems to be unresponsive/slow in future.
                # seemed to happen once. not sure if it's gonna be a repeat
                # problem (was one symptom of the inconsistent failure observed
                # w/o setting some of the XDG variables)

                # one weird thing is that running same cmd,
                # w/ env=<env saved here> from src/misc/popen_terminal.py
                # seems to work! so it seems other factors must be at play,
                # or something env is not fully determining the env...

            try:
                # TODO any cases where first arg shouldn't just be cmd.split()?
                # thought i saw some SO post where someone had a space in one
                # of the list elements...
                if not cmd_flags['shell']:
                    cmd = cmd.split()

                proc = Popen(cmd, shell=cmd_flags['shell'], cwd=wd, env=env)

                retcode = proc.wait()
                # TODO also test retcode before declaring success? assert 0?
                info(f'last cmd seemed successful (retcode={retcode})')

            except CalledProcessError as e:
                error(f'error in the last cmd: {e}')
                if cmd_flags['ignore_errors']:
                    continue
                raise

    elif not something_was_copied and 'run_if_anything_copied' in config:
        info('had commands to run if anything copied BUT nothing was copied')

    else:
        info('NO commands to run if anything copied')



if __name__ == '__main__':
    main()

