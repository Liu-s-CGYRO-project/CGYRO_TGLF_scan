"""Prepare immutable point inputs, submit one case, then optionally wait.

The project orchestrator calls this once per rho/isotope case. Point IDs keep
their original array indices so failed subsets can be retried independently.
"""
from builtins import (Exception, OSError, RuntimeError, TypeError, ValueError, all, any, bool, dict, enumerate, float,
                      int, isinstance, iter, len, list, max, print, range, set, sorted, str, sum, tuple, zip)
import numpy as np
import copy
import hashlib
import itertools
import json
import os
import posixpath
import re
import uuid
import zipfile
from OMFITlib_cgyro_read import num2str_xj
from OMFITlib_cgyro_parameters import (FIELDS as CALCULATION_FIELDS, apply_parameters, initialize_parameters,
                                      parameter_value, validate_zeff)
from OMFITlib_cgyro_scan_values import AXIS_KEYS, ky_values, scan_axes as resolved_scan_axes
from OMFITlib_cgyro_run_state import quote as shell_quote, refresh_run_state, submission_pending, text_output as output_to_text
from OMFITlib_cgyro_queue import advancing_batch, collection_done, pending_runs, save_current, wait_current
from OMFITlib_cgyro_retry import execute_submission, retry_limit
from OMFITlib_cgyro_continue import archived_case, continuation_plan, point_result, prepare_point, restart_files
from OMFITlib_cgyro_storage import compact_storage, result_view
from OMFITlib_cgyro_db import run_cases, set_run_cases
from OMFITlib_cgyro_scratch import check_start_capacity, clean_stage, directory_bytes, ensure_capacity
from OMFITlib_cgyro_launch import (launch_spec, slurm_guard, slurm_process_limits,
                                  validate_checkpoint_runtime)

if not os.environ.get('SHELL'):
    os.environ['SHELL'] = '/bin/bash'


def cfg_get(node, key, default=None):
    try:
        if key in node.keys():
            return node[key]
    except Exception:
        pass
    return default


def cfg_str(node, key, default=''):
    value = cfg_get(node, key, default)
    if value is None:
        return default
    return str(value)


def config_error(message):
    try:
        raise OMFITexception(message)
    except NameError:
        raise ValueError(message)


def selected_remote_config(rmt_setup):
    server_picker = cfg_str(rmt_setup, 'serverPicker', '')
    if server_picker == '':
        config_error("SETTINGS['REMOTE_SETUP']['serverPicker'] must be set")
    try:
        if server_picker in rmt_setup.keys():
            return rmt_setup[server_picker]
    except Exception:
        pass
    config_error("Missing SETTINGS['REMOTE_SETUP']['%s'] configuration" % server_picker)


def required_cfg(node, key):
    value = cfg_get(node, key, None)
    if value in [None, '']:
        config_error("Missing SETTINGS['REMOTE_SETUP'][serverPicker]['%s']" % key)
    return value


def required_cfg_int(node, key):
    return int(required_cfg(node, key))



def script_fragment(value):
    lines = str(value).replace('\r\n', '\n').replace('\r', '\n').split('\n')
    while lines and lines[0].strip() == '':
        lines.pop(0)
    if lines and lines[0].startswith('#!'):
        lines.pop(0)
    return '\n'.join(lines).strip() + '\n'


def setup_workdir(default='.'):
    try:
        value = cfg_get(setup, 'workDir', None)
        if value not in [None, '']:
            return str(value)
    except Exception:
        pass
    try:
        return str(OMFITworkDir(root, ''))
    except Exception:
        return default


def path_join(dirname, filename):
    dirname = str(dirname)
    if dirname.endswith('/') or dirname.endswith('\\'):
        return dirname + filename
    if dirname.startswith('/'):
        return dirname + '/' + filename
    return os.path.join(dirname, filename)


def path_basename(path):
    return str(path).replace('\\', '/').rstrip('/').split('/')[-1]


def runtime_abs_path(path):
    path = str(path)
    if path.startswith('/') or (len(path) > 2 and path[1] == ':' and path[2] in ['/', '\\']):
        return path
    return os.path.abspath(path)


defaultVars(scan_dimensions=1, wait_for_completion=True, batch_id='', continuation=None, check_temp_start=True)


