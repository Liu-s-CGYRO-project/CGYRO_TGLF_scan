"""Read-only checkpoint selection shared by native storage and the ZIP tool.

CGYRO v3 stores 25 int32 header words, then complex128 data at offset
1024 * 16 bytes. Time belongs to out.cgyro.tag, not to the binary header.
Validation detects structural damage; it cannot prove numerical correctness.
"""
from builtins import (IndexError, OSError, UnicodeError, ValueError, all, any, dict, float,
                      int, iter, len, list, map, open, set, str, zip)
import array
import hashlib
import math
import os
import re
import struct
import sys
import zipfile

CURRENT = 'bin.cgyro.restart'
OLD = CURRENT + '.old'
MAGIC = 140974129
OFFSET = 1024 * 16
GRID = ('N_THETA', 'N_RADIAL', 'N_SPECIES', 'N_XI', 'N_ENERGY', 'N_TOROIDAL')
_DIRECTORY_CACHE = {}


def _text(name, sizes, opener):
    if name not in sizes or sizes[name] > 16 * 1024 * 1024:
        raise ValueError('Missing or oversized checkpoint metadata: ' + name)
    with opener(name) as handle:
        return handle.read(16 * 1024 * 1024 + 1).decode('ascii')


def _grid(sizes, opener):
    if not sizes.get('input.cgyro', 0):
        raise ValueError('Missing input.cgyro for checkpoint validation')
    values = {}
    for name in ('input.cgyro.gen', 'input.cgyro'):
        if name not in sizes:
            continue
        for line in _text(name, sizes, opener).splitlines():
            line = re.split(r'[!#]', line, maxsplit=1)[0].strip()
            fields = line.split('=', 1) if name == 'input.cgyro' else list(reversed(line.split()))
            if len(fields) != 2 or fields[0].strip() not in GRID + ('VELOCITY_ORDER',):
                continue
            key, value = fields[0].strip(), float(fields[1].strip().replace('D', 'e').replace('d', 'e'))
            if not math.isfinite(value) or value < 1 or value != int(value):
                raise ValueError('Invalid checkpoint grid input: ' + key)
            if key in values and values[key] != int(value):
                raise ValueError('Input and generated checkpoint grids disagree: ' + key)
            values[key] = int(value)
    if any(key not in values for key in GRID):
        raise ValueError('Cannot establish all six checkpoint grid dimensions')
    return values


def _tag(sizes, opener):
    fields = _text('out.cgyro.tag', sizes, opener).split()
    if len(fields) < 2:
        raise ValueError('Invalid out.cgyro.tag')
    count, time = int(fields[0]), float(fields[1].replace('D', 'e').replace('d', 'e'))
    times = [float(line.split()[0].replace('D', 'e').replace('d', 'e'))
             for line in _text('out.cgyro.time', sizes, opener).splitlines() if line.strip()]
    if (count < 1 or count > len(times) or not math.isfinite(time) or time < 0
            or any(not math.isfinite(value) for value in times)
            or any(right <= left for left, right in zip(times, times[1:]))
            or not math.isclose(times[count - 1], time, rel_tol=1e-7, abs_tol=1e-10)):
        raise ValueError('Checkpoint tag does not match the saved time history')
    if len(fields) > 2:
        step = float(fields[2].replace('D', 'e').replace('d', 'e'))
        if not math.isfinite(step) or step <= 0:
            raise ValueError('Invalid checkpoint time step')
    return dict(sample_count=count, time=time, last_time=times[-1])


