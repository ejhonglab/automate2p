# -*- coding: utf-8 -*-
"""
Automate few startup tasks on two-photon imaging computer.
"""

import os
from os.path import join, split, exists
import subprocess as sp

import psutil

from util import todays_dir


first_fly_dir = join(todays_dir, '1')

# TODO odor_pid directory too? behind flag?

if not exists(first_fly_dir):
    os.makedirs(first_fly_dir)
    print('Making directory {}'.format(first_fly_dir))
    
# TODO insert into google doc / format line if possible    

running_programs = sorted([p.name() for p in psutil.process_iter()])

programs_to_open = [
    r'C:\Program Files (x86)\Spectra-Physics\Spectra-Physics MaiTai 2.x' +
        r'\MaiTai Customer 2.x.exe',

    r'C:\Program Files\Thorlabs\ThorImageLS 4.0\ThorImageLS.exe',
    r'C:\Program Files\Thorlabs\ThorSync 4.0\ThorSync.exe',
    #r'C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.Kinesis.exe',
    
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    
] + [(r'C:\Program Files (x86)\Arduino\arduino.exe',  'javaw.exe')] * 1 #3
# TODO not three separate arduino processes. new windows of one process.
# (interact w/ gui to open other two?)

# TODO script dell windows manager thing to put stuff in the right place?
# TODO also open arduino serial monitor

# (if not using dell...) (maybe store preferences on their placement in 
# profiles / also use those to load appropriate ThorSync XML settings?)

# TODO spyder / matlab

for item in programs_to_open:
    if type(item) is str:
        path = item
        name = None
    else:
        path, name = item
        
    exe_dir, exe = split(path)
    
    if name is None:
        name = exe
    
    # TODO also check correct count for multiple?
    if name in running_programs:
        print(exe, 'is already running')
    else:
        print('starting', exe)
        sp.Popen(path, cwd=exe_dir)

# TODO click through ThorImage equipment connection window (if no red error
# icons?)
# TODO click connect / laser on in maitai?
# TODO click off view thing in kinesis -> check in appropriate state
# (or just save state in kinesis...)
# TODO position everything

# TODO connect to vpn? just have that happen by default on startup?

#print('waiting')
#ti_p.wait()
print('exiting')