def json_scalar(value):
    return value.item() if isinstance(value, np.generic) else value


def configured_axes(physics, dimensions, source):
    """Return 0-3 Cartesian axes, including any legacy linked parameters."""
    resolved = resolved_scan_axes(physics, dimensions, source)
    conf, axes = {}, []
    for (pkey, rkey), axis in zip(AXIS_KEYS[dimensions], resolved):
        conf[pkey], conf[rkey] = axis['name'], axis['values']
        axes.append((axis['name'], axis['values'], pkey, rkey))
        for index, linked in enumerate(axis['linked'], 2):
            conf[pkey + str(index)] = linked['name']
            conf[rkey + str(index)] = linked['values']
    return conf, axes


def scan_points(physics, dimensions, effnum, source):
    """Return flat point IDs, overrides, result paths and an axis manifest."""
    conf, axes = configured_axes(physics, dimensions, source)
    scan_ky = ky_values(physics)
    points, axis_manifest, result_keys = [], [], set()
    fixed = {}
    if dimensions == 0:
        # Retain a real, unchanged input coordinate for legacy plotting views.
        # It is not an override or a scan axis: only KY is varied in this mode.
        reference = 'BETAE_UNIT' if 'BETAE_UNIT' in source else 'RMIN'
        fixed[reference] = json_scalar(source[reference])
        axis_manifest.append(dict(name=reference, values=[fixed[reference]], fixed=True))
    names = []
    for parameter, values, pkey, rkey in axes:
        if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', str(parameter)) or str(parameter).upper() == 'KY':
            raise ValueError('Invalid scan parameter: %s' % parameter)
        if str(parameter) in names:
            raise ValueError('Duplicate scan parameter: %s' % parameter)
        names.append(str(parameter))
        if str(parameter) not in source:
            raise ValueError('input.cgyro does not contain scan parameter: ' + str(parameter))
        if len(values) == 0:
            raise ValueError('Empty scan axis: %s' % parameter)
        for value in values:
            try:
                finite = np.isfinite(float(value))
            except (TypeError, ValueError, OverflowError):
                finite = False
            if not finite:
                raise ValueError('Non-finite scan value for %s' % parameter)
        linked = []
        n = 2
        while pkey + str(n) in conf or rkey + str(n) in conf:
            if pkey + str(n) not in conf or rkey + str(n) not in conf:
                raise ValueError('Incomplete linked scan axis %s%d' % (pkey, n))
            if len(conf[rkey + str(n)]) != len(values):
                raise ValueError('Linked scan range length differs from primary axis')
            linked_name = str(conf[pkey + str(n)])
            if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', linked_name) or linked_name.upper() == 'KY':
                raise ValueError('Invalid linked scan parameter: %s' % linked_name)
            if linked_name in names or any(item['name'] == linked_name for item in linked):
                raise ValueError('Duplicate linked scan parameter: %s' % linked_name)
            if linked_name not in source or not all(np.isfinite(float(value)) for value in conf[rkey + str(n)]):
                raise ValueError('Invalid linked scan parameter or values: ' + linked_name)
            linked.append(dict(name=linked_name,
                               values=[json_scalar(value) for value in conf[rkey + str(n)]]))
            names.append(linked_name)
            n += 1
        axis_manifest.append(dict(name=str(parameter), values=[json_scalar(value) for value in values],
                                  linked=linked))
    combinations = itertools.product(*[list(enumerate(axis[1])) for axis in axes])
    for combination in combinations:
        overrides = {}
        result_path = [reference, num2str_xj(fixed[reference], effnum)] if dimensions == 0 else []
        for (parameter, values, pkey, rkey), (index, value) in zip(axes, combination):
            overrides[parameter] = value
            result_path.extend([str(parameter), num2str_xj(value, effnum)])
            n = 2
            while pkey + str(n) in conf or rkey + str(n) in conf:
                overrides[conf[pkey + str(n)]] = conf[rkey + str(n)][index]
                n += 1
        for ky in scan_ky:
            if not np.isfinite(ky) or ky <= 0:
                raise ValueError('Linear scan ky must be finite and positive')
            point = dict(overrides, KY=ky)
            point_id = 'p{:06d}'.format(len(points) + 1)
            stored_path = result_path + ['lin', num2str_xj(ky, effnum)]
            result_key = tuple(stored_path)
            if result_key in result_keys:
                raise ValueError('Scan values collide at effnum=%s; increase effnum or separate the values' % effnum)
            result_keys.add(result_key)
            metadata = dict(values=dict(fixed, **{str(key): json_scalar(value) for key, value in point.items()}),
                            result_path=stored_path)
            points.append((point_id, point, metadata))
    if not points:
        raise ValueError('Empty scan')
    return points, axis_manifest