def _inspect(name, sizes, opener, grid):
    if name not in sizes:
        return dict(status='missing', reason='Checkpoint file is absent')
    report = dict(status='invalid', reason='')
    try:
        with opener(name) as handle:
            header = handle.read(100)
            if len(header) != 100:
                raise ValueError('Truncated checkpoint header')
            endian = '<' if struct.unpack('<i', header[:4])[0] == MAGIC else '>'
            words = struct.unpack(endian + '25i', header)
            if words[0] != MAGIC or words[1] != 3:
                return dict(status='unknown', reason='Unsupported checkpoint format; preserve originals')
            if words[24] != MAGIC or any(value < 1 for value in words[2:8]):
                raise ValueError('Damaged checkpoint header')
            dimensions = dict(zip(GRID, words[2:8]))
            if any(dimensions[key] != grid[key] for key in GRID):
                raise ValueError('Checkpoint grid differs from saved input')
            if words[8] not in (1, 2) or ('VELOCITY_ORDER' in grid and words[8] != grid['VELOCITY_ORDER']):
                raise ValueError('Checkpoint velocity ordering differs from saved input')
            velocity_size = math.prod(words[4:7])
            if words[9] < 1 or words[10] < 1 or words[7] % words[9] or velocity_size % words[10]:
                raise ValueError('Invalid checkpoint MPI block dimensions')
            expected = OFFSET + 16 * math.prod(words[2:8])
            if sizes[name] != expected:
                raise ValueError('Checkpoint length differs from its grid')
            padding = handle.read(OFFSET - 100)
            if len(padding) != OFFSET - 100:
                raise ValueError('Truncated checkpoint data offset')
            digest = hashlib.sha256(header + padding)
            total = OFFSET
            for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b''):
                total += len(chunk)
                digest.update(chunk)
                if len(chunk) % 16:
                    raise ValueError('Truncated complex checkpoint payload')
                numbers = array.array('d')
                numbers.frombytes(chunk)
                if (endian == '<') != (sys.byteorder == 'little'):
                    numbers.byteswap()
                if not all(map(math.isfinite, numbers)):
                    raise ValueError('Checkpoint payload contains NaN or infinity')
            if total != expected:
                raise ValueError('Checkpoint changed while reading')
        report.update(dict(status='valid', sha256=digest.hexdigest(), bytes=total,
                           grid=dimensions, velocity_order=words[8], format=3))
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile) as error:
        report['reason'] = str(error)
    return report


def select_checkpoint(sizes, opener):
    """Return omitted names and a serializable report, without changing files.

    A backup without a matching historical tag is retained under its .old
    name and is never advertised as a ready-to-run current checkpoint.
    Unknown formats and two failed candidates keep both for manual recovery.
    """
    present = set(sizes) & {CURRENT, OLD}
    report = dict(policy=1, selected='', resume_ready=False, candidates={})
    if not present:
        return set(), report
    try:
        grid = _grid(sizes, opener)
    except (OSError, ValueError, UnicodeError) as error:
        report['warning'] = str(error) + '; checkpoints preserved'
        return set(), report
    current = _inspect(CURRENT, sizes, opener, grid)
    report['candidates'][CURRENT] = current
    if current['status'] == 'valid':
        try:
            report['tag'] = _tag(sizes, opener)
        except (OSError, ValueError, UnicodeError, IndexError) as error:
            current.update(dict(status='invalid', reason=str(error)))
        else:
            report.update(dict(selected=CURRENT, resume_ready=True))
            return present - {CURRENT}, report
    old = _inspect(OLD, sizes, opener, grid)
    report['candidates'][OLD] = old
    if current['status'] in ('missing', 'invalid') and old['status'] == 'valid':
        report.update(dict(selected=OLD, warning='Backup retained; its matching historical tag is not available. '
                           'Do not rename it and reuse the current out.cgyro.tag.'))
        return present - {OLD}, report
    report['warning'] = 'No verified current checkpoint; originals preserved for manual recovery'
    return set(), report


def directory_checkpoint(directory):
    # Status tables revisit immutable archived points. Reuse validation only
    # while all checkpoint and metadata file identities/stamps are unchanged.
    sizes, stamps = {}, []
    for name in (CURRENT, OLD, 'input.cgyro', 'input.cgyro.gen', 'out.cgyro.tag', 'out.cgyro.time'):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            stat = os.stat(path)
            sizes[name] = stat.st_size
            stamps.append((name, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev))
    key = (os.path.abspath(directory), tuple(stamps))
    if key not in _DIRECTORY_CACHE:
        result = select_checkpoint(sizes, lambda name: open(os.path.join(directory, name), 'rb'))
        for name, size, modified, created, inode, device in stamps:
            stat = os.stat(os.path.join(directory, name))
            if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev) != (size, modified, created, inode, device):
                raise ValueError('Checkpoint changed during validation: ' + name)
        if len(_DIRECTORY_CACHE) >= 2048:
            _DIRECTORY_CACHE.clear()
        _DIRECTORY_CACHE[key] = result
    return _DIRECTORY_CACHE[key]
