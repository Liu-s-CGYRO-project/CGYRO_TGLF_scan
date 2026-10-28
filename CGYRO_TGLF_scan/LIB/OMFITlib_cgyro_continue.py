"""Checkpoint-based continuation of explicitly selected archived CGYRO points.

The archive is the source of truth: live input/scan controls are never applied
to a restart. Planning and staging do not change the successful result case.
CGYRO rewinds its history to out.cgyro.tag and MAX_TIME adds a new time segment.
"""
from builtins import (AttributeError, KeyError, OSError, TypeError, ValueError, abs, any, dict, float, int, len,
                      bool, isinstance, iter, list, max, open, range, set, sorted, str, sum, type, zip)
import copy
import hashlib
import json
import math
import os
import re
import shutil
import zipfile
from OMFITlib_cgyro_archive import (canonical_case_key, case_scans, clean_run_id, coordinate_path,
                                   output_final_time, point_coordinate, result_file, scan_branch, scan_key, solver_state)
from OMFITlib_cgyro_storage import submission_file, store_result, reference_id, storage_state
from OMFITlib_cgyro_result_index import (at as index_at, find_record, select_result,
                                        selected_result, scan_scope)
from OMFITlib_cgyro_db import run_cases, run_is_deleted, run_records
from OMFITlib_cgyro_checkpoint import directory_checkpoint
from OMFITlib_cgyro_launch import validate_checkpoint_runtime
from OMFITlib_cgyro_scratch import directory_bytes, ensure_capacity
from OMFITlib_cgyro_run_state import point_complete
from OMFITlib_cgyro_input_identity import effective_parameters, read_parameters, verified_parameters, RUN_CONTROL_PARAMETERS


def saved_run(module, token):
    """Read one RUN_DB input record for an explicitly unstarted point."""
    entry = run_records(module).get(str(token), {})
    if run_is_deleted(module, token):
        raise ValueError('This task input was explicitly deleted; select a retained result instead.')
    if entry.get('payload_retired', False):
        raise ValueError('This task input was superseded and retired; select a retained result instead.')
    manifest = copy.deepcopy(dict(entry.get('manifest', {})))
    retired = set(entry.get('retired_points', {}))
    manifest['points'] = [point for point in manifest.get('points', []) if point not in retired]
    manifest['point_table'] = {point: row for point, row in manifest.get('point_table', {}).items() if point not in retired}
    return manifest, entry.get('cases', {})


def stopped_context(module, token):
    """Compatibility view of one retained version, with no ancestry lookup."""
    entry = find_record(module, token)
    if not entry.get('stopped_run', False):
        return None
    rows = entry.get('resume_tasks', entry['tasks'])
    manifest = run_records(module).get(str(entry.get('run_token', '')), {}).get('manifest', entry)
    view = dict(__INFO__=entry, __TASKS__=entry['tasks'])
    results = {}
    for point, row in entry['tasks'].items():
        node = view
        for key in row['result_path'][:-1]:
            node = node.setdefault(key, {})
        result = index_at(module['RUN_DB'], entry['result_locations'][point])
        node[row['result_path'][-1]] = result
        results[point] = result
    scope = scan_scope(entry)
    return dict(manifest=manifest, info=entry, case=view, view=view, rows=rows,
                sources={point: (manifest, {}) for point in rows}, results=results,
                unfinished=set(rows) - set(manifest.get('loaded_points', [])),
                planned_points=list(rows) + scope['unknown'], missing_points=scope['unknown'],
                history_warning='', entry=entry)


def continuation_case(module, token):
    return archived_case(module, token)[2]


