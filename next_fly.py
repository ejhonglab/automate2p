# -*- coding: utf-8 -*-

import os
from os.path import join, split, exists, normpath
import glob

from util import todays_dir


use_last_if_empty = True

max_fly_num = None
for d in glob.glob(join(todays_dir, '*/')):
    rel_fly_dir = split(split(d)[0])[1]
    try:
        fly_num = int(rel_fly_dir)
    except ValueError:
        continue
    
    if max_fly_num is None:
        max_fly_num = fly_num
    else:
        if max_fly_num < fly_num:
            max_fly_num = fly_num
            last_dir = d

assert max_fly_num is not None, 'must have some existing fly dirs to call this'

last_empty = len(os.listdir(last_dir)) == 0

if not use_last_if_empty or not last_empty:
    next_fly_dir = join(todays_dir, str(max_fly_num + 1))
    if not exists(next_fly_dir):
        #os.makedirs(next_fly_dir)
        print('Making directory {}'.format(next_fly_dir))
else:
    print('Using empty fly directory {}'.format(normpath(last_dir)))
    next_fly_dir = last_dir
    
    
# TODO TODO use gui automation to input correct path in both thor programs
    
# TODO and make sure remote connection stuff is correct
    
# TODO stimulus generation stuff?

# TODO actuallly starting the experiment? (would need arduino code editing +
# upload or changing current cut-paste approach and communicating)

