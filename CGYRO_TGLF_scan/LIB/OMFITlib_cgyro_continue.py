"""Checkpoint-based continuation of explicitly selected archived CGYRO points.

The archive is the source of truth: live input/scan controls are never applied
to a restart. Planning and staging do not change the successful result case.
CGYRO rewinds its history to out.cgyro.tag and MAX_TIME adds a new time segment.
"""
from builtins import (AttributeError, OSError, TypeError, ValueError, any, dict, float, int, len,
                      list, max, range, set, sorted, str, zip)
import copy
import hashlib
import math
import os
import re


def archived_case(module, token):
    """Reject stale result dialogs instead of continuing a replaced case."""
    for runid, run in module.get('RUN_DB', {}).items():
        if str(runid).startswith('__'):
            continue
        for case_id, case in run.items():
            if str(case_id).startswith('__') or not hasattr(case, 'get'):
                continue
            info = case.get('__INFO__', {})
            if str(info.get('run_token', '')) == str(token):
                return runid, case_id, case
    raise ValueError('The selected result was replaced or is unindexed. Reopen the result table.')


def point_result(case, row):
    node = case
    path = list(row.get('result_path', []))
    if not path or any(str(key).startswith('__') for key in path):
        raise ValueError('Missing or invalid archived result path')
    for key in path:
        node = node[key]
    return node


