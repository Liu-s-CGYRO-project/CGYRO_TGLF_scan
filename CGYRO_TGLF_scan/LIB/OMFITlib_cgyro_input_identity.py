"""Small effective-input metadata, read only on collection or selected restart.

CGYRO's generated file expands defaults and uses ``value NAME`` lines. Comparing
its raw bytes would mistake formatting, a new duration or an MPI layout for a
different physical point. Keep the normalized parameters in the existing point
row; ordinary catalog queries never open these files.
"""
from builtins import (FileNotFoundError, KeyError, TypeError, ValueError, all, any, dict, float, int, len, open, str)
import hashlib
import math
import re
from OMFITlib_cgyro_archive import RUN_CONTROL_PARAMETERS, _at, case_scans, point_values, result_file


def read_parameters(path, generated=False):
    """Parse bounded scalar input without invoking the OMFITcgyro array reader."""
    with open(path, 'rb') as handle:
        data = handle.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('Oversized CGYRO input: ' + str(path))
    values = {}
    for line in data.decode('utf-8-sig').splitlines():
        line = re.split(r'[!#]', line, maxsplit=1)[0].strip()
        if not line:
            continue
        fields = line.rsplit(None, 1)[::-1] if generated else line.split('=', 1)
        if len(fields) != 2:
            raise ValueError('Malformed CGYRO input parameter: ' + line)
        name, value = (field.strip() for field in fields)
        if re.fullmatch(r'[A-Z][A-Z0-9_]*', name) is None or name in values:
            raise ValueError('Invalid or duplicate CGYRO input parameter: ' + name)
        # These values also freeze solver defaults into continuation inputs.
        # Fortran integer reads reject "10.0"; preserve the original token type
        # instead of converting every parameter to float or guessing by name.
        value = int(value) if re.fullmatch(r'[+-]?[0-9]+', value) else float(value.replace('D', 'e').replace('d', 'e'))
        if not math.isfinite(value):
            raise ValueError('Non-finite CGYRO input parameter: ' + name)
        values[name] = value
    if not values:
        raise ValueError('Empty CGYRO input: ' + str(path))
    return values, hashlib.sha256(data).hexdigest()


def effective_parameters(result):
    """Prefer generated input; old/unstarted outputs can retain explicit input.

    Missing defaults are not guessed. A malformed present generated file is an
    error, not permission to silently replace it with the less complete input.
    """
    try:
        values, digest = read_parameters(result_file(result, 'input.cgyro.gen'), generated=True)
        source = 'input.cgyro.gen'
    except (FileNotFoundError, KeyError):
        values, digest = read_parameters(result_file(result, 'input.cgyro'))
        source = 'input.cgyro'
    except ValueError as error:
        if str(error) != 'Missing CGYRO result file: input.cgyro.gen':
            raise
        values, digest = read_parameters(result_file(result, 'input.cgyro'))
        source = 'input.cgyro'
    return values, source, digest


def verified_parameters(result, expected_hash=''):
    """Check this owner's explicit/generated inputs before indexing or restart."""
    actual, input_digest = read_parameters(result_file(result, 'input.cgyro'))
    if expected_hash and input_digest != expected_hash:
        raise ValueError('Saved input.cgyro checksum disagrees with the frozen input')
    values, source, digest = effective_parameters(result)
    if source == 'input.cgyro.gen':
        for name, value in actual.items():
            if name not in values or not math.isclose(value, values[name], rel_tol=1e-9, abs_tol=1e-12):
                raise ValueError('Saved input.cgyro.gen disagrees with input.cgyro: ' + name)
    return actual, values, source, digest


def cache_parameters(row, info, result):
    """Attach verified effective parameters to this existing point row only."""
    _, values, source, digest = verified_parameters(result, row.get('input_sha256', ''))
    expected = dict(point_values(info, row))
    expected.update(row.get('effective_time', {}))
    for name, value in expected.items():
        if source == 'input.cgyro' and name not in values:
            continue  # Old files may omit solver defaults; never guess them.
        if name not in values or not math.isclose(float(value), values[name], rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('Saved ' + source + ' disagrees with coordinate: ' + name)
    if source != 'input.cgyro.gen':
        return values
    row['input_parameters'] = {name: value for name, value in values.items() if name not in RUN_CONTROL_PARAMETERS}
    row['input_parameter_source'] = source
    row['input_parameter_sha256'] = digest
    return values


def cache_competing_parameters(case, info, tasks, resolve):
    """Read only old points whose known coordinates could match this submission.

    Backfill small generated inputs off-tree during publication. Full arrays,
    checkpoint hashes and unrelated ky/parameter points are never inspected.
    """
    candidates = [point_values(info, row, include_input=True) for row in tasks.values()
                  if row.get('input_parameters', None) is not None]
    for _, saved, rows in case_scans(case):
        for row in rows.values():
            if row.get('input_parameters', None) is not None:
                continue
            known = point_values(saved, row)
            known = {name: value for name, value in known.items() if name not in RUN_CONTROL_PARAMETERS}
            if not any(all(name in candidate and candidate[name] == value for name, value in known.items())
                       for candidate in candidates):
                continue
            cache_parameters(row, saved, resolve(_at(case, row['result_path'])))
