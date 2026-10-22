# Run and collect a 1D, 2D, or 3D CGYRO parameter scan.
import copy
from builtins import ValueError, any, dict, int, len, list, set, str
from datetime import datetime, timezone
from OMFITlib_cgyro_archive import (canonical_case_key, catalog_runs, clean_run_id, combine_cases,
                                  grouped_case_path, install_case, matching_cases, output_final_time,
                                  scan_key, store_scan, validate_preserved_scans)
from OMFITlib_cgyro_retry import collect_current
from OMFITlib_cgyro_continue import continuation_case, point_result
from OMFITlib_cgyro_queue import save_current
from OMFITlib_cgyro_storage import compact_storage, prune_storage, resolve_result, store_result
from OMFITlib_cgyro_db import run_cases
from OMFITlib_cgyro_recover import recover_archives
defaultVars(wait_for_completion=True, batch_id='', collect_stopped=False, continuation=None,
            allow_solver_retries=None, check_temp_start=True)

setup = root['SETTINGS']['SETUP']
# Direct legacy run entries inherit their run intent. A collection-only entry
# defaults to no submissions; queued run orchestration passes its intent explicitly.
retry_enabled = setup['irun'] == 1 if allow_solver_retries is None else allow_solver_retries
if setup['icgyro'] != 1:
    raise RuntimeError('Legacy GYRO submission is unavailable in this repaired CGYRO package')
dimensions = int(setup['idimrun'])
if dimensions not in (0, 1, 2, 3):
    raise ValueError('CGYRO parameter-axis count must be 0, 1, 2, or 3')

if setup['irun'] == 1:
    root['SCRIPTS']['subscan_lin.py'].run(scan_dimensions=dimensions,
        wait_for_completion=wait_for_completion, batch_id=batch_id, continuation=continuation,
        check_temp_start=check_temp_start)
if (wait_for_completion and (setup['idownsync'] == 1 or root.get('RUN_MANIFEST', {}).get('auto_collect_requested', False))
        and (collect_stopped or root.get('RUN_MANIFEST', {}).get('auto_collect_requested', False)
             or not root.get('RUN_MANIFEST', {}).get('stop_requested', False))):
    collect_current(root, OMFITx, OMFITtree, OMFITpath, OMFITascii,
                    allow_solver_retries=retry_enabled)


def result_path(manifest, point_id):
    """Resolve a flat point ID; accept pre-1.13 readable directory names."""
    table = manifest.get('point_table', {})
    if point_id in table:
        path = list(table[point_id]['result_path'])
        if len(path) != 2 * int(manifest['dimensions']) + 2 or path[-2] != 'lin':
            raise ValueError('Invalid point index for ' + point_id)
        path[0] = scan_key(manifest, path[0])
        return path
    parts = point_id.split('~')
    expected = 2 * int(manifest['dimensions']) + 2
    if len(parts) != expected or parts[-2].lower() != 'ky':
        raise ValueError('Invalid legacy manifest point: ' + point_id)
    return parts[:-2] + ['lin', parts[-1]]


def remember_collection(root):
    save_current(root, OMFITtree)


