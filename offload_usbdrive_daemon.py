#!/usr/bin/env python3

"""
Copies data from USB external harddrive when it's connected.
"""

import os

import pyudev


context = pyudev.Context()
monitor = pyudev.Monitor.from_netlink(context)

monitor.filter_by(subsystem='usb')

mount_dir = '/media/tom/smhcr'

for action, device in monitor:
    vendor_id = device.get('ID_VENDOR_ID')
    print('detected {} for device with vendor ID {}'.format(action, vendor_id))
    os.listdir(mount_dir)

