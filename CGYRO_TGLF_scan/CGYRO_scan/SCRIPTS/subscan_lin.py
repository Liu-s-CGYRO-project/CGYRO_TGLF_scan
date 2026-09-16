from builtins import (Exception, TypeError, ValueError, any, dict, enumerate, float,
                      int, len, list, range, set, sorted, str, tuple, zip)
import numpy as np
import os
import re
from OMFITlib_cgyro_read import *

if 'SHELL' not in os.environ:
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


def shell_quote(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


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



def output_to_text(value):
    """Convert OMFIT command output containers into plain text."""
    if value is None:
        return ''
    if isinstance(value, (list, tuple)):
        return '\n'.join([output_to_text(item) for item in value])
    return str(value)


def parse_scheduler_job_id(text, rule):
    """Extract scheduler job id from sbatch/qsub output."""
    match = re.search(rule, output_to_text(text))
    if match is None:
        config_error("Could not find scheduler jobID in submit output: %s" % output_to_text(text))
    return match.group(1)
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


# One engine prepares 1-3 parameter axes, with immutable per-run paths.
import copy
import hashlib
import itertools
import json
import tempfile
import uuid
import zipfile
import posixpath
defaultVars(scan_dimensions=1)


def json_scalar(value):
    return value.item() if isinstance(value, np.generic) else value


def configured_axes(physics, dimensions):
    """Return 1-3 Cartesian axes, including any legacy linked parameters."""
    if dimensions == 1:
        conf = physics['1d']
        axes = [(conf['Para'], conf['Range'], 'Para', 'Range')]
    elif dimensions in (2, 3):
        conf = physics[str(dimensions) + 'd']
        suffixes = ('x', 'y') if dimensions == 2 else ('x', 'y', 'z')
        axes = [(conf['Para_' + suffix], conf['Range_' + suffix],
                 'Para_' + suffix, 'Range_' + suffix) for suffix in suffixes]
    else:
        raise ValueError('scan_dimensions must be 1, 2, or 3')
    return conf, axes


def scan_points(physics, dimensions, effnum):
    """Return flat point IDs, overrides, result paths and an axis manifest."""
    conf, axes = configured_axes(physics, dimensions)
    points, axis_manifest, result_keys = [], [], set()
    names = []
    for parameter, values, pkey, rkey in axes:
        if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', str(parameter)) or str(parameter).upper() == 'KY':
            raise ValueError('Invalid scan parameter: %s' % parameter)
        if str(parameter) in names:
            raise ValueError('Duplicate scan parameter: %s' % parameter)
        names.append(str(parameter))
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
            linked.append(dict(name=linked_name,
                               values=[json_scalar(value) for value in conf[rkey + str(n)]]))
            n += 1
        axis_manifest.append(dict(name=str(parameter), values=[json_scalar(value) for value in values],
                                  linked=linked))
    combinations = itertools.product(*[list(enumerate(axis[1])) for axis in axes])
    for combination in combinations:
        overrides = {}
        result_path = []
        for (parameter, values, pkey, rkey), (index, value) in zip(axes, combination):
            overrides[parameter] = value
            result_path.extend([str(parameter), num2str_xj(value, effnum)])
            n = 2
            while pkey + str(n) in conf or rkey + str(n) in conf:
                overrides[conf[pkey + str(n)]] = conf[rkey + str(n)][index]
                n += 1
        for ky in physics['kyarr']:
            if not np.isfinite(ky) or ky <= 0:
                raise ValueError('Linear scan ky must be finite and positive')
            point = dict(overrides, KY=ky)
            point_id = 'p{:06d}'.format(len(points) + 1)
            stored_path = result_path + ['lin', num2str_xj(ky, effnum)]
            result_key = tuple(stored_path)
            if result_key in result_keys:
                raise ValueError('Scan values collide at effnum=%s; increase effnum or separate the values' % effnum)
            result_keys.add(result_key)
            metadata = dict(values={str(key): json_scalar(value) for key, value in point.items()},
                            result_path=stored_path)
            points.append((point_id, point, metadata))
    if not points:
        raise ValueError('Empty scan')
    return points, axis_manifest


def validate_restart_input(previous, current):
    # Changing the layout or physics invalidates a binary restart. Deliberately
    # permit only run duration and output cadence until other changes are verified.
    allowed = {'MAX_TIME', 'PRINT_STEP'}
    changed = [key for key in set(previous.keys()) | set(current.keys())
               if key not in allowed and (key not in previous or key not in current
                   or not np.array_equal(previous[key], current[key]))]
    if changed:
        raise ValueError('Restart input is incompatible (%s); use restart_mode=0' % ', '.join(sorted(changed)))


physics = root['SETTINGS']['PHYSICS']
setup = root['SETTINGS']['SETUP']
rmt_setup = root['SETTINGS']['REMOTE_SETUP']
server_setup = selected_remote_config(rmt_setup)
local_submit = cfg_str(rmt_setup, 'serverPicker', '') == 'localhost'
caseName = physics['case_tag']
caseRoot = root['Cases']
previous_cases = caseRoot.get(caseName, OMFITtree())
restart_mode = int(physics['restart_mode'])
if restart_mode not in (0, 1):
    raise ValueError('restart_mode must be 0 or 1')
previous_manifest = root.get('RUN_MANIFEST', {})
if previous_cases and previous_manifest and previous_manifest.get('status', None) not in ('published',):
    raise ValueError('The previous CGYRO run has not been published; collect it before starting another run')
points, scan_axes = scan_points(physics, scan_dimensions, setup['effnum'])
if restart_mode and not previous_cases:
    raise ValueError('No saved cases are available for restart')
run_token = uuid.uuid4().hex
base_workdir = runtime_abs_path(setup_workdir())
case_id = str(physics.get('case_id', '') or 'nr={}__ion={}'.format(physics['nr'], physics['mass']))
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
inputs_node = root['INPUTS']
base_input = inputs_node['input.cgyro'].duplicate()
base_input['GAMMA_E'] = 0
base_input['NONLINEAR_FLAG'] = 0
input_names = ['input.cgyro']
if base_input.get('PROFILE_MODEL', 1) == 2:
    input_names += ['input.profiles', 'input.profiles.geo']
    base_input['GAMMA_E_SCALE'] = 0.
for name in input_names[1:]:
    if name not in inputs_node:
        raise ValueError('Required profile input is missing: ' + name)
prepared_cases = OMFITtree()
inputs = []
dir_list = []
input_checksums = {}
point_table = {}
for new_dir, overrides, point_metadata in points:
    stage = os.path.join(submit_workdir, 'staging', new_dir)
    # OMFITobject.deploy(existing_dir) appends its original basename. Supply a
    # nonexistent destination when copying a result directory (framework API).
    os.makedirs(os.path.dirname(stage), exist_ok=True)
    current_input = base_input.duplicate()
    for name, value in overrides.items():
        current_input[name] = value
    time_scheme = physics['time_scheme']
    if time_scheme[0] == 1 and overrides['KY'] > 1:
        current_input['DELTA_T'] = time_scheme[1] / overrides['KY']
        current_input['MAX_TIME'] = time_scheme[2] / overrides['KY']
    packed_names = list(input_names)
    if restart_mode:
        if new_dir not in previous_cases:
            raise ValueError('Restart point missing: %s; use a fresh run for new points' % new_dir)
        previous_cases[new_dir].deploy(stage)
        old_input_path = os.path.join(stage, 'input.cgyro')
        if not os.path.isfile(old_input_path):
            raise ValueError('Restart lacks input.cgyro: ' + new_dir)
        validate_restart_input(OMFITgacode(old_input_path), current_input)
        restart_name = 'bin.cgyro.restart'
        if not os.path.isfile(os.path.join(stage, restart_name)):
            raise ValueError('Restart binary missing: ' + new_dir)
        packed_names.append(restart_name)
    os.makedirs(stage, exist_ok=True)
    current_input.deploy(os.path.join(stage, 'input.cgyro'))
    for name in input_names[1:]:
        inputs_node[name].duplicate().deploy(os.path.join(stage, name))
    prepared = OMFITtree()
    zip_path = os.path.join(submit_workdir, new_dir + '.zip')
    checksums = {}
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in packed_names:
            path = os.path.join(stage, name)
            if not os.path.isfile(path):
                raise ValueError('Prepared input is missing: ' + path)
            with open(path, 'rb') as handle:
                checksums[name] = hashlib.sha256(handle.read()).hexdigest()
            archive.write(path, name)
            prepared[name] = OMFITgacode(path) if name == 'input.cgyro' else OMFITpath(path)
    prepared['zip'] = OMFITpath(zip_path)
    prepared_cases[new_dir] = prepared
    inputs.append(prepared['zip'])
    dir_list.append(new_dir)
    input_checksums[new_dir] = checksums
    point_table[new_dir] = point_metadata

# Commit the prepared run only after every point passes validation and packaging.
if previous_cases:
    history_key = root.get('RUN_MANIFEST', {}).get('run_token', 'imported-' + run_token)
    if 'RUN_HISTORY' not in root:
        root['RUN_HISTORY'] = OMFITtree()
    if history_key not in root['RUN_HISTORY']:
        root['RUN_HISTORY'][history_key] = OMFITtree()
    archived_manifest = copy.deepcopy(previous_manifest)
    archived_manifest.pop('point_table', None)  # Permanent task rows live once in RUN_DB.
    root['RUN_HISTORY'][history_key]['manifest'] = archived_manifest
manifest = {'run_token': run_token, 'case_tag': caseName, 'dimensions': scan_dimensions,
            'points': dir_list, 'server': remote_server, 'tunnel': remote_tunnel,
            'workDir': remote_workdir, 'local_workDir': submit_workdir,
            'serverPicker': cfg_str(rmt_setup, 'serverPicker'),
            'runid': root['SETTINGS']['EXPERIMENT']['runid'], 'nr': physics['nr'],
            'rho': physics.get('rho', None), 'mass': physics['mass'], 'case_id': case_id,
            'scan_axes': scan_axes, 'point_table': point_table,
            'input_sha256': input_checksums, 'status': 'prepared'}
root['RUN_MANIFEST'] = OMFITtree(manifest)
caseRoot[caseName] = prepared_cases
with open(os.path.join(submit_workdir, 'manifest.json'), 'w') as handle:
    json.dump(manifest, handle, indent=2)
environment=script_fragment(required_cfg(server_setup, 'environment'))
executable=script_fragment(required_cfg(server_setup, 'executable')).strip()
scheduler=cfg_str(server_setup, 'scheduler', '').lower()
if scheduler not in ['local', 'pbs', 'slurm']:
    config_error('Selected scheduler must be local, pbs, or slurm')
if local_submit != (scheduler == 'local'):
    config_error('localhost and local scheduler must be selected together')
pbs_file=os.path.join(submit_workdir, 'scan.pbs')
username=os.environ.get('USER', 'localhost') if local_submit else remote_server.split('@')[0]
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
#    r'#SBATCH --workdir=./'+'\n' +\
    if scheduler == 'slurm':
        num_nodes=required_cfg_int(server_setup, 'nodes')
        ntasks_per_node=required_cfg_int(server_setup, 'ntasks_per_node')
        array_parallel=required_cfg_int(server_setup, 'array_parallel')
        bash_head= \
        r'#!/bin/bash '+'\n' + \
        r'#SBATCH -p '+str(required_cfg(server_setup, 'queue')) +'\n' +\
        r'#SBATCH -J '+ps_name +'\n' +\
        r'#SBATCH -t '+str(required_cfg(server_setup, 'w')) +'\n' +\
        r'#SBATCH -o %j.out'+'\n' +\
        r'#SBATCH -e %j.err'+'\n' +\
        r'#SBATCH --nodes='+str(num_nodes)+'\n' +\
        r'#SBATCH --ntasks-per-node='+str(ntasks_per_node) +'\n' +\
        r'#SBATCH --array=0-'+str(dirlist_num-1)+'%'+str(array_parallel)+'\n' +\
        r'ulimit -n 65535'+'\n' +\
        r'ulimit -s unlimited'+'\n' +\
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

###########
#bash_content= \
#'dir_list=('+' '.join(dir_list)+')' +'\n'+ \
#r'for i in ${dir_list[@]}; ' +'\n'+  \
#'do '  +'\n'+  \
#r'  while [[ $( ps -u '+username+r' |grep '+ps_name+r' | wc -l ) -gt '+str(setup['num_cores']-1)+' ]]; do ' +'\n' + \
#r'    sleep 10s' +'\n' +\
#r'  done ' +'\n'+ \
#r'  if [ -d ${i} ]; then  ' +'\n'+\
#r'    echo "${i} exist. Do not unzip this case"   ' +'\n'+\
#r'  cd $i' +'\n'+\
#r'  else'   +'\n'+\
#r'    unzip ${i}.zip -d $i'+'\n'+\
#r'    cd $i' +'\n'+\
#r'    cp input.cgyro* input.cgyro.tmp && mv input.cgyro.tmp input.cgyro;'+'\n'+\
#r'  fi'+'\n'+\
#r'  '+executable+' > run_log & ' +'\n'+ \
#r'  sleep 5s' +'\n'+ \
#r"  cd .." +'\n'+ \
#r'done' +'\n'

if local_submit:
    bash_content= \
    r'dir_list=('+' '.join(dir_list)+')' +'\n'+ \
    r'for current_dir in ${dir_list[@]}; do'+'\n'+\
    r'  prepare_case_dir "${current_dir}"'+'\n'+\
    r'  '+executable+' > run_log 2>&1'+'\n'+\
    r'  cd ..'+'\n'+\
    r'done'+'\n'
else:
    if scheduler == 'slurm':
        bash_content= \
        r'dir_list=('+' '.join(dir_list)+')' +'\n'+ \
        r'current_dir=${dir_list[$SLURM_ARRAY_TASK_ID]}' +'\n'+ \
        r'prepare_case_dir "${current_dir}"'+'\n'+\
        r''+executable+' > run_log 2>&1' +'\n'
    else:
        bash_content= \
        r'dir_list=('+' '.join(dir_list)+')' +'\n'+ \
        r'for current_dir in ${dir_list[@]}; do'+'\n'+\
        r'  while [[ $( ps -u '+username+r' |grep '+ps_name+r' | wc -l ) -gt '+str(required_cfg_int(server_setup, 'n')-1)+' ]]; do'+'\n'+\
        r'    sleep 2s'+'\n'+\
        r'  done'+'\n'+\
        r'  prepare_case_dir "${current_dir}"'+'\n'+\
        r'  '+executable+' > run_log 2>&1 &'+'\n'+\
        r'  cd ..'+'\n'+\
        r'done'+'\n'+\
        r'while [[ $( ps -u '+username+r' |grep '+ps_name+r' | wc -l ) -gt 0 ]]; do'+'\n'+\
        r'  sleep 5s'+'\n'+\
        r'done'+'\n'+\
        r'rm ${JOBID_FILE}'+'\n'




#bash_tail= \
#r'while [[ $( ps -u '+username+r' |grep '+ps_name+r' | wc -l ) -gt 0 ]]; do ' +'\n' + \
#r'  sleep 5s' +'\n'+ \
#r'done ' +'\n'+ \
#r'rm ${JOBID_FILE}' +'\n'



##############################################
##############################################
with open(pbs_file,'w') as f1:
    #f1.write(bash_head+'\n'+bash_content+'\n'+bash_tail)
    f1.write(bash_head+'\n'+bash_helpers+'\n'+bash_content)
pbs_name = path_basename(pbs_file)
caseRoot[caseName][pbs_name]=OMFITascii(pbs_file)

inputs.append(caseRoot[caseName][pbs_name])
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
                                   executable='/usr/bin/env -u LD_LIBRARY_PATH -u CONDA_PREFIX -u CONDA_DEFAULT_ENV LC_ALL=C LANG=C /bin/bash scan.pbs',clean=False,std_out=submit_out,std_err=submit_err)
    else:
        submit_cmd='sbatch scan.pbs'
        submit_rule=r'(?i)submitted\s+batch\s+job\s+([0-9]+)'
        if scheduler == 'pbs':
            submit_cmd='qsub scan.pbs'
            submit_rule=r'([0-9]{3,}(?:\.[A-Za-z0-9._-]+)?)'
        rmtserver=remote_server
        rmttunnel=remote_tunnel
        workdir=submit_workdir
        rmtworkdir=remote_workdir
        submit_out=[]
        submit_err=[]
        submit_log='.cgyro_submit.out'
        submit_wrapper="/bin/bash -lc 'rm -f " + submit_log + "; " + submit_cmd + " > " + submit_log + " 2>&1; cat " + submit_log + "'"
        ret_code=OMFITx.executable(root, inputs=inputs, outputs=[],  \
                                   server=rmtserver, \
                                   tunnel=rmttunnel, \
                                   workdir=workdir,\
                                   remotedir=rmtworkdir,\
                                   executable=submit_wrapper,clean=False,std_out=submit_out,std_err=submit_err)
        submit_read_cmd='for i in $(seq 1 120); do if [ -s '+submit_log+' ]; then cat '+submit_log+'; exit 0; fi; sleep 2; done; echo "ERROR: '+submit_log+' was not created"; exit 1'
        submit_text=OMFITx.remote_execute(
            rmtserver,
            submit_read_cmd,
            rmtworkdir,
            rmttunnel,
            quiet=False,
            ignoreReturnCode=True,
            use_bang_command=False
        )
        submit_combined=output_to_text(submit_out)+'\n'+output_to_text(submit_err)+'\n'+output_to_text(submit_text)
        job_id=parse_scheduler_job_id(submit_combined, submit_rule)
        root['RUN_MANIFEST']['job_id'] = job_id
        root['RUN_MANIFEST']['status'] = 'submitted'
        if scheduler == 'pbs':
            wait_cmd='hb=0; while qstat '+job_id+' >/dev/null 2>&1; do sleep 30; hb=$((hb+30)); if [ \"$hb\" -ge 600 ]; then echo \"[heartbeat] job '+job_id+' still in queue/running at $(date)\"; hb=0; fi; done; echo \"[heartbeat] job '+job_id+' finished at $(date)\"'
        else:
            wait_cmd='hb=0; while squeue -h -j '+job_id+' | grep -q .; do sleep 30; hb=$((hb+30)); if [ \"$hb\" -ge 600 ]; then echo \"[heartbeat] job '+job_id+' still in queue/running at $(date)\"; hb=0; fi; done; echo \"[heartbeat] job '+job_id+' finished at $(date)\"'
        OMFITx.remote_execute(
            rmtserver,
            wait_cmd,
            rmtworkdir,
            rmttunnel,
            quiet=False,
            ignoreReturnCode=True,
            use_bang_command=False
        )

    root['RUN_MANIFEST']['status'] = 'submitted_or_finished'