def validate_restart_input(previous, current):
    # Changing the layout or physics invalidates a binary restart. Deliberately
    # permit only run duration and output cadence until other changes are verified.
    allowed = {'MAX_TIME', 'PRINT_STEP', 'rho'}  # Ignore removed legacy radius metadata.
    changed = [key for key in set(previous.keys()) | set(current.keys())
               if key not in allowed and (key not in previous or key not in current
                   or not np.array_equal(previous[key], current[key]))]
    if changed:
        raise ValueError('Restart input is incompatible (%s); use restart_mode=0' % ', '.join(sorted(changed)))


physics = root['SETTINGS']['PHYSICS']
setup = root['SETTINGS']['SETUP']
retry_limit(root)
rmt_setup = root['SETTINGS']['REMOTE_SETUP']
server_setup = selected_remote_config(rmt_setup)
local_submit = cfg_str(rmt_setup, 'serverPicker', '') == 'localhost'
# Resolve the launch before copying point/checkpoint data. Slurm array elements
# each own this full allocation; a saved literal -n must never underfill it.
execution = (launch_spec(server_setup, setup)
             if cfg_str(server_setup, 'scheduler', '').lower() in ('slurm', 'local') else None)
if continuation:
    # Re-resolve the dialog's frozen identity before reading or changing state.
    continuation = continuation_plan(root, continuation['source_token'],
        continuation['points'], continuation['additional_time'])
    scan_dimensions = int(continuation['info'].get('scan_dimensions', continuation['info']['dimensions']))
caseName = continuation['case_tag'] if continuation else physics['case_tag']
base_workdir = runtime_abs_path(setup_workdir())
if check_temp_start:
    print('[CGYRO] Checking existing temporary usage once (100 GiB start limit).', flush=True)
    space = check_start_capacity(base_workdir)
    print('[CGYRO] Start check passed; preparing inputs. Later peaks above 100 GiB are allowed.', flush=True)
print('[CGYRO] Checking saved result/input references before preparing this case.', flush=True)
compact_storage(root, OMFITtree)
previous_cases = result_view(root, run_cases(root))
restart_mode = 0 if continuation else int(physics['restart_mode'])
if restart_mode not in (0, 1):
    raise ValueError('restart_mode must be 0 or 1')
if restart_mode == 1 and not previous_cases:
    # Completed points are owned by the public scan, not a lingering Cases copy.
    _, _, archived = archived_case(root, root.get('RUN_MANIFEST', {}).get('run_token', ''))
    previous_cases = {point: point_result(archived, row) for point, row in archived['__TASKS__'].items()}
previous_manifest = root.get('RUN_MANIFEST', {})
if submission_pending(previous_manifest):
    raise ValueError('The previous submission is unconfirmed. Synchronize its saved submission log before submitting again.')
if not batch_id and pending_runs(root):
    raise ValueError('The queued CGYRO batch still needs synchronization or collection before another run.')
previous_status = previous_manifest.get('status', None)
previous_failed = previous_status in ('failed', 'cancelled') or (
    previous_status == 'submitted_or_finished' and bool(previous_manifest.get('failed_points', [])))
if previous_manifest and not collection_done(previous_manifest) and not previous_failed and not advancing_batch(root, batch_id):
    # A killed local wait does not update a remote job's final status. Query the
    # saved run, rather than treating the stale local flag as a live allocation.
    refresh_run_state(root, OMFITx)
    previous_status = previous_manifest.get('status', None)
    previous_failed = previous_status in ('failed', 'cancelled')
    if not collection_done(previous_manifest) and not previous_failed:
        raise ValueError('The previous CGYRO run is still active, needs collection, or has an unconfirmed scheduler state. '
                         'Synchronize its job status or collect its results before starting another run.')
