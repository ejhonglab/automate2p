#!/usr/bin/env bash

# Since the Python3 that root finds by default may not be as new as the
# Python I use as my non-root user, and setup_linux_service.py uses some
# features only available in newer Python 3 (f-strings).

# https://stackoverflow.com/questions/18215973
if [ ${EUID:-$(id -u)} -eq 0 ]
then
    echo "You must not run this script as root."
    exit 1
fi

NONROOT_PYTHON=`which python3`
# re: the last expression I'm using to expand all arguments,
# https://stackoverflow.com/questions/3811345
sudo ${NONROOT_PYTHON} setup_linux_service.py --user ${USER} \
  --python ${NONROOT_PYTHON} "$@"

