# Run and collect a 1D, 2D, or 3D CGYRO parameter scan.
import copy
from builtins import ValueError, all, any, bool, dict, int, len, list, set, sorted, str
from datetime import datetime, timezone
from OMFITlib_cgyro_archive import (cache_merge_status, canonical_case_key, case_scans, catalog_runs, clean_run_id, combine_cases, continuation_failed, coordinate_path, full_point_coordinate,
                                  grouped_case_path, install_case, matching_cases, output_final_time,
                                  scan_key, share_matching_inputs, store_scan, validate_preserved_scans)
from OMFITlib_cgyro_retry import collect_current
from OMFITlib_cgyro_continue import point_status
from OMFITlib_cgyro_result_index import (RESULT_INFO_FIELDS, at as index_at, release_published_results, scan_scope, merge_scopes, scan_completion)
from OMFITlib_cgyro_queue import save_current
from OMFITlib_cgyro_storage import compact_storage, reference_id, resolve_result
from OMFITlib_cgyro_db import run_cases
from OMFITlib_cgyro_reference import copy_result_tree
from OMFITlib_cgyro_input_identity import cache_parameters, cache_competing_parameters
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
        coordinate = coordinate_path(table[point_id])
        if len(coordinate) != 2 * int(manifest['dimensions']) + 2 or coordinate[-2] != 'lin':
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
    compact_storage(root, OMFITtree, run_token=root.get('RUN_MANIFEST', {}).get('run_token', ''))
    manifest = root.get('RUN_MANIFEST', None)
    if not manifest or manifest.get('collection_status', '') != 'ready' and manifest.get('status', '') != 'loaded':
        return
    if int(manifest['dimensions']) not in (1, 2, 3):
        raise ValueError('Unsupported run manifest dimension')
    errors = manifest.get('load_errors', {})
    loaded = [point for point in manifest.get('loaded_points', []) if point not in errors]
    partial = [point for point in manifest.get('partial_points', []) if point not in errors]
    readable = list(dict.fromkeys(loaded + partial))
    expected = list(manifest.get('points', loaded))
    if not readable:
        if errors:
            raise ValueError('Result download/read errors remain; no verified points can be archived: ' + str(errors))
        manifest['submission_complete'] = False
        manifest['scan_complete'] = False
        manifest['collection_status'] = 'empty'
        remember_collection(root)
        print('Collection finished: no readable results; {} empty/incomplete points skipped. Previous results are unchanged.'.format(len(expected)))
        return
    complete = (set(loaded) == set(expected) and not manifest.get('failed_points', [])
                and not partial and not manifest.get('load_errors', {}))
    continuation = manifest.get('continuation', None)
    if continuation and set(expected) != set(continuation['points']):
        raise ValueError('Continuation point list changed; the previous case is preserved')
    # This attempt is self-contained. All existing coordinates are retained by
    # store_scan; neither files nor completion evidence are borrowed from jobs.
    case_tag = manifest['case_tag']
    fresh_output = OMFITtree()
    for point_id in readable:
        path = result_path(manifest, point_id)
        node = fresh_output
        for key in path[:-1]:
            if key not in node:
                node[key] = OMFITtree()
            node = node[key]
        node[path[-1]] = copy_result_tree(run_cases(root, manifest)[point_id], OMFITtree)

    run_id = clean_run_id(manifest['runid'])
    if not run_id or run_id.startswith('__') or '/' in run_id:
        raise ValueError('CGYRO run ID is empty, reserved or contains a slash')
    manifest.pop('partial_runid', None)
    legacy = 'case_id' not in manifest
    base_case_key = ('nr=' + str(manifest['nr']) if legacy else str(manifest['case_id']))
    case_key = canonical_case_key(base_case_key, {'rho': manifest.get('rho', None), 'ion_case': manifest['mass']})
    previous = catalog_runs(root, run_id, case_key).get(run_id, {})
    replaced = []
    old_keys = matching_cases(root, run_id, case_key)
    for key in old_keys:
        old_info = previous[key].get('__INFO__', {})
        replaced.append(str(key))
        replaced.extend(str(value) for value in old_info.get('replaced_case_keys', []))
    # Build off-tree, preserving all other scan axes. Replacing the whole case
    # here used to discard N_THETA as soon as N_ENERGY was collected.
    prior_cases = [copy_result_tree(previous[key], OMFITtree) for key in old_keys]

    task_rows = OMFITtree()
    for point_id in readable:
        metadata = copy.deepcopy(manifest.get('point_table', {}).get(point_id, {}))
        row = OMFITtree()
        row.update(metadata)
        row.update(dict(task_id=point_id, runid=run_id, case_id=case_key,
                        source_nr=manifest['nr'], rho=manifest.get('rho', None),
                        ion_case=manifest['mass'], status='partial' if point_id in partial else 'loaded'))
        row['result_path'] = result_path(manifest, point_id)
        if row.get('coordinate_path', None):
            row['coordinate_path'][0] = row['result_path'][0]
        row['result_workDir'] = manifest.get('point_workdirs', {}).get(point_id, manifest['workDir'])
        row['run_token'] = manifest['run_token']
        row['resume_pending'] = point_id in partial
        row['continuation_pending'] = manifest.get('continuation_pending', {}).get(point_id, '')
        row['scheduler_state'] = manifest.get('point_states', {}).get(point_id, '')
        owner = run_cases(root, manifest)[point_id]
        summary = row.get('result_summary', {})
        if summary.get('result_id', None) == reference_id(owner) and summary.get('version', 0) == 1:
            row.update(dict((name, summary[name]) for name in ('final_time', 'solver_status', 'checkpoint_time')))
        else:
            # Older collected projects lack summaries. Read only this point's
            # small metadata files; never parse other scans to repair the cache.
            result = resolve_result(root, owner)
            row['final_time'] = output_final_time(result)
            hint = point_status(result, verify_checkpoint=False)
            row['solver_status'] = hint['convergence']
            row['checkpoint_time'] = (hint.get('checkpoint', None) or {}).get('time', None)
            cache_parameters(row, manifest, result)
        row['input_sha256'] = manifest.get('input_sha256', {}).get(point_id, {}).get('input.cgyro', row.get('input_sha256', ''))
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
                     server=manifest['server'], case_tag=case_tag, runtime=copy.deepcopy(manifest.get('runtime', {})),
                     source_runid=manifest['runid'], collection_status='complete' if complete else 'partial',
                     submission_complete=complete,
                     planned_points=list(continuation.get('source_points', expected) if continuation else expected),
                     skipped_points=list(manifest.get('skipped_points', [])),
                     continuation_pending={point: row['continuation_pending'] for point, row in task_rows.items()
                                           if row.get('continuation_pending', '')},
                     status='published'))
    info['case_path'] = grouped_case_path(case_key, info)
    if continuation:
        # Provenance is diagnostic metadata only. The result merge does not
        # load or require any source token's point table.
        info['continuations'] = [dict(continuation, run_token=manifest['run_token'])]
    # Keep the task table with the results.  Reserved double-underscore keys are
    # hidden by the comparison selectors, while remaining directly inspectable
    # in the OMFIT data tree.
    for row in task_rows.values():
        row['result_info'] = {name: copy.deepcopy(info[name]) for name in RESULT_INFO_FIELDS if name in info}
    # Backfill detached originals before merging, so retention still detects
    # any point accidentally omitted by the merge. This copies no file payloads.
    for case in prior_cases:
        cache_competing_parameters(case, info, task_rows, lambda node: resolve_result(root, node))
    destination = combine_cases(prior_cases, OMFITtree)
    if continuation:
        cache_merge_status(destination, info, task_rows, lambda node: resolve_result(root, node))
    store_scan(destination, fresh_output, info, task_rows, OMFITtree, prefer_progress=bool(continuation))
    share_matching_inputs(destination, info, task_rows, OMFITtree, prefer_progress=bool(continuation))
    scope = continuation.get('scope', None) if continuation else None
    if scope is None:
        scope = scan_scope(dict(info, resume_tasks=manifest.get('point_table', {})))
        if continuation and set(continuation.get('source_points', [])) - set(expected):
            scope['unknown'] = sorted(set(continuation['source_points']) - set(expected))
    prior_scopes = [scan_scope(dict(old_info, tasks=old_tasks)) for case in prior_cases
                    for key, old_info, old_tasks in case_scans(case) if key == scan_key(info)]
    scope = merge_scopes(scope, *prior_scopes)
    scan = destination['__SCANS__'][scan_key(info)]
    if continuation:
        winners = {full_point_coordinate(scan['info'], row): reference_id(index_at(destination, row['result_path']))
                   for row in scan['tasks'].values()}
        for point, row in task_rows.items():
            row['archive_pending'] = (continuation_failed(row) and
                winners[full_point_coordinate(info, row)] != reference_id(run_cases(root, manifest)[point]))
    scan_complete = scan_completion(scan['info'], scan['tasks'], scope)
    scan['info'].update(dict(scan_complete=scan_complete, submission_complete=complete,
                        planned_coordinates=copy.deepcopy(scope),
                        collection_status='complete' if scan_complete else 'partial'))
    manifest.update(dict(submission_complete=complete, scan_complete=scan_complete))
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
    manifest['collection_status'] = 'incomplete' if errors else ('complete' if complete else 'partial')
    for point, row in task_rows.items():
        manifest['point_table'][point] = copy.deepcopy(dict(row))
    manifest['unpublished_points'] = [point for point, row in task_rows.items() if row.get('archive_pending', False)]
    if complete:
        manifest['status'] = 'published'
    remember_collection(root)
    release_published_results(root, destination, verified_cases=prior_cases)
    # Unlink only the published coordinates here. Proving an owner has no
    # remaining references is a global maintenance operation, not collection.
    # One current result per coordinate. Job manifests retain provenance, not
    # alternate old payload versions; unrelated/unselected points stay intact.
    print('Collected {} complete and {} partial points; {} points skipped. {}'.format(
        len(loaded), len(partial), len(manifest.get('skipped_points', [])),
        'Results merged into RUN_DB / {} / {}.'.format(run_id, ' / '.join(info['case_path']))))


if wait_for_completion:
    publish_loaded_run(root)
