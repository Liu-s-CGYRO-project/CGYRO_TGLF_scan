# Run and collect a 1D, 2D, or 3D CGYRO parameter scan.
import copy

setup = root['SETTINGS']['SETUP']
if setup['icgyro'] != 1:
    raise RuntimeError('Legacy GYRO submission is unavailable in this repaired CGYRO package')
dimensions = int(setup['idimrun'])
if dimensions not in (1, 2, 3):
    raise ValueError('CGYRO parameter-axis count must be 1, 2, or 3')

if setup['irun'] == 1:
    root['SCRIPTS']['subscan_lin.py'].run(scan_dimensions=dimensions)
if setup['idownsync'] == 1:
    root['SCRIPTS']['downsync.py'].run()


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
    case_tag = manifest['case_tag']
    fresh_output = OMFITtree()
    for point_id in manifest['loaded_points']:
        path = result_path(manifest, point_id)
        node = fresh_output
        for key in path[:-1]:
            if key not in node:
                node[key] = OMFITtree()
            node = node[key]
        node[path[-1]] = copy.deepcopy(root['Cases'][case_tag][point_id])

    # OUTPUTScan remains the plotting view of the most recently collected case.
    root['OUTPUTScan'] = fresh_output
    run_id = str(manifest['runid'])
    legacy = 'case_id' not in manifest
    base_case_key = ('nr=' + str(manifest['nr']) if legacy else str(manifest['case_id']))
    if run_id not in root['RUN_DB']:
        root['RUN_DB'][run_id] = OMFITtree()
    # A collected run is immutable. Repeating the same input case creates a
    # revision key instead of relabelling or partly overwriting old data.
    case_key = base_case_key
    if case_key in root['RUN_DB'][run_id]:
        case_key = base_case_key + '__run=' + str(manifest['run_token'])[:8]
    root['RUN_DB'][run_id][case_key] = OMFITtree()
    destination = root['RUN_DB'][run_id][case_key]
    for parameter in fresh_output:
        # Older records encoded the ion case in the parameter key. New records
        # encode it once in case_id, keeping parameter names physically accurate.
        key = parameter + '_' + str(manifest['mass']) if legacy else parameter
        destination[key] = copy.deepcopy(fresh_output[parameter])

    task_rows = OMFITtree()
    for point_id in manifest['loaded_points']:
        metadata = copy.deepcopy(manifest.get('point_table', {}).get(point_id, {}))
        row = OMFITtree()
        row.update(dict(task_id=point_id, runid=run_id, case_id=case_key,
                        source_nr=manifest['nr'], rho=manifest.get('rho', None),
                        ion_case=manifest['mass'], status='loaded'))
        row.update(metadata)
        row['result_path'] = result_path(manifest, point_id)
        task_rows[point_id] = row
    info = OMFITtree()
    info.update(dict(run_token=manifest['run_token'], runid=run_id, case_id=case_key,
                     source_nr=manifest['nr'], rho=manifest.get('rho', None),
                     ion_case=manifest['mass'], dimensions=manifest['dimensions'],
                     scan_axes=copy.deepcopy(manifest.get('scan_axes', [])),
                     parameters=list(fresh_output.keys()), points=len(manifest['loaded_points']),
                     workDir=manifest['workDir'], job_id=manifest.get('job_id', None),
                     status='published'))
    # Keep the task table with the results.  Reserved double-underscore keys are
    # hidden by the comparison selectors, while remaining directly inspectable
    # in the OMFIT data tree.
    destination['__INFO__'] = info
    destination['__TASKS__'] = task_rows
    root['RUN_MANIFEST']['status'] = 'published'
    if 'RUN_HISTORY' not in root:
        root['RUN_HISTORY'] = OMFITtree()
    history = root['RUN_HISTORY'].setdefault(manifest['run_token'], OMFITtree())
    archived_manifest = copy.deepcopy(root['RUN_MANIFEST'])
    archived_manifest.pop('point_table', None)
    history['manifest'] = archived_manifest


publish_loaded_run(root)
