#!/usr/bin/env python3

"""
Running this script in a gnome-terminal will produce input to the gnome-terminal
--geometry flag suitable to recreate the geometry of this terminal.

You may copy the output of this script into the terminal_geometry flag for one
of your commands (in a config YAML), assuming in_new_terminal is already True
for this command.
"""

from subprocess import check_output


def main():
    # TODO what (if anything) needs to be installed from stock 16.04/18.04
    # to run this cmd?

    # cmd from Alberto's answer at this post:
    # https://stackoverflow.com/questions/4892866
    cmd = ("xwininfo -id $(xprop -root | awk "
        "'/_NET_ACTIVE_WINDOW\(WINDOW\)/{print $NF}')"
    )
    out = check_output(cmd, shell=True).decode('utf-8')
    lines = [e.strip() for e in out.splitlines()]
    lines = [e for e in lines if e]

    aulx = None
    for e in lines:
        if e.startswith('Absolute upper-left X:'):
            aulx = e.split()[-1]
            break
    assert aulx is not None

    assert lines[-1].startswith('-geometry')
    geomstr = lines[-1].split()[1]

    parts = geomstr.split('+')
    size_part = parts[0]
    # TODO does offset always start w/ +, or can that be a - sign too?
    # +- then maybe? (assuming always NxN+N?N for now, where ? == + or --)
    offset_part = '+'.join(parts[1:])

    assert offset_part[0].isdigit()
    n_parsed_nums = 0
    x_offset_str = ''
    y_offset_str = ''
    separator = ''
    for i in range(len(offset_part)):
        char = offset_part[i]
        if char.isdigit():
            if n_parsed_nums == 0:
                x_offset_str += char
            elif n_parsed_nums == 1:
                y_offset_str += char
            else:
                raise AssertionError('only expected to parse 2 offset nums')
            last_was_digit = True
        else:
            if last_was_digit:
                n_parsed_nums += 1

            assert n_parsed_nums == 1, 'only expected one separator'
            separator += char
            last_was_digit = False

    # again assuming that initial separator
    geom_str_out = f'{size_part}+{aulx}{separator}{y_offset_str}'
    print('Copy the next line to a terminal_geometry flag in a config YAML:')
    print(geom_str_out)

    import ipdb; ipdb.set_trace()


if __name__ == '__main__':
    main()

