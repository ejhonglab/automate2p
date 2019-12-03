#!/usr/bin/env python3

# DO NOT CALL THIS SCRIPT DIRECTLY!!! Call setup_linux_service.sh instead.

# This script and service template adapted from sumid's answer here:
# https://askubuntu.com/questions/25071

import getpass
import argparse
import os
from os.path import join, splitext, exists, islink, isfile, abspath
from subprocess import Popen, check_output, CalledProcessError
import time
import warnings
import traceback
from shutil import copyfile

import util


def get_drive_systemctl_unit():
    n_constant_lines_at_end = 7
    def get_systemctl_unit_lines():
        sc_unit_lines = check_output('systemctl list-units -t mount'.split())

        return [b' '.join(line.split()) for line in
            sc_unit_lines.splitlines()[
            :-n_constant_lines_at_end]
        ]

    input('If the drive of interest is connected, disconnect it now. '
        'Press any key afterward.'
    )
    time.sleep(0.5)
    lines_without_drive = get_systemctl_unit_lines()

    input('Now connect the drive, and press any key afterward.')
    max_retry_time_s = 10.0
    sleep_time_s = 3.0

    drive_line = None
    while True:
        lines_with_drive = get_systemctl_unit_lines()

        if len(lines_with_drive) == len(lines_without_drive):
            time.sleep(sleep_time_s)
            continue

        drive_line_set = set(lines_with_drive) - set(lines_without_drive)
        assert len(drive_line_set) == 1
        drive_line = drive_line_set.pop()
        break

    if drive_line is None:
        raise ValueError('no new drive found before timeout')

    drive_systemctl_unit = drive_line.split()[0]

    return drive_systemctl_unit.decode('utf-8')


def systemctl_call(action):
    if action == 'stop':
        print('stopping service')
    elif not action.endswith('e'):
        print(f'{action}ing service')
    else:
        print(f'{action[:-1]}ing service')

    return check_output(f'systemctl {action} {service_name}'.split())


def install(python_path=None):
    abspath_script_to_trigger = abspath('linux_on_usb_connect.py')
    assert exists(abspath_script_to_trigger), \
        f'script to trigger did not exist at {abspath_script_to_trigger}'

    assert exists(example_config), f'no example config at {example_config}'
    if exists(service_config_file):
        # In case we double install, don't want to overwrite some config
        # that may have already been edited.
        print(f'leaving existing config file at {service_config_file}')
    else:
        print(f'copying example config to {service_config_file}')
        copyfile(example_config, service_config_file)

    with open(service_templ_path, 'r') as f:
        # didn't seem to do the trick (couldn't find .mount things to
        # start service)
        '''
        service = f.read().replace('{drive_systemctl_unit}',
            drive_systemctl_unit.replace('\\', '\\\\')
            ).replace('{abspath_script_to_trigger}', 
            abspath_script_to_trigger
        )
        '''
        service = f.read().replace('{drive_systemctl_unit}',
            drive_systemctl_unit).replace('{abspath_script_to_trigger}', 
            abspath_script_to_trigger
        )

    # From testing, escaping this but not Requires/After seemed
    # to work (i.e. actually get triggered when drive is connected).
    service = service.replace('{escaped_drive_systemctl_unit}',
        drive_systemctl_unit.replace('\\', '\\\\')
    )

    if python_path is None:
        print('not using explicit python interpreter')
        # Note that this also includes the following space.
        service = service.replace('{abspath_python} ', '')
    else:
        print(f'using python interpreter at {python_path} to run triggered '
            'script'
        )
        assert exists(python_path), f'python at {python_path} did not exist'
        service = service.replace('{abspath_python}', python_path)

    if exists(service_path):
        warnings.warn(f'overwriting service already installed at '
            '{service_path}'
        )

    with open(service_path, 'w') as f:
        print(f'writing service file to {service_path}')
        f.write(service)

    # Just doing things in this order as per SO link mentioned at top
    # of this file. start call may not be necessary.
    systemctl_call('start')
    systemctl_call('enable')
    