def resume_source(module, token, point, context=None, binding=None):
    """Use the selected owner, or the exact RUN_DB input of an unstarted point."""
    if binding is None:
        entry = context.get('entry', None) if context is not None else find_record(module, token)
        if entry is not None and point in entry.get('tasks', {}):
            binding = select_result(module, entry, point)
    if binding is not None and binding.get('mode', None) != 'input':
        result = selected_result(module, binding)
        actual = validate_selected_input(result, binding['info'], binding['row'])
        report = checkpoint_details(result.filename)
        saved = storage_state(module).get('checkpoints', {}).get(binding.get('result_id', ''), '')
        if saved:
            expected = json.loads(saved)['candidates'].get('bin.cgyro.restart', {}).get('sha256', '')
            if expected and report['candidates']['bin.cgyro.restart'].get('sha256', '') != expected:
                raise ValueError('Selected checkpoint checksum disagrees with the stored result')
        restart_files(result.filename, {name: float(actual.get(name, 1)) for name in ('N_TOROIDAL', 'PROFILE_MODEL')}, verified=True)
        _, parameter_source, parameter_digest = effective_parameters(result)
        return dict(mode='checkpoint', directory=result.filename, checkpoint=report['tag'],
                    checkpoint_sha256=report['candidates']['bin.cgyro.restart']['sha256'],
                    input_sha256=_file_sha256(result_file(result, 'input.cgyro')),
                    generated_sha256=parameter_digest if parameter_source == 'input.cgyro.gen' else '',
                    runtime=copy.deepcopy(dict(binding['info'].get('runtime', {}))))
    if binding is not None:
        token = binding['record_token']
    record, _ = saved_run(module, token.removeprefix('version:') if str(token).startswith('version:') else token)
    # Only this job's frozen input may restart an unstarted point. In particular
    # source_token is not followed when the parent result has been collected.
    if point not in record.get('point_table', {}):
        raise ValueError(str(point) + ': no retained result or frozen input in RUN_DB')
    path = submission_file(module, record, 'zip', point=point, stored_only=True)
    hashes = record.get('input_sha256', {}).get(point, {})
    if not hashes:
        raise ValueError('Original input checksums are missing: ' + point)
    if binding is not None and dict(hashes) != binding['input_hashes']:
        raise ValueError('The selected frozen input changed: ' + point)
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


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_selected_input(result, info, row):
    """Check the selected owner's input against its stored coordinate/hash."""
    actual, effective, source, digest = verified_parameters(result, row.get('input_sha256', ''))
    if row.get('input_parameters', None) is not None:
        parameters = {name: value for name, value in effective.items() if name not in RUN_CONTROL_PARAMETERS}
        if parameters != dict(row['input_parameters']):
            raise ValueError('Selected input.cgyro.gen disagrees with saved effective parameters')
    if row.get('input_parameter_sha256', '') and digest != row['input_parameter_sha256']:
        raise ValueError('Selected generated input checksum disagrees with the result index')
    expected = dict(info.get('numeric_parameters', {}))
    expected.update(info.get('fixed_parameters', {}))
    expected.update(row.get('values', {}))
    expected.update(row.get('effective_time', {}))
    for name, value in expected.items():
        if name not in effective or not math.isclose(effective[name],
                                                   float(value), rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError('Selected input.cgyro disagrees with coordinate: ' + str(name))
    return effective


def archived_case(module, token, allow_inherited=False):
    """Adapt the explicit RUN_DB version for older callers; never join parents."""
    entry = find_record(module, token)
    if not entry['tasks']:
        raise ValueError('The selected version has no retained results')
    view = dict(__INFO__=entry, __TASKS__=entry['tasks'])
    for point, row in entry['tasks'].items():
        node = view
        for part in row['result_path'][:-1]:
            node = node.setdefault(part, {})
        # Resolving the selected leaf is the caller's responsibility.
        node[row['result_path'][-1]] = index_at(module['RUN_DB'], entry['result_locations'][point])
    return entry['runid'], entry['case_id'], view


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
    """Return the tag only after full checkpoint validation for continuation."""
    return checkpoint_details(directory)['tag']


def checkpoint_preview(result):
    """Read a bounded tag/time hint, never certify or read a restart binary.

    Opening a point picker must not validate gigabytes of unselected restart
    payloads. The continuation planner still calls checkpoint_tag on every
    selected point before staging or submitting anything.
    """
    with open(result_file(result, 'out.cgyro.tag'), 'rb') as handle:
        fields = handle.read(4096).split()
    if len(fields) < 2:
        raise ValueError('Missing checkpoint time metadata')
    count = int(fields[0])
    time = float(fields[1].replace(b'D', b'E').replace(b'd', b'e'))
    last = output_final_time(result)
    if count < 1 or not math.isfinite(time) or time < 0 or last is None or time > last + 1e-7 * max(1., abs(last)):
        raise ValueError('Invalid checkpoint time metadata')
    return dict(sample_count=count, time=time, last_time=last)


def point_status(result, *, verify_checkpoint=True):
    """Read solver status; UI previews defer binary validation to continuation."""
    status = dict(convergence=solver_state(result), checkpoint=None, reason='')
    try:
        status['checkpoint'] = checkpoint_tag(result.filename) if verify_checkpoint else checkpoint_preview(result)
        if not verify_checkpoint:
            status['reason'] = '检查点时间仅作预览；续算前将完整校验所选点。'
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


def continuation_plan(module, token, point_ids, additional_time, selections=None, scope=None):
    """Freeze selected versions, retaining scan coverage as metadata only.

    UI and submission pass the same owner IDs; a public merge between them
    cannot silently switch to a different checkpoint at the same coordinate.
    """
    duration = float(additional_time)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Additional simulation time must be finite and positive')
    selected = list(point_ids)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError('Select at least one distinct calculation point')
    entry = find_record(module, token) if selections is None else None
    if entry is not None:
        tasks = entry.get('resume_tasks', entry['tasks'])
        scope = scan_scope(entry)
    else:
        tasks = {point: binding.get('row', {}) for point, binding in selections.items()}
    bindings, sources, rejected = {}, {}, {}
    for point in selected:
        try:
            if point not in tasks or not re.fullmatch(r'p[0-9]{6,}', str(point)):
                raise ValueError('Unindexed calculation point: ' + str(point))
            binding = select_result(module, entry, point) if selections is None else selections[point]
            source = resume_source(module, token, point, binding=binding)
            if source.get('checkpoint', None) is not None:
                tag = source['checkpoint']
                if tag['time'] + duration <= previous_final_time(binding['row'], tag):
                    raise ValueError('Additional time must extend beyond this point\'s previous final sample')
            if binding.get('legacy_object_id', None) is not None:
                # Upgrade only this validated native point, using the existing
                # content owner store. Querying/listing never performs hashing.
                owner = selected_result(module, binding)
                factory = type(module['RUN_DB'])
                reference = store_result(module, owner, factory)
                parent = index_at(module['RUN_DB'], binding['location'][:-1])
                parent[binding['location'][-1]] = reference
                binding = dict(binding, result_id=reference_id(reference))
                binding.pop('legacy_object_id', None)
                source['directory'] = selected_result(module, binding).filename
            bindings[point], sources[point] = copy.deepcopy(binding), source
        except (KeyError, OSError, TypeError, ValueError) as exc:
            if len(selected) == 1:
                raise
            rejected[point] = str(exc)
    selected = [point for point in selected if point in sources]
    if not selected:
        raise ValueError('No selected point can restart:\n' + '\n'.join(point + ': ' + reason for point, reason in rejected.items()))
    info = copy.deepcopy(bindings[selected[0]]['info'] if selected[0] in bindings else
                         {key: value for key, value in entry.items() if key not in
                          ('tasks', 'resume_tasks', 'result_locations')})
    rows = {point: copy.deepcopy(dict(tasks[point])) for point in selected}
    return dict(source_token=str(token), source_runid=info['runid'], source_case_id=info['case_id'],
                additional_time=duration, info=info, points=selected, rows=rows, sources=sources,
                selections=bindings, scope=copy.deepcopy(scope), rejected=rejected,
                stopped_run=bool(entry and entry.get('stopped_run', False)),
                source_points=list(tasks), runtime=copy.deepcopy(dict(info.get('runtime', {}))),
                server=info.get('server', ''), case_tag=info.get('case_tag', 'linear'))


def restart_files(directory, source, verified=False):
    """Carry standard histories with the checkpoint; omit old exit/batch files.

    CGYRO opens existing time/frequency/precision streams while rewinding. An
    archive containing only the restart binary cannot provide a valid restart.
    Version-specific optional outputs are copied when present, without inventing
    histories for files that were never written by that solver version.
    """
    if not verified:
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
    """The selected result's own time stream defines the tail to recalculate."""
    previous = float(tag['last_time'])
    if not math.isfinite(previous):
        raise ValueError('Invalid selected result final time')
    return previous


def prepare_point(module, plan, point_id, stage, reader, runtime=None):
    """Copy to a new run directory and change only the segment duration."""
    row = copy.deepcopy(plan['rows'][point_id])
    axes = plan.get('info', {}).get('scan_axes', [])
    if axes:
        # Job manifests use the primary axis name; the public archive uses a
        # combined scan key. Preserve any extra physical coordinate leaf.
        for name in ('result_path', 'coordinate_path'):
            if row.get(name, None):
                row[name][0] = axes[0]['name']
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
        if _file_sha256(os.path.join(stage, 'input.cgyro')) != origin['input_sha256']:
            raise ValueError('Selected input changed while preparing continuation: ' + point_id)
        if origin.get('generated_sha256', '') and _file_sha256(os.path.join(stage, 'input.cgyro.gen')) != origin['generated_sha256']:
            raise ValueError('Selected generated input changed while preparing continuation: ' + point_id)
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
    if origin.get('generated_sha256', ''):
        generated, _ = read_parameters(os.path.join(stage, 'input.cgyro.gen'), generated=True)
        for name, value in generated.items():
            if name not in source:
                source[name] = value  # Freeze the selected solver's defaults too.
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
    if origin['mode'] == 'checkpoint' and checkpoint['sha256'] != origin['checkpoint_sha256']:
        raise ValueError('Selected checkpoint changed while preparing continuation: ' + point_id)
    if runtime is not None:
        validate_checkpoint_runtime(origin.get('runtime', plan['runtime']), runtime, checkpoint=checkpoint)
    tag = verified['tag']
    delta_t = float(source.get('DELTA_T', 0))
    print_step = int(source.get('PRINT_STEP', 0))
    # The checkpoint can precede this result's last output sample. Recalculate
    # that tail, then require at least one new sample beyond the selected result.
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
    error. The publisher selects one result per coordinate, preferring actual
    convergence and then simulation time. This function never requests a rerun.
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
                'Archive selection will retain the converged or more advanced result.').format(
                    float(times[-1]), previous_final, float(tag['time']))
    return ''