if restart_mode and not previous_cases:
    raise ValueError('No saved cases are available for restart')
run_token = uuid.uuid4().hex
case_id = (str(continuation['source_case_id']) if continuation else
           str(physics.get('case_id', '') or 'nr={}__ion={}'.format(physics['nr'], physics['mass'])))
if not wait_for_completion:
    queued_batch = root.get('RUN_BATCH', {})
    if (local_submit or not batch_id or queued_batch.get('batch_id', '') != batch_id
            or queued_batch.get('status', '') != 'submitting' or queued_batch.get('stop_requested', False)
            or case_id not in queued_batch.get('case_ids', [])):
        raise ValueError('Deferred waiting requires an unstopped case in this recorded remote batch.')
relative_run_dir = os.path.join('runs', run_token)
submit_workdir = os.path.join(base_workdir, relative_run_dir)
os.makedirs(submit_workdir)
remote_server = 'localhost' if local_submit else cfg_str(server_setup, 'server', cfg_str(rmt_setup, 'server', ''))
remote_tunnel = '' if local_submit else cfg_str(server_setup, 'tunnel', cfg_str(rmt_setup, 'tunnel', ''))
remote_base = cfg_str(server_setup, 'workDir', cfg_str(rmt_setup, 'workDir', ''))
if not local_submit and (not remote_server or not remote_base):
    raise ValueError('Selected server requires server and workDir')
if not local_submit and 'server' not in server_setup and remote_server.split('@')[-1] != cfg_str(rmt_setup, 'serverPicker'):
    raise ValueError('Selected server differs from the old endpoint; set server in the selected server configuration')
remote_workdir = submit_workdir if local_submit else posixpath.join(remote_base, 'runs', run_token)
runtime = {key: cfg_get(server_setup, key, None) for key in
           ('environment', 'executable', 'nodes', 'ntasks_per_node', 'ppn', 'cpus_per_task')}
if execution is not None:
    runtime.update(dict(executable=execution['executable'], mpi_ranks=execution['mpi_ranks'],
                        cpus_per_task=execution['threads']))
if continuation:
    if continuation['server'] and continuation['server'] != remote_server:
        raise ValueError('Continuation requires the original server: ' + str(continuation['server']))
    has_checkpoint = any(origin['mode'] == 'checkpoint' for origin in continuation['sources'].values())
    validate_checkpoint_runtime(continuation['runtime'], runtime, has_checkpoint=has_checkpoint)
elif restart_mode:
    validate_checkpoint_runtime(previous_manifest.get('runtime', {}), runtime)
inputs_node = root['INPUTS']
if continuation:
    first_point = continuation['points'][0]
    first_stage = os.path.join(submit_workdir, 'staging', first_point)
    os.makedirs(os.path.dirname(first_stage), exist_ok=True)
    first_prepared = prepare_point(root, continuation, first_point, first_stage, OMFITgacode)
    base_input = first_prepared[0].duplicate()
else:
    base_input = inputs_node['input.cgyro'].duplicate()
prescribed_zeff = float(base_input.get('Z_EFF_METHOD', 2)) == 1
source_rho = continuation['info'].get('rho', None) if continuation else physics.get('rho', None)
if source_rho is None:
    source_rho = base_input.get('rho', None)
if 'rho' in base_input:
    del base_input['rho']  # Old projects may still carry this non-solver metadata.
if continuation:
    fixed_parameters = copy.deepcopy(continuation['info'].get('fixed_parameters', {}))
    scan_axes = copy.deepcopy(continuation['info']['scan_axes'])
    points = [(point, {}, copy.deepcopy(continuation['rows'][point])) for point in continuation['points']]
else:
    initialize_parameters(physics, base_input, OMFITtree)
    fixed_parameters = apply_parameters(base_input, physics, scan_dimensions)
    base_input['NONLINEAR_FLAG'] = 0
    points, scan_axes = scan_points(physics, scan_dimensions, setup['effnum'], base_input)
input_names = ['input.cgyro']
if base_input.get('PROFILE_MODEL', 1) == 2:
    input_names += ['input.profiles', 'input.profiles.geo']