def publish_loaded_run(root):
    compact_storage(root, OMFITtree)
    # The current run is published below; only recover older retained sources.
    recover_archives(root, resolve_result, OMFITtree,
                     exclude_token=str(root.get('RUN_MANIFEST', {}).get('run_token', '')))
    manifest = root.get('RUN_MANIFEST', None)
    if not manifest or manifest.get('collection_status', '') != 'ready' and manifest.get('status', '') != 'loaded':
        return
    if manifest.get('load_errors', {}):
        raise ValueError('Result download/read errors remain; collect again before archiving.')
    if int(manifest['dimensions']) not in (1, 2, 3):
        raise ValueError('Unsupported run manifest dimension')
    loaded = list(manifest.get('loaded_points', []))
    partial = list(manifest.get('partial_points', []))
    readable = list(dict.fromkeys(loaded + partial))
    expected = list(manifest.get('points', loaded))
    if not readable:
        manifest['collection_status'] = 'empty'
        remember_collection(root)
        print('Collection finished: no readable results; {} empty/incomplete points skipped. Previous results are unchanged.'.format(len(expected)))
        return
    complete = set(loaded) == set(expected) and not manifest.get('failed_points', []) and not partial
    continuation = manifest.get('continuation', None)
    source_case = None
    if continuation:
        try:
            source_case = continuation_case(root, continuation['source_token'])
        except ValueError:
            if not continuation.get('stopped_run', False):
                raise
        if set(expected) != set(continuation['points']):
            raise ValueError('Continuation point list changed; the previous case is preserved')
        if continuation.get('stopped_run', False):
            finished = {point for point, row in (source_case or {}).get('__TASKS__', {}).items()
                        if row.get('status', '') == 'loaded' and not row.get('resume_pending', False)}
            complete = complete and set(continuation['source_points']) <= (finished | set(loaded))
    case_tag = manifest['case_tag']
    fresh_output = OMFITtree()
    if source_case is not None:
        # Rebuild native scaffolding even when a stopped run's view is a plain
        # metadata blueprint; each retained result receives a native parent.
        for row in source_case['__TASKS__'].values():
            path = row['result_path']
            node = fresh_output
            for key in path[:-1]:
                if key not in node:
                    node[key] = OMFITtree()
                node = node[key]
            node[path[-1]] = store_result(root, point_result(source_case, row), OMFITtree)
    for point_id in readable:
        path = result_path(manifest, point_id)
        node = fresh_output
        for key in path[:-1]:
            if key not in node:
                node[key] = OMFITtree()
            node = node[key]
        node[path[-1]] = copy.deepcopy(run_cases(root, manifest)[point_id])

    run_id = clean_run_id(manifest['runid'])
    if not run_id or run_id.startswith('__') or '/' in run_id:
        raise ValueError('CGYRO run ID is empty, reserved or contains a slash')
    manifest.pop('partial_runid', None)
    legacy = 'case_id' not in manifest
    base_case_key = ('nr=' + str(manifest['nr']) if legacy else str(manifest['case_id']))
    case_key = canonical_case_key(base_case_key, {'rho': manifest.get('rho', None), 'ion_case': manifest['mass']})
    previous = catalog_runs(root).get(run_id, {})
    replaced = []
    old_keys = matching_cases(root, run_id, case_key)
    for key in old_keys:
        old_info = previous[key].get('__INFO__', {})
        replaced.append(str(key))
        replaced.extend(str(value) for value in old_info.get('replaced_case_keys', []))
    # Build off-tree, preserving all other scan axes. Replacing the whole case
    # here used to discard N_THETA as soon as N_ENERGY was collected.
    prior_cases = [previous[key] for key in old_keys]
    destination = combine_cases(prior_cases, OMFITtree)

    task_rows = OMFITtree()
    if source_case is not None:
        task_rows.update(copy.deepcopy(source_case['__TASKS__']))
    for point_id in readable:
        metadata = copy.deepcopy(manifest.get('point_table', {}).get(point_id, {}))
        row = OMFITtree()
        row.update(metadata)
        row.update(dict(task_id=point_id, runid=run_id, case_id=case_key,
                        source_nr=manifest['nr'], rho=manifest.get('rho', None),
                        ion_case=manifest['mass'], status='partial' if point_id in partial else 'loaded'))
        row['result_path'] = result_path(manifest, point_id)
        row['result_workDir'] = manifest.get('point_workdirs', {}).get(point_id, manifest['workDir'])
        row['run_token'] = manifest['run_token']
        row['resume_pending'] = point_id in partial
        row['continuation_pending'] = manifest.get('continuation_pending', {}).get(point_id, '')
        row['scheduler_state'] = manifest.get('point_states', {}).get(point_id, '')
        row['final_time'] = output_final_time(resolve_result(root, run_cases(root, manifest)[point_id]))
        task_rows[point_id] = row
    for row in task_rows.values():
        row.update(dict(runid=run_id, case_id=case_key))
    info = OMFITtree()
    info.update(dict(run_token=manifest['run_token'], runid=run_id, case_id=case_key,
                     source_nr=manifest['nr'], rho=manifest.get('rho', None),
                     ion_case=manifest['mass'], dimensions=manifest['dimensions'],
                     scan_dimensions=manifest.get('scan_dimensions', manifest['dimensions']),
                     scan_axes=copy.deepcopy(manifest.get('scan_axes', [])),
                     fixed_parameters=copy.deepcopy(manifest.get('fixed_parameters', {})),
                     numeric_parameters=copy.deepcopy(manifest.get('numeric_parameters', {})),
                     scale_time_with_ky=manifest.get('scale_time_with_ky', False),
                     parameters=list(fresh_output.keys()), points=len(task_rows),
                     workDir=manifest['workDir'], job_id=manifest.get('job_id', None),
                     published_at=datetime.now(timezone.utc).isoformat(),
                     replaced_case_keys=list(dict.fromkeys(replaced)),
                     retry_count=manifest.get('retry_count', 0), attempts=copy.deepcopy(manifest.get('attempts', [])),
                     point_workdirs=copy.deepcopy(manifest.get('point_workdirs', {})),
                     server=manifest['server'], runtime=copy.deepcopy(manifest.get('runtime', {})),
                     source_runid=manifest['runid'], collection_status='complete' if complete else 'partial',
                     planned_points=list(continuation.get('source_points', expected) if continuation else expected),
                     skipped_points=list(manifest.get('skipped_points', [])),
                     continuation_pending={point: row['continuation_pending'] for point, row in task_rows.items()
                                           if row.get('continuation_pending', '')},
                     status='published'))
    info['case_path'] = grouped_case_path(case_key, info)
    if source_case is not None:
        continuations = copy.deepcopy(source_case['__INFO__'].get('continuations', []))
        continuations.append(dict(continuation, run_token=manifest['run_token']))
        info['continuations'] = continuations
        info['point_workdirs'] = {point: row['result_workDir'] for point, row in task_rows.items()
                                 if row.get('result_workDir', None) is not None}
    # Keep the task table with the results.  Reserved double-underscore keys are
    # hidden by the comparison selectors, while remaining directly inspectable
    # in the OMFIT data tree.
    store_scan(destination, fresh_output, info, task_rows, OMFITtree)
    validate_preserved_scans(prior_cases, destination, scan_key(info), task_rows)
    if 'RUN_DB' not in root:
        root['RUN_DB'] = OMFITtree()
    if run_id not in root['RUN_DB']:
        root['RUN_DB'][run_id] = OMFITtree()
    run = root['RUN_DB'][run_id]
    install_case(run, case_key, destination, OMFITtree)
    for key in old_keys:
        if key in run:
            del run[key]
    root['RUN_MANIFEST']['case_id'] = case_key
    manifest['runid'] = run_id
    manifest['collection_status'] = 'complete' if complete else 'partial'
    if complete:
        manifest['status'] = 'published'
    remember_collection(root)
    prune_storage(root)
    print('Collected {} complete and {} partial points; {} points skipped. {}'.format(
        len(loaded), len(partial), len(manifest.get('skipped_points', [])),
        'Results merged into RUN_DB / {} / {}.'.format(run_id, ' / '.join(info['case_path']))))


if wait_for_completion:
    publish_loaded_run(root)
