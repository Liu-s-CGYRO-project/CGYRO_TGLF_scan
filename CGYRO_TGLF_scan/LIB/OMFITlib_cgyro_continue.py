"""Checkpoint-based continuation of explicitly selected archived CGYRO points.

The archive is the source of truth: live input/scan controls are never applied
to a restart. Planning and staging do not change the successful result case.
CGYRO rewinds its history to out.cgyro.tag and MAX_TIME adds a new time segment.
"""
from OMFITlib_cgyro_archive import catalog_runs
from builtins import (AttributeError, OSError, TypeError, ValueError, any, dict, float, int, len,
                      isinstance, iter, list, max, range, set, sorted, str, sum, type, zip)
import copy
import hashlib
import math
import os
import re
import shutil
import zipfile
from OMFITlib_cgyro_archive import (canonical_case_key, case_scans, clean_run_id,
                                   point_coordinate, scan_branch, scan_key)
from OMFITlib_cgyro_storage import result_view, submission_file
from OMFITlib_cgyro_db import run_cases, run_is_deleted, run_records
from OMFITlib_cgyro_checkpoint import directory_checkpoint
from OMFITlib_cgyro_launch import validate_checkpoint_runtime
from OMFITlib_cgyro_scratch import directory_bytes, ensure_capacity
from OMFITlib_cgyro_run_state import point_complete


def saved_run(module, token):
    """Resolve frozen state, rejecting stale dialogs after payload retirement.

    RUN_MANIFEST can still describe an older selection after archive cleanup.
    Check the authoritative run record before the current-view shortcut: its
    point IDs must never be rebound to newer public results with reused IDs.
    """
    if run_is_deleted(module, token):
        raise ValueError('This task was explicitly deleted; close the old result window.')
    entry = run_records(module).get(str(token), {})
    if entry.get('payload_retired', False):
        raise ValueError('This historical result was superseded and its payload was retired. '
                         'Reopen the result table and select the latest retained scan.')
    current = module.get('RUN_MANIFEST', {})
    if str(current.get('run_token', '')) == str(token):
        manifest = current
    else:
        manifest = entry.get('manifest', {})
    retired = set(entry.get('retired_points', {}))
    if retired:
        # Keep the original manifest as an audit record, but never advertise a
        # retired point as an unstarted job eligible for a fresh resubmission.
        manifest = copy.deepcopy(dict(manifest))
        for field in ('points', 'loaded_points', 'partial_points'):
            if field in manifest:
                manifest[field] = [point for point in manifest[field] if point not in retired]
        manifest['point_table'] = {point: row for point, row in manifest.get('point_table', {}).items()
                                   if point not in retired}
        continuation = manifest.get('continuation', {})
        if 'source_points' in continuation:
            continuation['source_points'] = [point for point in continuation['source_points'] if point not in retired]
    return manifest, result_view(module, run_cases(module, manifest))