for name in input_names[1:]:
    if not continuation and name not in inputs_node:
        raise ValueError('Required profile input is missing: ' + name)
prepared_cases = OMFITtree()
inputs = []
dir_list = []
input_checksums = {}
point_table = {}
for point_number, (new_dir, overrides, point_metadata) in enumerate(points, 1):
    if point_number == 1 or point_number % 10 == 0 or point_number == len(points):
        print('[CGYRO] Preparing input {}/{}: {} ({})'.format(
            point_number, len(points), new_dir, case_id), flush=True)
    stage = os.path.join(submit_workdir, 'staging', new_dir)
    # OMFITobject.deploy(existing_dir) appends its original basename. Supply a
    # nonexistent destination when copying a result directory (framework API).
    os.makedirs(os.path.dirname(stage), exist_ok=True)
    current_input = base_input.duplicate()
    for name, value in overrides.items():
        current_input[name] = parameter_value(name, value) if name in CALCULATION_FIELDS else value
    if not continuation:
        validate_zeff(current_input, set(fixed_parameters) | set(overrides), prescribed=prescribed_zeff)
    if not continuation and physics['scale_time_with_ky'] and overrides['KY'] > 1:
        current_input['DELTA_T'] = current_input['DELTA_T'] / overrides['KY']
        current_input['MAX_TIME'] = current_input['MAX_TIME'] / overrides['KY']
    point_metadata['effective_time'] = {
        name: json_scalar(current_input[name]) for name in ('DELTA_T', 'MAX_TIME', 'PRINT_STEP') if name in current_input}
    packed_names = list(input_names)
    if continuation:
        if new_dir == first_point:
            current_input, point_metadata, packed_names = first_prepared
        else:
            current_input, point_metadata, packed_names = prepare_point(
                root, continuation, new_dir, stage, OMFITgacode)
    elif restart_mode:
        if new_dir not in previous_cases:
            raise ValueError('Restart point missing: %s; use a fresh run for new points' % new_dir)
        ensure_capacity(stage, directory_bytes(previous_cases[new_dir].filename))
        previous_cases[new_dir].deploy(stage)
        old_input_path = os.path.join(stage, 'input.cgyro')
        if not os.path.isfile(old_input_path):
            raise ValueError('Restart lacks input.cgyro: ' + new_dir)
        validate_restart_input(OMFITgacode(old_input_path), current_input)
        packed_names = restart_files(stage, current_input)
    os.makedirs(stage, exist_ok=True)
    size_inputs = [current_input] + ([] if continuation else [inputs_node[name] for name in input_names[1:]])
    ensure_capacity(stage, sum(os.path.getsize(node.filename) for node in size_inputs if os.path.isfile(node.filename)))
    current_input.deploy(os.path.join(stage, 'input.cgyro'))
    for name in input_names[1:]:
        if not continuation:
            inputs_node[name].duplicate().deploy(os.path.join(stage, name))
    prepared = OMFITtree()
    zip_path = os.path.join(submit_workdir, new_dir + '.zip')
    ensure_capacity(zip_path, sum(os.path.getsize(os.path.join(stage, name)) for name in packed_names) + 1048576)
    checksums = {}
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in packed_names:
            path = os.path.join(stage, name)
            if not os.path.isfile(path):
                raise ValueError('Prepared input is missing: ' + path)
            with open(path, 'rb') as handle:
                digest = hashlib.sha256()
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
                checksums[name] = digest.hexdigest()
            archive.write(path, name)
            # The ZIP is the immutable submission input. Keeping each expanded
            # restart here as well used to multiply large files in history.
    prepared['zip'] = OMFITpath(zip_path)
    prepared_cases[new_dir] = prepared
    inputs.append(prepared['zip'])
    dir_list.append(new_dir)
    input_checksums[new_dir] = checksums
    point_table[new_dir] = point_metadata
    # The ZIP and its checksums replace the reproducible expanded checkpoint.
    # Never remove a path still used by the base input reader.
    try:
        clean_stage(submit_workdir, run_token, new_dir, zip_path, checksums,
                    protected=[base_input.filename])
    except (OSError, ValueError) as exc:
        print('Staging retained: ' + str(exc))

