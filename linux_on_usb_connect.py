#!/usr/bin/env python3

import getpass
import os
from os.path import split, join, exists, isdir
import glob
from shutil import copy2, copytree
import traceback
import time

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
        data = yaml.load(f)
    copy_rules = data['copy_rules']

    info(f'rules: {copy_rules}')

    return copy_rules


def main():
    user = getpass.getuser()
    info(f'script is being run as user={user}')
    if user == 'root':
        raise ValueError('we do not want this script triggered as root')

    rules = load_config()

    gui = util.ProgressGUI()
    # not exactly same as label in other case, but this is ok
    gui.set_drive_label(root)

    # TODO somehow factor this loop out to share between this and
    # windows_on_usb_connect.py ?

    current_time_s = time.time()
    for rn, rule in enumerate(rules):
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
    
    gui.all_copies_successful = True
    gui.final_notifications()
    # TODO destroy?
    del gui
    
    info('all rules processed')

    # TODO delete.
    '''
    sleep_s = 15.0
    info(f'sleeping for {sleep_s:.1f} seconds')
    import time
    time.sleep(sleep_s)
    info('exiting')
    '''
    #


if __name__ == '__main__':
    main()