def stopped_context(module, token):
    """Join a stopped run's frozen point table with its continuation ancestry."""
    manifest, _ = saved_run(module, token)
    if manifest.get('collection_status', '') not in ('partial', 'empty'):
        return None
    records, seen, current = [], set(), str(token)
    while current:
        if current in seen:
            raise ValueError('Circular continuation history')
        seen.add(current)
        record, cases = saved_run(module, current)
        if not record:
            raise ValueError('Missing frozen continuation history: ' + current)
        records.append((record, cases))
        current = str(record.get('continuation', {}).get('source_token', '') or '')
    rows, sources, results, readable, unfinished = {}, {}, {}, {}, set()
    for record, cases in reversed(records):
        complete_points = set(record.get('loaded_points', []))
        unfinished.difference_update(complete_points)
        unfinished.update(set(record.get('points', [])) - complete_points)
        try:
            _, _, archived = archived_case(module, record['run_token'], allow_inherited=True)
        except ValueError:
            archived = None
        if archived is not None:
            for point, row in archived['__TASKS__'].items():
                rows[point] = copy.deepcopy(dict(row))
                readable[point] = copy.deepcopy(dict(row))
                results[point] = point_result(archived, row)
        for point, row in record.get('point_table', {}).items():
            row = copy.deepcopy(dict(row))
            row.update(dict(continuation_pending=record.get('continuation_pending', {}).get(point, ''),
                            scheduler_state=record.get('point_states', {}).get(point, '')))
            rows[point] = row
            sources[point] = (record, cases)
            node = cases.get(point, None)
            if (point in list(record.get('loaded_points', [])) + list(record.get('partial_points', []))
                    and node is not None and any(base.__name__ == 'OMFITcgyro' for base in type(node).__mro__)):
                readable[point] = copy.deepcopy(dict(row))
                readable[point].update(dict(status='partial' if point in record.get('partial_points', []) else 'loaded',
                    run_token=record['run_token'], runid=record['runid'], case_id=record['case_id'],
                    source_nr=record['nr'], rho=record.get('rho', None), ion_case=record['mass'],
                    result_workDir=record.get('point_workdirs', {}).get(point, record['workDir'])))
                results[point] = node
    try:
        _, _, case = archived_case(module, token)
    except ValueError:
        case = None
    if case is not None:
        # An unchanged point may have been inherited from an earlier segment.
        for point, row in case['__TASKS__'].items():
            rows.setdefault(point, copy.deepcopy(dict(row)))
    # Ancestor reconstruction can bring a superseded point back. Retirement
    # is explicit for this frozen job, so remove it from every runtime view.
    for point in run_records(module).get(str(token), {}).get('retired_points', {}):
        for mapping in (rows, sources, results, readable):
            mapping.pop(point, None)
        unfinished.discard(point)
    planned = set(manifest.get('continuation', {}).get('source_points', manifest.get('points', [])))
    if planned - set(rows) or (planned - unfinished) - set(results):
        # A full rescan can replace a published ancestor while leaving an old
        # empty/partial child in history. Do not rebuild a smaller "full" scan.
        raise ValueError('Continuation ancestry was replaced or is incomplete. Select the latest retained scan.')
    info = copy.deepcopy(dict(case['__INFO__'] if case is not None else manifest))
    info.update(dict(source_nr=manifest['nr'], ion_case=manifest['mass'],
                     runid=manifest['runid'], points=len(rows)))
    view = dict(__INFO__=info, __TASKS__=readable)
    for point, result in results.items():
        readable[point]['resume_pending'] = point in unfinished
        path = list(readable[point]['result_path'])
        path[0] = scan_key(info, path[0])
        readable[point]['result_path'] = path
        node = view
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = result
    return dict(manifest=manifest, info=info, case=case, view=view, rows=rows, sources=sources,
                results=results, unfinished=unfinished)


def continuation_case(module, token):
    context = stopped_context(module, token)
    if context is not None:
        return context['view']
    return archived_case(module, token)[2]


def resume_source(module, token, point, context=None):
    """Choose a verified checkpoint or original input, never current GUI data."""
    context = stopped_context(module, token) if context is None else context
    if context is None:
        _, _, case = archived_case(module, token)
        result = point_result(case, case['__TASKS__'][point])
        checkpoint_tag(result.filename)
        return dict(mode='checkpoint', directory=result.filename)
    if point in context['results']:
        result = context['results'][point]
        checkpoint_tag(result.filename)  # Existing samples never silently restart from zero.
        return dict(mode='checkpoint', directory=result.filename)
    if point not in context['sources']:
        raise ValueError('No original input provenance for ' + point)
    record, cases = context['sources'][point]
    node = cases.get(point, None)
    if node is not None and any(base.__name__ == 'OMFITcgyro' for base in type(node).__mro__):
        checkpoint_tag(node.filename)
        return dict(mode='checkpoint', directory=node.filename)
    original = record.get('source_local_workDir', record.get('local_workDir', ''))
    path = os.path.join(str(original), point + '.zip')
    if isinstance(node, dict):
        retained = node.get('zip', None)
        if retained is not None and os.path.isfile(retained.filename):
            path = retained.filename
    if not os.path.isfile(path):
        # After job-ID recovery and project reopening, only the native RUN_DB
        # input owner may survive; a former /tmp pathname is not authoritative.
        path = submission_file(module, record, 'zip', point=point)
    hashes = record.get('input_sha256', {}).get(point, {})
    if not hashes:
        raise ValueError('Original input checksums are missing: ' + point)
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    if {'bin.cgyro.restart', 'out.cgyro.tag', 'out.cgyro.time'} <= names:
        mode = 'checkpoint_zip'
    else:
        reason = str(record.get('skipped_reasons', {}).get(point, ''))
        if 'out.cgyro.time' not in reason and reason != 'No time samples':
            raise ValueError('The point has incomplete output, not a confirmed unstarted input: ' + point)
        mode = 'fresh'
    return dict(mode=mode, zip=path, sha256=copy.deepcopy(dict(hashes)))


