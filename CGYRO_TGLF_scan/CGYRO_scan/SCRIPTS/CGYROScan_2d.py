# this script is used to collect the CGYRO result of 2D scan in a good format
setup=root['SETTINGS']['SETUP']
if setup['icgyro'] != 1:
    raise RuntimeError('Legacy GYRO submission is unavailable in this repaired CGYRO package')
# start to scan
# run
if setup['irun']==1:
    if setup['icgyro']==1:
        root['SCRIPTS']['subscan_lin_2d.py'].run()
    else:
        root['SCRIPTS']['set_resolution.py'].run()
        root['SCRIPTS']['subscan_lin_2d_gyro.py'].run()
# load the results from the remote sever
if setup['idownsync']==1:
    root['SCRIPTS']['downsync.py'].run()
# Publish only the successfully loaded points of this run. Old branches remain
# in RUN_HISTORY; setting changes after submission cannot relabel these results.
def publish_loaded_run(root):
    manifest = root.get('RUN_MANIFEST')
    if not manifest or manifest.get('status') != 'loaded':
        print('No fully loaded run to publish; preserved results are unchanged.')
        return
    if manifest['dimensions'] != 2:
        raise ValueError('Run manifest dimension does not match collector')
    case_tag = manifest['case_tag']
    fresh_output = OMFITtree()
    for item in manifest['loaded_points']:
        parts = item.split('~')
        expected = 4 if 2 == 1 else 6
        if len(parts) != expected:
            raise ValueError('Invalid manifest point: ' + item)
        path = parts[:2] + ['lin', parts[3]] if 2 == 1 else parts[:4] + ['lin', parts[5]]
        node = fresh_output
        for key in path[:-1]:
            if key not in node:
                node[key] = OMFITtree()
            node = node[key]
        node[path[-1]] = copy.deepcopy(root['Cases'][case_tag][item])
    root['OUTPUTScan'] = fresh_output
    run_id = manifest['runid']
    nr_key = 'nr=' + str(manifest['nr'])
    if run_id not in root['RUN_DB']:
        root['RUN_DB'][run_id] = OMFITtree()
    if nr_key not in root['RUN_DB'][run_id]:
        root['RUN_DB'][run_id][nr_key] = OMFITtree()
    for parameter in fresh_output:
        key = parameter + '_' + str(manifest['mass'])
        destination = root['RUN_DB'][run_id][nr_key]
        if key in destination:
            old_key = key + '__previous_' + manifest['run_token']
            destination[old_key] = copy.deepcopy(destination[key])
        destination[key] = copy.deepcopy(fresh_output[parameter])
    root['RUN_MANIFEST']['status'] = 'published'

publish_loaded_run(root)
