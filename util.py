# -*- coding: utf-8 -*-

from os.path import join, splitext
from datetime import datetime
import logging
import logging.handlers
import sys


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