manifest = {'run_token': run_token, 'case_tag': caseName, 'dimensions': max(1, scan_dimensions),
            'scan_dimensions': scan_dimensions,
            'points': dir_list, 'server': remote_server, 'tunnel': remote_tunnel,
            'workDir': remote_workdir, 'local_workDir': submit_workdir,
            'serverPicker': cfg_str(rmt_setup, 'serverPicker'),
            'runid': root['SETTINGS']['EXPERIMENT']['runid'], 'nr': physics['nr'],
            'rho': source_rho, 'mass': physics['mass'], 'case_id': case_id,
            'scan_axes': scan_axes, 'point_table': point_table,
            'fixed_parameters': fixed_parameters,
            'numeric_parameters': {name: json_scalar(base_input[name]) for name in CALCULATION_FIELDS if name in base_input},
            'scale_time_with_ky': bool(physics['scale_time_with_ky']),
            'input_sha256': input_checksums, 'status': 'prepared', 'batch_id': batch_id}
manifest['runtime'] = runtime
if execution is not None:
    manifest['launch'] = {key: execution[key] for key in
                          ('nodes', 'mpi_per_node', 'mpi_ranks', 'threads', 'total_cpus', 'executable')}
if continuation:
    source_info = continuation['info']
    manifest.update(dict(runid=continuation['source_runid'], nr=source_info['source_nr'],
                         mass=source_info['ion_case'],
                         numeric_parameters=copy.deepcopy(source_info.get('numeric_parameters', {})),
                         scale_time_with_ky=source_info.get('scale_time_with_ky', False),
                         continuation={key: copy.deepcopy(continuation[key]) for key in
                             ('source_token', 'source_runid', 'source_case_id', 'additional_time', 'points',
                              'stopped_run', 'source_points')}))
environment=script_fragment(required_cfg(server_setup, 'environment'))
executable=script_fragment(required_cfg(server_setup, 'executable')).strip()
if execution is not None:
    executable = execution['executable']
scheduler=cfg_str(server_setup, 'scheduler', '').lower()
if scheduler not in ['local', 'pbs', 'slurm']:
    config_error('Selected scheduler must be local, pbs, or slurm')
if local_submit != (scheduler == 'local'):
    config_error('localhost and local scheduler must be selected together')
cpus_per_task = int(cfg_get(server_setup, 'cpus_per_task', cfg_get(setup, 'cpus_per_task', 1)))
if cpus_per_task < 1:
    config_error('cpus_per_task must be a positive integer')
manifest['scheduler'] = scheduler
manifest['cpus_per_task'] = cpus_per_task
pbs_file=os.path.join(submit_workdir, 'scan.pbs')
ps_name='cgyro'
dirlist_num=len(dir_list)
if local_submit:
    bash_head = \
    r'#!/bin/bash '+'\n'+ \
    r'set -e'+'\n'+ \
    r'unset LD_LIBRARY_PATH'+'\n'+ \
    r'unset CONDA_PREFIX'+'\n'+ \
    r'unset CONDA_DEFAULT_ENV'+'\n'+ \
    r'export LC_ALL=C'+'\n'+ \
    r'export LANG=C'+'\n'+ \
    r'cd "$(dirname "$0")"'+'\n'+ \
    r'pwd'+'\n'+ \
    environment