def archived_case(module, token, allow_inherited=False):
    """Resolve one retained scan; reject a dialog for a replaced scan token.

    Only ancestry reconstruction may use surviving points from a newer scan
    header. It requires the original owner token, full case/scan/coordinates
    and frozen point IDs; a stale dialog never opts into this fallback.
    """
    manifest, points = saved_run(module, token)
    stopped = manifest.get('collection_status', '') in ('partial', 'empty')
    for runid, run in catalog_runs(module).items():
        if stopped:
            break  # A stopped job uses its frozen IDs, never merged catalog IDs.
        if str(runid).startswith('__'):
            continue
        for case_id, case in run.items():
            if str(case_id).startswith('__') or not hasattr(case, 'get'):
                continue
            for _, info, tasks in case_scans(case):
                if str(info.get('run_token', '')) == str(token):
                    branch = scan_branch(case, info, tasks)
                    # A view of only this scan prevents continuation from
                    # copying unrelated axes or reusing their point IDs.
                    view = {'__INFO__': info, '__TASKS__': tasks}
                    for row in tasks.values():
                        path = row.get('result_path', [])
                        if path:
                            view[path[0]] = case[branch]
                    return runid, case_id, result_view(module, view)
                if (allow_inherited and manifest.get('status', '') == 'published'
                        and clean_run_id(runid) == clean_run_id(manifest.get('runid', ''))
                        and canonical_case_key(case_id, info) == canonical_case_key(
                            manifest.get('case_id', ''), manifest)
                        and scan_key(info) == scan_key(manifest)):
                    # A subset continuation replaces the public header but
                    # retains unselected points from its published ancestor.
                    # Published snapshots no longer own duplicate cases, so
                    # recover only those exact, still-owned public points.
                    expected = {}
                    for point, row in manifest.get('point_table', {}).items():
                        coordinate = point_coordinate(row)
                        if coordinate in expected:
                            raise ValueError('Ambiguous frozen ancestor coordinates')
                        expected[coordinate] = (point, row)
                    inherited = {}
                    for source in tasks.values():
                        if str(source.get('run_token', '')) != str(token) or not point_complete(source):
                            continue
                        coordinate = point_coordinate(source)
                        if coordinate not in expected:
                            continue
                        point, original = expected[coordinate]
                        if point in inherited:
                            raise ValueError('Ambiguous inherited ancestor coordinates')
                        row = copy.deepcopy(dict(source))
                        row.update(copy.deepcopy(dict(original)))
                        row.update(dict(task_id=point, result_path=list(source['result_path'])))
                        inherited[point] = row
                    if inherited:
                        source_info = copy.deepcopy(dict(manifest))
                        source_info.update(dict(source_nr=manifest.get('nr', ''), ion_case=manifest.get('mass', '')))
                        view = dict(__INFO__=source_info, __TASKS__=inherited)
                        for row in inherited.values():
                            view[row['result_path'][0]] = case[row['result_path'][0]]
                        return runid, case_id, result_view(module, view)
    # Older stopped jobs retain their original point IDs internally, even
    # after their public results merge into Jet/radius/isotope. Use that
    # frozen table rather than another job's identically named p000001.
    tasks, view = {}, {}
    for point, source in manifest.get('point_table', {}).items():
        result = points.get(point, None)
        if result is None or not any(base.__name__ == 'OMFITcgyro' for base in type(result).__mro__):
            continue
        row = copy.deepcopy(dict(source))
        loaded = point in manifest.get('loaded_points', []) and point not in manifest.get('partial_points', [])
        row.update(dict(task_id=point, run_token=str(token),
                        status='loaded' if loaded else 'partial', resume_pending=not loaded))
        tasks[point] = row
        node = view
        for part in row['result_path'][:-1]:
            node = node.setdefault(part, {})
        node[row['result_path'][-1]] = result
    if tasks:
        info = copy.deepcopy(dict(manifest))
        info.update(dict(ion_case=manifest.get('mass', ''), source_nr=manifest.get('nr', '')))
        view.update(dict(__INFO__=info, __TASKS__=tasks))
        return manifest.get('runid', ''), manifest.get('case_id', ''), view
    raise ValueError('The selected result was replaced or is unindexed. Reopen the result table.')


