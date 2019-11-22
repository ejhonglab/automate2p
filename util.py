# -*- coding: utf-8 -*-

from os.path import join
from datetime import datetime

data_root = r'D:\mb_team'
todays_dir = join(data_root, datetime.today().strftime('%Y-%m-%d'))
