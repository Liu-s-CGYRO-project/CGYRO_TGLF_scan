"""Prepare candidates removing the custom timing.debug output from CGYRO.

No installed source, binary, checkpoint or result is changed. Both candidate
paths must be new. Compile and validate in the solver's build environment.
"""
import argparse
from pathlib import Path
import re


DEBUG_NAMES = re.compile(r'\b(?:write_timers_debug|runfile_timers_debug)\b|out\.cgyro\.timing\.debug', re.I)


def without_debug_writer(source):
    """Remove the two recognized calls and their standalone output routine."""
    text = source.decode('utf-8')
    if not DEBUG_NAMES.search(text):
        return source
    routine = re.compile(r'^subroutine write_timers_debug\(datafile,mode\)\r?\n.*?'
                         r'^end subroutine write_timers_debug[^\S\r\n]*(?:\r?\n|$)', re.M | re.S)
    call = re.compile(r'^[ \t]*call write_timers_debug\(trim\(path\)//runfile_timers_debug,io_control\)[ \t]*\r?\n', re.M)
    if len(routine.findall(text)) != 1 or len(call.findall(text)) != 2:
        raise ValueError('Unrecognized diagnostic timer implementation; no change made')
    result = call.sub('', routine.sub('', text))
    if DEBUG_NAMES.search(result):
        raise ValueError('Unexpected remaining diagnostic reference; no change made')
    return result.encode('utf-8')


def without_debug_name(source):
    """Drop only the custom diagnostic filename declaration."""
    text = source.decode('utf-8')
    if not DEBUG_NAMES.search(text):
        return source
    line = re.compile(r"^[ \t]*character\(len=22\) :: runfile_timers_debug = 'out\.cgyro\.timing\.debug'[ \t]*\r?\n", re.M)
    result, count = line.subn('', text)
    if count != 1 or DEBUG_NAMES.search(result):
        raise ValueError('Unrecognized diagnostic filename declaration; no change made')
    return result.encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('timedata_source', type=Path)
    parser.add_argument('timedata_candidate', type=Path)
    parser.add_argument('globals_source', type=Path)
    parser.add_argument('globals_candidate', type=Path)
    args = parser.parse_args()
    candidates = [(args.timedata_candidate, without_debug_writer(args.timedata_source.read_bytes())),
                  (args.globals_candidate, without_debug_name(args.globals_source.read_bytes()))]
    if candidates[0][0].resolve() == candidates[1][0].resolve() or any(p.exists() for p, _ in candidates):
        raise ValueError('Candidate paths must be distinct new files; no change made')
    for path, data in candidates:
        with path.open('xb') as output:
            output.write(data)
        print('Prepared candidate: ' + str(path))


if __name__ == '__main__':
    main()
