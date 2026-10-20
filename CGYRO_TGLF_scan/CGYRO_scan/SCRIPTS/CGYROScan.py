# Run and collect a 1D, 2D, or 3D CGYRO parameter scan.
import copy
from builtins import ValueError, dict, int, len, list, set, str
from datetime import datetime, timezone
from OMFITlib_cgyro_archive import canonical_case_key, combine_cases, matching_cases, store_scan
from OMFITlib_cgyro_retry import collect_current
from OMFITlib_cgyro_continue import archived_case
defaultVars(wait_for_completion=True, batch_id='', collect_stopped=False, continuation=None)

setup = root['SETTINGS']['SETUP']
if setup['icgyro'] != 1:
    raise RuntimeError('Legacy GYRO submission is unavailable in this repaired CGYRO package')
dimensions = int(setup['idimrun'])
if dimensions not in (0, 1, 2, 3):
    raise ValueError('CGYRO parameter-axis count must be 0, 1, 2, or 3')

if setup['irun'] == 1:
    root['SCRIPTS']['subscan_lin.py'].run(scan_dimensions=dimensions,
        wait_for_completion=wait_for_completion, batch_id=batch_id, continuation=continuation)
if (wait_for_completion and setup['idownsync'] == 1
        and (collect_stopped or not root.get('RUN_MANIFEST', {}).get('stop_requested', False))):
    collect_current(root, OMFITx, OMFITtree, OMFITpath, OMFITascii)


def result_path(manifest, point_id):
    """Resolve a flat point ID; accept pre-1.13 readable directory names."""
    table = manifest.get('point_table', {})
    if point_id in table:
        path = list(table[point_id]['result_path'])
        if len(path) != 2 * int(manifest['dimensions']) + 2 or path[-2] != 'lin':
            raise ValueError('Invalid point index for ' + point_id)
        return path
    parts = point_id.split('~')
    expected = 2 * int(manifest['dimensions']) + 2
    if len(parts) != expected or parts[-2].lower() != 'ky':
        raise ValueError('Invalid legacy manifest point: ' + point_id)
    return parts[:-2] + ['lin', parts[-1]]


def publish_loaded_run(root):
    manifest = root.get('RUN_MANIFEST', None)
    if not manifest or manifest.get('status', None) != 'loaded':
        print('No fully loaded run to publish; preserved results are unchanged.')
        return
    if int(manifest['dimensions']) not in (1, 2, 3):
        raise ValueError('Unsupported run manifest dimension')
    loaded = list(manifest.get('loaded_points', []))
    expected = list(manifest.get('points', loaded))
    if (not loaded or len(loaded) != len(expected) or set(loaded) != set(expected)
            or manifest.get('failed_points', []) or manifest.get('partial_points', [])):
        raise ValueError('Only a completely collected scan can replace the previous results for these axes')
    continuation = manifest.get('continuation', None)
    source_case = None
    if continuation:
        _, _, source_case = archived_case(root, continuation['source_token'])
        if set(expected) != set(continuation['points']):
            raise ValueError('Continuation point list changed; the previous case is preserved')
    case_tag = manifest['case_tag']
    fresh_output = OMFITtree()
    if source_case is not None:
        # archived_case returns this scan only; unselected points survive.
        for key in source_case:
            if not str(key).startswith('__'):
                fresh_output[key] = copy.deepcopy(source_case[key])
    for point_id in manifest['loaded_points']:
        path = result_path(manifest, point_id)
        node = fresh_output
        for key in path[:-1]:
            if key not in node:
                node[key] = OMFITtree()
            node = node[key]
        node[path[-1]] = copy.deepcopy(root['Cases'][case_tag][point_id])

    run_id = str(manifest['runid'])
    legacy = 'case_id' not in manifest
    base_case_key = ('nr=' + str(manifest['nr']) if legacy else str(manifest['case_id']))
    case_key = canonical_case_key(base_case_key, {'rho': manifest.get('rho', None), 'ion_case': manifest['mass']})
    previous = root.get('RUN_DB', {}).get(run_id, {})
    replaced = []
    old_keys = matching_cases(root, run_id, case_key)
    for key in old_keys:
        old_info = previous[key].get('__INFO__', {})
        replaced.append(str(key))
        replaced.extend(str(value) for value in old_info.get('replaced_case_keys', []))
    # Build off-tree, preserving all other scan axes. Replacing the whole case
    # here used to discard N_THETA as soon as N_ENERGY was collected.
    destination = combine_cases([previous[key] for key in old_keys], OMFITtree)

    task_rows = OMFITtree()
    if source_case is not None:
        task_rows.update(copy.deepcopy(source_case['__TASKS__']))
    for point_id in manifest['loaded_points']:
        metadata = copy.deepcopy(manifest.get('point_table', {}).get(point_id, {}))
        row = OMFITtree()
        row.update(dict(task_id=point_id, runid=run_id, case_id=case_key,
                        source_nr=manifest['nr'], rho=manifest.get('rho', None),
                        ion_case=manifest['mass'], status='loaded'))
        row.update(metadata)
        row['result_path'] = result_path(manifest, point_id)
        row['result_workDir'] = manifest.get('point_workdirs', {}).get(point_id, manifest['workDir'])
        row['run_token'] = manifest['run_token']
        task_rows[point_id] = row
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
                     status='published'))
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
    if 'RUN_DB' not in root:
        root['RUN_DB'] = OMFITtree()
    if run_id not in root['RUN_DB']:
        root['RUN_DB'][run_id] = OMFITtree()
    run = root['RUN_DB'][run_id]
    run[case_key] = destination
    for key in old_keys:
        if key != case_key:
            del run[key]
    # OUTPUTScan is the latest scan only; RUN_DB contains all retained axes.
    root['OUTPUTScan'] = fresh_output
    root['RUN_MANIFEST']['case_id'] = case_key
    root['RUN_MANIFEST']['status'] = 'published'
    if 'RUN_HISTORY' not in root:
        root['RUN_HISTORY'] = OMFITtree()
    history = root['RUN_HISTORY'].setdefault(manifest['run_token'], OMFITtree())
    archived_manifest = copy.deepcopy(root['RUN_MANIFEST'])
    archived_manifest.pop('point_table', None)
    history['manifest'] = archived_manifest


if wait_for_completion:
    publish_loaded_run(root)