else:
    if scheduler == 'slurm':
        num_nodes=required_cfg_int(server_setup, 'nodes')
        ntasks_per_node=required_cfg_int(server_setup, 'ntasks_per_node')
        array_parallel=required_cfg_int(server_setup, 'array_parallel')
        bash_head= \
        r'#!/bin/bash '+'\n' + \
        r'#SBATCH -p '+str(required_cfg(server_setup, 'queue')) +'\n' +\
        r'#SBATCH -J '+ps_name +'\n' +\
        r'#SBATCH -t '+str(required_cfg(server_setup, 'w')) +'\n' +\
        r'#SBATCH -o %A_%a.out'+'\n' +\
        r'#SBATCH -e %A_%a.err'+'\n' +\
        r'#SBATCH --nodes='+str(num_nodes)+'\n' +\
        r'#SBATCH --ntasks='+str(execution['mpi_ranks']) +'\n' +\
        r'#SBATCH --ntasks-per-node='+str(ntasks_per_node) +'\n' +\
        r'#SBATCH --cpus-per-task='+str(cpus_per_task) +'\n' +\
        r'#SBATCH --array=0-'+str(dirlist_num-1)+'%'+str(array_parallel)+'\n' +\
        r'set -e'+'\n' +\
        slurm_process_limits() +\
        environment
    else:
        bash_head= \
        r'#!/bin/bash '+'\n'+ \
        r'#PBS -N '+ps_name +'\n'+ \
        r'#PBS -l nodes='+str(required_cfg(server_setup, 'nodes'))+':ppn='+str(required_cfg(server_setup, 'ppn')) +'\n'+ \
        r'#PBS -j oe' +'\n'+ \
        r'#PBS -l walltime='+str(required_cfg(server_setup, 'w')) +'\n'+ \
        r'#PBS -q '+str(required_cfg(server_setup, 'queue')) +'\n'+ \
        r'cd ${PBS_O_WORKDIR}' +'\n'+ \
        r'pwd'  +'\n'+ \
        r'NP=`cat ${PBS_NODEFILE}|wc -l`' +'\n'+ \
        '\n'+ \
        r'JOBID_FILE="JOBID_${PBS_JOBID}"' +'\n'+ \
        r'touch ${JOBID_FILE}' +'\n'+ \
        environment
bash_helpers = r"""
set -e
prepare_case_dir() {
  local current_dir="$1"
  case "$current_dir" in *[!A-Za-z0-9_.~+-]*|"") echo "Invalid case name" >&2; return 1;; esac
  if [ -e "$current_dir" ]; then
    echo "Refusing to overwrite an existing run directory: $current_dir" >&2
    return 1
  fi
  mkdir -- "$current_dir"
  unzip -o "$current_dir.zip" -d "$current_dir"
  cd "$current_dir"
  test -s input.cgyro
}
"""
bash_helpers += ('\nexport OMP_NUM_THREADS=' + str(cpus_per_task)
                 + '\nexport OMP_THREAD_LIMIT=' + str(cpus_per_task) + '\nexport OMP_DYNAMIC=false\n')
if scheduler == 'slurm':
    bash_helpers += slurm_guard(execution)
bash_helpers += r"""
run_case() (
  set -e
  prepare_case_dir "$1"
  trap 'status=$?; printf "%s\n" "$status" > cgyro.exit' EXIT
""" + executable + r""" > run_log 2>&1
  if [ -s out.cgyro.info ] && grep -q -E '^[[:space:]]*ERROR:' out.cgyro.info; then
    grep -E '^[[:space:]]*ERROR:' out.cgyro.info >&2
    exit 1
  fi
  for output in out.cgyro.grids out.cgyro.time; do
    [ -s "$output" ] || { echo "CGYRO did not generate $output; see run_log." >&2; exit 1; }
  done
)
"""

# Slurm owns array concurrency. PBS waits for this script's child PIDs only.
if local_submit:
    bash_content= \
    r'dir_list=('+' '.join(dir_list)+')' +'\n'+ \
    r'for current_dir in ${dir_list[@]}; do'+'\n'+\
    r'  run_case "${current_dir}"'+'\n'+\
    r'done'+'\n'
else:
    if scheduler == 'slurm':
        bash_content= \
        r'dir_list=('+' '.join(dir_list)+')' +'\n'+ \
        r'current_dir=${dir_list[$SLURM_ARRAY_TASK_ID]}' +'\n'+ \
        r'run_case "${current_dir}"'+'\n'
    else:
        parallel = required_cfg_int(server_setup, 'n')
        if parallel < 1:
            config_error('PBS concurrent point count n must be positive')
        # Counting process names can miss a child before launch or match a
        # different isotope allocation. Wait for every owned child explicitly.
        bash_content = ('dir_list=(' + ' '.join(dir_list) + ')\n'
                        + 'parallel=' + str(parallel) + '\n' + r"""
pids=()
result=0
for current_dir in "${dir_list[@]}"; do
  run_case "$current_dir" &
  pids+=("$!")
  if [ "${#pids[@]}" -ge "$parallel" ]; then
    wait "${pids[0]}" || result=1
    pids=("${pids[@]:1}")
  fi
done
for pid in "${pids[@]}"; do
  wait "$pid" || result=1
done
rm -- "$JOBID_FILE"
exit "$result"
""")