def checkpoint_tag(directory):
    """Check the paired binary/tag and the saved time samples before submission."""
    for name in ('input.cgyro', 'bin.cgyro.restart', 'out.cgyro.tag', 'out.cgyro.time'):
        path = os.path.join(directory, name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise ValueError('Missing checkpoint file: ' + name)
    with open(os.path.join(directory, 'out.cgyro.tag'), encoding='ascii') as handle:
        fields = handle.read().split()
    if len(fields) < 2:
        raise ValueError('Invalid out.cgyro.tag')
    count = int(fields[0])
    time = float(fields[1].replace('D', 'e').replace('d', 'e'))
    if count < 1 or not math.isfinite(time) or time < 0:
        raise ValueError('Invalid checkpoint time or sample count')
    times = []
    with open(os.path.join(directory, 'out.cgyro.time'), encoding='ascii') as handle:
        for line in handle:
            if line.strip():
                times.append(float(line.split()[0].replace('D', 'e').replace('d', 'e')))
    if (count > len(times) or any(not math.isfinite(value) for value in times)
            or any(right <= left for left, right in zip(times, times[1:]))
            or not math.isclose(times[count - 1], time, rel_tol=1e-7, abs_tol=1e-10)):
        raise ValueError('Checkpoint tag does not match the saved time history')
    return dict(sample_count=count, time=time, last_time=times[-1])


def point_status(result):
    """Solver termination is distinct from a small tail fluctuation estimate."""
    status = dict(convergence='unknown', checkpoint=None, reason='')
    try:
        directory = result.filename
        with open(os.path.join(directory, 'out.cgyro.info'), encoding='utf-8', errors='replace') as handle:
            for line in handle:
                if 'Linear converged' in line:
                    status['convergence'] = 'converged'
                elif 'Linear terminated at max time' in line:
                    status['convergence'] = 'max_time'
                elif 'Integration error exceeded limit' in line or line.lstrip().startswith('ERROR:'):
                    status['convergence'] = 'failed'
    except (OSError, AttributeError):
        pass
    try:
        status['checkpoint'] = checkpoint_tag(result.filename)
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        status['reason'] = str(exc)
    return status


def history_prefix(directory, count, names):
    """Fingerprint the samples CGYRO must retain before appending a segment."""
    checksums = {}
    for name in names:
        digest = hashlib.sha256()
        with open(os.path.join(directory, name), 'rb') as handle:
            for _ in range(count):
                line = handle.readline()
                if not line.strip():
                    raise ValueError('Incomplete checkpoint history: ' + name)
                digest.update(line)
        checksums[name] = digest.hexdigest()
    return checksums


def continuation_plan(module, token, point_ids, additional_time):
    """Freeze identity and rows; stage from the archive again at execution time."""
    duration = float(additional_time)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Additional simulation time must be finite and positive')
    runid, case_id, case = archived_case(module, token)
    tasks = case.get('__TASKS__', {})
    selected = list(point_ids)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError('Select at least one distinct calculation point')
    for point_id in selected:
        if point_id not in tasks or not re.fullmatch(r'p[0-9]{6,}', str(point_id)):
            raise ValueError('Unindexed calculation point: ' + str(point_id))
        checkpoint_tag(point_result(case, tasks[point_id]).filename)
    info = copy.deepcopy(dict(case['__INFO__']))
    previous = module.get('RUN_HISTORY', {}).get(str(token), {}).get('manifest', {})
    if not previous and str(module.get('RUN_MANIFEST', {}).get('run_token', '')) == str(token):
        previous = module['RUN_MANIFEST']
    return dict(source_token=str(token), source_runid=runid, source_case_id=case_id,
                additional_time=duration, info=info, points=selected,
                rows={point: copy.deepcopy(dict(tasks[point])) for point in selected},
                runtime=copy.deepcopy(dict(info.get('runtime', previous.get('runtime', {})))),
                server=info.get('server', previous.get('server', '')),
                case_tag=previous.get('case_tag', 'linear'))


def restart_files(directory, source):
    """Carry standard histories with the checkpoint; omit old exit/batch files.

    CGYRO opens existing time/frequency/precision streams while rewinding. An
    archive containing only the restart binary cannot provide a valid restart.
    Version-specific optional outputs are copied when present, without inventing
    histories for files that were never written by that solver version.
    """
    checkpoint_tag(directory)
    required = ['out.cgyro.prec']
    required.append('out.cgyro.freq' if int(source.get('N_TOROIDAL', 1)) == 1 else 'bin.cgyro.freq')
    if int(source.get('PROFILE_MODEL', 1)) == 2:
        required.extend(('input.profiles', 'input.profiles.geo'))
    for name in required:
        path = os.path.join(directory, name)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise ValueError('Restart history/input missing: ' + name)
    # The flux and potential histories are rewound by MPI-IO too. Accept
    # earlier ASCII output names, but never silently create an empty stream.
    for suffix in ('ky_flux', 'kxky_phi'):
        if not any(os.path.isfile(os.path.join(directory, prefix + suffix))
                   and os.path.getsize(os.path.join(directory, prefix + suffix)) > 0
                   for prefix in ('bin.cgyro.', 'out.cgyro.')):
            raise ValueError('Restart history missing: ' + suffix)
    names = ['input.cgyro'] + [name for name in required if name.startswith('input.')]
    for name in sorted(os.listdir(directory)):
        if (name.startswith(('out.cgyro.', 'bin.cgyro.')) and not name.endswith('.old')
                and os.path.isfile(os.path.join(directory, name))):
            names.append(name)
    return names


def prepare_point(module, plan, point_id, stage, reader):
    """Copy to a new run directory and change only the segment duration."""
    _, _, case = archived_case(module, plan['source_token'])
    row = plan['rows'][point_id]
    result = point_result(case, row)
    result.deploy(stage)  # stage must not exist: OMFIT otherwise appends a basename.
    tag = checkpoint_tag(stage)
    source = reader(os.path.join(stage, 'input.cgyro'))
    for name, value in row.get('values', {}).items():
        if name not in source or not math.isclose(float(source[name]), float(value), rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('Archived input disagrees with task {}: {}'.format(point_id, name))
    duration = plan['additional_time']
    delta_t = float(source.get('DELTA_T', 0))
    print_step = int(source.get('PRINT_STEP', 0))
    # Require progress beyond the previous saved tail as well as one new sample.
    # The checkpoint may precede the last output; that tail is recalculated.
    minimum = max(delta_t * print_step, tag['last_time'] - tag['time'] + delta_t * print_step)
    if (not math.isfinite(delta_t) or delta_t <= 0 or print_step < 1
            or duration + 1e-10 * max(1., minimum) < minimum):
        raise ValueError('{}: additional time must be at least {:g} (checkpoint {:g}, last sample {:g})'.format(
            point_id, minimum, tag['time'], tag['last_time']))
    packed_names = restart_files(stage, source)
    prefix_names = ['out.cgyro.time']
    if 'out.cgyro.freq' in packed_names:
        prefix_names.append('out.cgyro.freq')
    prefixes = history_prefix(stage, tag['sample_count'], prefix_names)
    current = source.duplicate()
    current['MAX_TIME'] = duration
    # No re-scaling by ky, no reapplication of the current parameter panel.
    current.deploy(os.path.join(stage, 'input.cgyro'))
    metadata = copy.deepcopy(row)
    metadata['effective_time'] = {name: float(current[name]) for name in ('DELTA_T', 'MAX_TIME', 'PRINT_STEP')}
    metadata['continuation'] = dict(source_token=plan['source_token'], checkpoint=tag,
                                    additional_time=duration, history_sha256=prefixes)
    return current, metadata, packed_names


def validate_continued_result(result, metadata):
    """Reject a no-progress collection, preserving the previous published case."""
    restart = metadata.get('continuation', {})
    if not restart:
        return
    tag = restart['checkpoint']
    expected = restart.get('history_sha256', {})
    if expected and history_prefix(result.filename, int(tag['sample_count']), expected) != expected:
        raise ValueError('Continuation changed the pre-checkpoint history; previous results are preserved')
    times = list(result['t'])
    count = int(tag['sample_count'])
    if (len(times) <= count or any(not math.isfinite(float(value)) for value in times)
            or any(right <= left for left, right in zip(times, times[1:]))
            or not math.isclose(float(times[count - 1]), float(tag['time']),
                                               rel_tol=1e-7, abs_tol=1e-10)
            or float(times[-1]) <= float(tag['time'])):
        raise ValueError('Continuation did not extend the saved time history; previous results are preserved')
    if float(times[-1]) <= float(tag['last_time']) and point_status(result)['convergence'] != 'converged':
        raise ValueError('Continuation has not passed the previous final time or converged; previous results are preserved')
