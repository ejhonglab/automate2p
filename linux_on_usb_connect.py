#!/usr/bin/env python3

"""
"""

import os
from os.path import split, join
import yaml

import util


l = util.init_logging(__file__)

def load_config():
    try:
        # This should be set in the invokation of the service by systemd
        service_unit = os.environ['DRIVE_SYSTEMCTL_UNIT']
        l.info(f'service_unit: {service_unit}')
    except KeyError as e:
        l.info('failed to lookup DRIVE_SYSTEMCTL_UNIT')
        raise

    config_file = util.service_unit_config_file(service_unit)
    config_file = join(split(__file__)[0], config_file)
    l.info(f'({service_unit}) loading config at {config_file}')
    with open(config_file, 'r') as f:
        data = yaml.load(f)

    copy_rules = data['copy_rules']
    l.info(f'({service_unit}) rules: {copy_rules}')

    return copy_rules


def main():
    rules = load_config()

    # TODO delete.
    '''
    sleep_s = 15.0
    l.info(f'sleeping for {sleep_s:.1f} seconds')
    import time
    time.sleep(sleep_s)
    l.info('exiting')
    '''
    #


if __name__ == '__main__':
    main()