def point_result(case, row):
    node = case
    path = list(row.get('result_path', []))
    if not path or any(str(key).startswith('__') for key in path):
        raise ValueError('Missing or invalid archived result path')
    for key in path:
        node = node[key]
    return node


def checkpoint_details(directory):
    """Validate the actual binary/grid/tag together, retaining the v3 layout."""
    _, report = directory_checkpoint(directory)
    if not report['resume_ready']:
        detail = (report.get('warning', '') or report['candidates'].get('bin.cgyro.restart', {}).get('reason', '')
                  or 'bin.cgyro.restart is missing')
        raise ValueError('No verified current CGYRO checkpoint: ' + detail)
    return report


def checkpoint_tag(directory):
    """Keep the historical tag-only API for tables and continuation planning."""
    return checkpoint_details(directory)['tag']


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
    stopped = stopped_context(module, token)
    if stopped is None:
        runid, case_id, case = archived_case(module, token)
        tasks, info = case.get('__TASKS__', {}), case['__INFO__']
    else:
        tasks, info = stopped['rows'], stopped['info']
        runid, case_id = stopped['manifest']['runid'], stopped['manifest']['case_id']
    selected = list(point_ids)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError('Select at least one distinct calculation point')
    for point_id in selected:
        if point_id not in tasks or not re.fullmatch(r'p[0-9]{6,}', str(point_id)):
            raise ValueError('Unindexed calculation point: ' + str(point_id))
    sources = {point: resume_source(module, token, point, stopped) for point in selected}
    rows = {point: copy.deepcopy(dict(tasks[point])) for point in selected}
    if stopped is not None:
        for point in selected:
            if sources[point]['mode'] == 'checkpoint' and point in stopped['view']['__TASKS__']:
                rows[point] = copy.deepcopy(dict(stopped['view']['__TASKS__'][point]))
    info = copy.deepcopy(dict(info))
    previous = module.get('RUN_HISTORY', {}).get(str(token), {}).get('manifest', {})
    if not previous and str(module.get('RUN_MANIFEST', {}).get('run_token', '')) == str(token):
        previous = module['RUN_MANIFEST']
    return dict(source_token=str(token), source_runid=runid, source_case_id=case_id,
                additional_time=duration, info=info, points=selected,
                rows=rows,
                sources=sources, stopped_run=stopped is not None, source_points=list(tasks),
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


def previous_final_time(metadata, tag):
    """Keep the longest saved tail as the target across pending segments."""
    restart = metadata.get('continuation', {})
    previous = float(restart.get('previous_final_time', restart.get('checkpoint', {}).get('last_time', tag['last_time'])))
    if not math.isfinite(previous):
        raise ValueError('Invalid previous continuation final time')
    return max(float(tag['last_time']), previous)


def prepare_point(module, plan, point_id, stage, reader, runtime=None):
    """Copy to a new run directory and change only the segment duration."""
    row = plan['rows'][point_id]
    origin = plan['sources'][point_id]
    if origin['mode'] == 'checkpoint':
        ensure_capacity(stage, directory_bytes(origin['directory']))
    else:
        with zipfile.ZipFile(origin['zip']) as packed:
            ensure_capacity(stage, sum(item.file_size for item in packed.infolist()))
    if origin['mode'] == 'checkpoint':
        # The collected directory is immutable. Copy it to a new staging path,
        # preserving optional histories and leaving the original run intact.
        shutil.copytree(origin['directory'], stage)
    else:
        os.makedirs(stage)
        with zipfile.ZipFile(origin['zip']) as archive:
            if len(archive.namelist()) != len(origin['sha256']) or set(archive.namelist()) != set(origin['sha256']):
                raise ValueError('Original input archive member list changed: ' + point_id)
            for name, expected in origin['sha256'].items():
                if not name or name in ('.', '..') or '/' in name or '\\' in name:
                    raise ValueError('Invalid original input archive member: ' + name)
                digest = hashlib.sha256()
                with archive.open(name) as source_file, open(os.path.join(stage, name), 'wb') as target_file:
                    for chunk in iter(lambda: source_file.read(1024 * 1024), b''):
                        digest.update(chunk)
                        target_file.write(chunk)
                if digest.hexdigest() != expected:
                    raise ValueError('Original prepared input changed: ' + point_id + '/' + name)
    source = reader(os.path.join(stage, 'input.cgyro'))
    for name, value in row.get('values', {}).items():
        if name in ('DELTA_T', 'MAX_TIME', 'PRINT_STEP'):
            value = row.get('effective_time', {}).get(name, value)
        if name not in source or not math.isclose(float(source[name]), float(value), rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('Archived input disagrees with task {}: {}'.format(point_id, name))
    duration = plan['additional_time']
    if origin['mode'] == 'fresh':
        if runtime is not None:
            validate_checkpoint_runtime(plan['runtime'], runtime, has_checkpoint=False)
        current = source.duplicate()
        current['MAX_TIME'] = float(source['MAX_TIME']) + duration
        current.deploy(os.path.join(stage, 'input.cgyro'))
        metadata = copy.deepcopy(row)
        metadata['effective_time'] = {name: float(current[name]) for name in ('DELTA_T', 'MAX_TIME', 'PRINT_STEP')}
        metadata['continuation'] = dict(source_token=plan['source_token'], mode='fresh', additional_time=duration)
        return current, metadata, [name for name in origin['sha256'] if name.startswith('input.')]
    verified = checkpoint_details(stage)
    checkpoint = verified['candidates']['bin.cgyro.restart']
    if runtime is not None:
        validate_checkpoint_runtime(plan['runtime'], runtime, checkpoint=checkpoint)
    tag = verified['tag']
    delta_t = float(source.get('DELTA_T', 0))
    print_step = int(source.get('PRINT_STEP', 0))
    # A pending segment can have a shorter tail than its ancestor. Keep the
    # original end-time target across further resumes; never lower the bar.
    previous_final = previous_final_time(row, tag)
    # Require progress beyond the previous saved tail as well as one new sample.
    # The checkpoint may precede the last output; that tail is recalculated.
    minimum = max(delta_t * print_step, previous_final - tag['time'] + delta_t * print_step)
    if (not math.isfinite(delta_t) or delta_t <= 0 or print_step < 1
            or duration + 1e-10 * max(1., minimum) < minimum):
        raise ValueError('{}: additional time must be at least {:g} (checkpoint {:g}, last sample {:g})'.format(
            point_id, minimum, tag['time'], previous_final))
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
                                    checkpoint_layout=copy.deepcopy(checkpoint),
                                    additional_time=duration, history_sha256=prefixes,
                                    previous_final_time=previous_final)
    return current, metadata, packed_names


def validate_continued_result(result, metadata):
    """Raise for damaged history; return a warning for a valid pending segment.

    Replaying the tail after a checkpoint is readable work, not a download
    error. Retain the segment/checkpoint in the run's internal record without
    replacing a longer public result or automatically rerunning it.
    """
    restart = metadata.get('continuation', {})
    if not restart or not restart.get('checkpoint', None):
        return ''
    tag = restart['checkpoint']
    expected = restart.get('history_sha256', {})
    if expected and history_prefix(result.filename, int(tag['sample_count']), expected) != expected:
        raise ValueError('Continuation changed the pre-checkpoint history; previous results are preserved')
    times = list(result['t'])
    count = int(tag['sample_count'])
    if (count < 1 or len(times) < count or any(not math.isfinite(float(value)) for value in times)
            or any(right <= left for left, right in zip(times, times[1:]))
            or not math.isclose(float(times[count - 1]), float(tag['time']),
                                               rel_tol=1e-7, abs_tol=1e-10)):
        raise ValueError('Continuation history is truncated or invalid; previous results are preserved')
    previous_final = previous_final_time(metadata, tag)
    if len(times) == count or (float(times[-1]) <= previous_final
                              and point_status(result)['convergence'] != 'converged'):
        return ('Continuation pending: final time {:g}, previous final time {:g}, source checkpoint {:g}. '
                'Readable data retained separately; previous scans preserved.').format(
                    float(times[-1]), previous_final, float(tag['time']))
    return ''