with open(pbs_file,'w') as f1:
    f1.write(bash_head+'\n'+bash_helpers+'\n'+bash_content)
with open(pbs_file, 'rb') as handle:
    manifest['submit_script_sha256'] = hashlib.sha256(handle.read()).hexdigest()
pbs_name = path_basename(pbs_file)
prepared_cases[pbs_name] = OMFITascii(pbs_file)
inputs.append(prepared_cases[pbs_name])
with open(os.path.join(submit_workdir, 'manifest.json'), 'w') as handle:
    json.dump(manifest, handle, indent=2)

# Commit the prepared run only after every point passes validation and packaging.
if previous_manifest or previous_cases:
    history_key = root.get('RUN_MANIFEST', {}).get('run_token', 'imported-' + run_token)
    if 'RUN_HISTORY' not in root:
        root['RUN_HISTORY'] = OMFITtree()
    if history_key not in root['RUN_HISTORY']:
        root['RUN_HISTORY'][history_key] = OMFITtree()
    archived_manifest = copy.deepcopy(previous_manifest)
    if previous_status == 'published':
        archived_manifest.pop('point_table', None)  # Permanent task rows live once in RUN_DB.
        root['RUN_HISTORY'][history_key].pop('cases', None)
    elif previous_failed or not previous_manifest:
        old_tag = previous_manifest.get('case_tag', caseName)
        set_run_cases(root, previous_manifest, run_cases(root, previous_manifest), OMFITtree)
    root['RUN_HISTORY'][history_key]['manifest'] = archived_manifest
if not batch_id:
    root['RUN_BATCH'] = OMFITtree()
run_manifest = OMFITtree()
run_manifest.update(manifest)
root['RUN_MANIFEST'] = run_manifest
set_run_cases(root, run_manifest, prepared_cases, OMFITtree)
print('[CGYRO] Saving {} prepared input ZIPs and original point table.'.format(len(points)), flush=True)
save_current(root, OMFITtree)
print('[CGYRO] Local preparation complete: {} points. Run directory: {}'.format(len(points), submit_workdir), flush=True)
if setup['irun']==1:
    # sub jobs
    # Submit through scheduler directly and let OMFIT wait for job completion.
    # We first capture submission output, parse jobID, then follow jobID-specific logs.
    if local_submit:
        rmt_setup['localResultsDir'] = submit_workdir
        submit_out=[]
        submit_err=[]
        ret_code=OMFITx.executable(root, inputs=inputs, outputs=[],  \
                                   server='localhost', \
                                   tunnel='', \
                                   workdir=submit_workdir,\
                                   remotedir=submit_workdir,\
                                   executable='/usr/bin/env -u LD_LIBRARY_PATH -u CONDA_PREFIX -u CONDA_DEFAULT_ENV LC_ALL=C LANG=C /bin/bash scan.pbs',clean=False,std_out=submit_out,std_err=submit_err,ignoreReturnCode=True)
        if ret_code != 0:
            root['RUN_MANIFEST']['status'] = 'failed'
            raise RuntimeError('CGYRO local execution failed: ' + output_to_text(submit_out + submit_err))
    else:
        submit_cmd='sbatch scan.pbs'
        if scheduler == 'pbs':
            submit_cmd='qsub scan.pbs'
        print('[CGYRO] Uploading inputs to {}; then submitting {}.'.format(remote_server, scheduler), flush=True)
        execute_submission(root, OMFITx, OMFITtree, OMFITascii, inputs, submit_workdir, submit_cmd)
        print('[CGYRO] Recorded job ID: {} (state: {}).'.format(
            root['RUN_MANIFEST'].get('job_id', ''), root['RUN_MANIFEST'].get('status', '')), flush=True)
        if wait_for_completion:
            wait_current(root, OMFITx, OMFITtree)

    if (wait_for_completion and not root['RUN_MANIFEST'].get('stop_requested', False)
            and root['RUN_MANIFEST'].get('status', '') not in ('cancelled', 'failed')):
        root['RUN_MANIFEST']['status'] = 'submitted_or_finished'
