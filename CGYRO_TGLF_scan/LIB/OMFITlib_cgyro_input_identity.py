"""Small effective-input metadata, read only on collection or selected restart.

CGYRO's generated file expands defaults and uses ``value NAME`` lines. Comparing
its raw bytes would mistake formatting, a new duration or an MPI layout for a
different physical point. Keep the normalized parameters in the existing point
row; ordinary catalog queries never open these files.
"""
from builtins import (FileNotFoundError, KeyError, TypeError, ValueError, all, any, dict, float, frozenset, len, open, str)
import hashlib
import math
import re

# These change execution/output, not the equations, grid or numerical accuracy.
# DELTA_T, ERROR_TOL, FREQ_TOL and precision-mode flags deliberately stay in.
RUN_CONTROL_PARAMETERS = frozenset(('MAX_TIME', 'PRINT_STEP', 'RESTART_STEP',
    'RESTART_PRESERVATION_MODE', 'SILENT_FLAG', 'MPI_RANK_ORDER', 'TOROIDALS_PER_PROC',
    'MPIIO_STRIPE_FACTOR', 'MPIIO_SMALL_STRIPE_FACTOR', 'THETA_PLOT',
    'H_PRINT_FLAG', 'MOMENT_PRINT_FLAG', 'GFLUX_PRINT_FLAG', 'FIELD_PRINT_FLAG',
    'TRIAD_PRINT_FLAG', 'FULL_T_PRINT_FLAG', 'FULL_T_ASYM_PRINT_FLAG',
    'FULL_T_REAL_ONLY', 'FULL_T_DEBUG_PRINT_FLAG', 'FULL_T_KX0'))


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
        value = float(value.replace('D', 'e').replace('d', 'e'))
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
    from OMFITlib_cgyro_archive import result_file
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


def cache_parameters(row, info, result):
    """Attach verified effective parameters to this existing point row only."""
    from OMFITlib_cgyro_archive import point_values
    values, source, digest = effective_parameters(result)
    if source != 'input.cgyro.gen':
        return values  # Legacy metadata is usable; absent solver defaults are not invented.
    expected = dict(point_values(info, row))
    expected.update(row.get('effective_time', {}))
    for name, value in expected.items():
        if name not in values or not math.isclose(float(value), values[name], rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('Saved ' + source + ' disagrees with coordinate: ' + name)
    row['input_parameters'] = {name: value for name, value in values.items() if name not in RUN_CONTROL_PARAMETERS}
    row['input_parameter_source'] = source
    row['input_parameter_sha256'] = digest
    return values


def cache_competing_parameters(case, info, tasks, resolve):
    """Read only old points whose known coordinates could match this submission.

    Backfill small generated inputs off-tree during publication. Full arrays,
    checkpoint hashes and unrelated ky/parameter points are never inspected.
    """
    from OMFITlib_cgyro_archive import _at, case_scans, point_values
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