def remove():
    if islink(service_path):
        raise IOError(f'{service_path} already existed as a symlink, which '
            'means this script did not install it.')

    # Calling stop / disable / etc first in case they want service file
    # to still be in place.
    try:
        systemctl_call('stop')
        service_stop_successful = True
    except CalledProcessError as e:
        service_stop_successful = False
        traceback_str = traceback.format_exc()
        # Not exiting yet, because if we installed some service files that
        # were invalid, and thus could not be installed, we still want to 
        # delete those.

    try:
        systemctl_call('disable')
        disable_success = True
    except CalledProcessError as e:
        disable_success = False
        print('\nDisabling service failed with:')
        print(traceback.format_exc())
        print('This may have been because the service was not installed.\n')

    if service_stop_successful or disable_success:
        # Also including these two lines as per:
        # https://superuser.com/questions/513159
        # (nothing similar needed on install, right?)
        print('systemctl daemon-reload')
        Popen(f'systemctl daemon-reload'.split())
        print('systemctl reset-failed')
        Popen(f'systemctl reset-failed'.split())

    if isfile(service_path):
        print(f'removing service installed at {service_path}')
        os.remove(service_path)
    else:
        print(f'no file at {service_path} to uninstall')

    if exists(service_config_file):
        print(f'removing config file at {service_config_file}')
        os.remove(service_config_file)

    if not service_stop_successful:
        print('')
        print(traceback_str)
        # Max # of incorrect sudo password attempts seems to yield
        # exit status 1, for example.
        if traceback_str.endswith('exit status 5.\n'):
            print('Service did not seem to be installed.')


if __name__ == '__main__':
    if getpass.getuser() != 'root':
        raise ValueError(
            'this script should be run by calling setup_linux_service.sh'
        )

    parser = argparse.ArgumentParser(description='Install/remove copy-on-USB '
        'connect systemctl service.'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--install', action='store_true')
    group.add_argument('--remove', action='store_true')

    # Mostly for testing without having to actually [un/re]plug drive.
    # Note: need to add an extra backslash to any lone backslashes, to
    # prevent bash / other shell from stripping it out.
    parser.add_argument('--service-unit', action='store', help='Use this '
        'systemctl service unit, rather than discovering by connecting '
        'drive.'
    )

    # The .sh wrapper should pass this in.
    parser.add_argument('--python', action='store',
        help='Full path to Python executable to use to start triggered script. '
        'DO NOT PASS (used internally by wrapper .sh script).'
    )
    args = parser.parse_args()

    # These are global variables used in the functions above.

    # If this is gonna be used to name service too, will also need on uninstall.
    if args.service_unit is None:
        drive_systemctl_unit = get_drive_systemctl_unit()
    else:
        drive_systemctl_unit = args.service_unit
    #
    '''
    print(type(drive_systemctl_unit))
    print(len(drive_systemctl_unit))
    print(drive_systemctl_unit)
    import sys; sys.exit()
    '''
    #

    '''
    if '\\x20' in drive_systemctl_unit:
        raise NotImplementedError('not dealing with escaping spaces for now. '
            'relabel the drive to something without any spaces.'
        )
    '''

    example_config = 'example_linux_config.yaml'
    service_config_file = util.service_unit_config_file(drive_systemctl_unit)

    service_templ_path = 'usb_copy_on_conn.service.templ'
    without_suffix = util.service_unit_without_suffix(drive_systemctl_unit)
    service_name = without_suffix + '-' + splitext(service_templ_path)[0]
    # It seems to be convention to use '-' rather than '_' in service names.
    service_name = service_name.replace('_', '-')
    service_path = join('/etc/systemd/system', service_name)

    bs_escaped_service_name = service_name.replace('\\', '\\\\')

    # End global variables.

    print('service_unit:', drive_systemctl_unit.replace('\\', '\\\\'))
    # For manual inspection of service w/ existing CLI tools.
    print('Service name:', bs_escaped_service_name)

    if args.install:
        install(python_path=args.python)
    elif args.remove:
        remove()

