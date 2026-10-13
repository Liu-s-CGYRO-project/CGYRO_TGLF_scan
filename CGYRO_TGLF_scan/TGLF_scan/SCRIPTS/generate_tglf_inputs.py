"""Prepare the full 99-radius TGLF input set before replacing any existing data."""
from builtins import dict, enumerate, float, int, isinstance, len, list, str
from datetime import datetime, timezone
from pathlib import PurePosixPath
import copy
import math
import os
import uuid
from OMFITlib_tglf_workbench import clone

defaultVars(profile=None, seed=None, input_text='', radii=None, coordinate='rho',
            include_ions='thermal', profile_digest='', source=None, environment='', command='')
if profile is None or seed is None or len(radii or []) != 99 or not command.strip():
    raise ValueError('TGLF preparation needs input.gacode, a TGLF seed and 99 radii')
if not os.environ.get('SHELL', None):
    os.environ['SHELL'] = '/bin/bash'

module = root['TGYRO']
remote = module['SETTINGS']['REMOTE_SETUP']
selected = remote.get(str(remote.get('serverPicker', '')), {})
scheduler = str(selected.get('scheduler', '') or remote.get('scheduler', '')).lower()
server = str(selected.get('server', '') or remote.get('server', ''))
tunnel = str(selected.get('tunnel', remote.get('tunnel', '')) or '')
partition = str(selected.get('queue', '') or remote.get('queue', ''))
wall_time = str(selected.get('w', '') or remote.get('w', ''))
if scheduler not in ('local', 'slurm', 'pbs'):
    raise ValueError('Apply the project scheduler before generating TGLF inputs')
if scheduler == 'local' and (remote.get('serverPicker', '') != 'localhost'
                             or server not in ('localhost', '127.0.0.1', '::1')):
    raise ValueError('Remote TGLF preparation requires Slurm or PBS')
if scheduler != 'local' and (not server or not partition or not wall_time):
    raise ValueError('TGLF preparation requires a server, queue and wall time')

run_id = 'inputs_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8]
base = OMFITworkDir(root)
if not base:
    raise ValueError('OMFIT local work directory is not available')
workdir = os.path.join(str(base), 'tglf_inputs', run_id)
if scheduler == 'local':
    remotedir = workdir
else:
    shared = str(selected.get('workDir', '') or remote.get('workDir', ''))
    if (not shared.startswith('/') or shared.rstrip('/') in ('', '/tmp') or shared.startswith('/tmp/')
            or '..' in shared.split('/') or '\n' in shared or '\r' in shared):
        raise ValueError('Use a shared absolute job directory visible to compute nodes, not /tmp')
    remotedir = str(PurePosixPath(shared) / 'tglf_inputs' / run_id)

seed = clone(seed)
seed['USE_TRANSPORT_MODEL'] = True
tgyro_input = OMFITascii('input.tgyro', fromString=input_text)
record = OMFITtree()
record.update(dict(id=run_id, status='preparing', created=datetime.now(timezone.utc).isoformat(),
    coordinate=coordinate, radii=list(radii), include_ions=include_ions, profile_digest=profile_digest,
    source=dict(source or {}), runtime=copy.deepcopy(remote), command=command,
    workdir=workdir, remotedir=remotedir, diagnostics=OMFITtree()))
record['input.gacode'] = clone(profile)
record['input.tgyro'] = tgyro_input
record['seed.tglf'] = clone(seed)
module.setdefault('RUN_DB', OMFITtree())[run_id] = record
inputs = [(record['input.gacode'], 'input.gacode'), (tgyro_input, 'input.tgyro'), (seed, 'input.tglf')]
body = '#!/bin/bash\nset -e\nexec > input_generation.log 2>&1\n'
body += "trap 'status=$?; printf \"%s\\n\" \"$status\" > input_generation.exit' EXIT\n"
if scheduler != 'local':
    allocation = 'SLURM_JOB_ID' if scheduler == 'slurm' else 'PBS_JOBID'
    body += ('[ -n "${' + allocation + ':-}" ] || { echo "No scheduler allocation"; exit 1; }\n')
body += environment + '\nexport OMP_NUM_THREADS=1\nexport OMP_THREAD_LIMIT=1\n'
body += 'for i in $(seq 1 99); do mkdir -p "TGLF$i"; cp input.tglf "TGLF$i/input.tglf"; done\n'
body += command + '\n'
body += ('for i in $(seq 1 99); do\n'
         '  [ -s "TGLF$i/out.tglf.localdump" ] || { echo "Missing TGLF$i/out.tglf.localdump"; exit 1; }\n'
         'done\n')
record['job_script'] = OMFITascii('generate_inputs.sh', fromString=body)
inputs.append((record['job_script'], 'generate_inputs.sh'))


def save_diagnostics():
    for name in ('input_generation.log', 'input_generation.exit', 'input_generation.out', 'input_generation.err'):
        path = os.path.join(workdir, name)
        if os.path.isfile(path):
            record['diagnostics'][name] = OMFITascii(path).duplicate()


try:
    print('TGLF: generating 99 local inputs on {} using {}; one MPI rank per radius.'.format(server, scheduler))
    if scheduler == 'local':
        code = OMFITx.executable(module, inputs=inputs, outputs=['./'], executable='/bin/bash generate_inputs.sh',
            queued=False, server=server, tunnel=tunnel, workdir=workdir, remotedir=remotedir, ignoreReturnCode=False)
        if code != 0:
            raise RuntimeError('TGYRO preparation returned ' + str(code))
    else:
        options = ('#SBATCH --nodes=1\n#SBATCH --ntasks-per-node=99\n'
                   '#SBATCH --output=input_generation.out\n#SBATCH --error=input_generation.err'
                   if scheduler == 'slurm' else '#PBS -o input_generation.out\n#PBS -e input_generation.err')
        OMFITx.submit_job(module, batch_command='/bin/bash generate_inputs.sh', inputs=inputs, outputs=['./'],
            environment='', partition=partition, job_time=wall_time, batch_type=scheduler.upper(),
            ntasks=99, nproc_per_task=1, batch_option=options, out_name='TGLFInputs',
            server=server, tunnel=tunnel, workdir=workdir, remotedir=remotedir, ignoreReturnCode=False)
    save_diagnostics()
    with open(os.path.join(workdir, 'input_generation.exit')) as stream:
        status = stream.read().strip()
    if status != '0':
        raise RuntimeError('TGYRO preparation exit status: ' + status)
    generated = OMFITtree()
    for index, radius in enumerate(radii, 1):
        value = OMFITgacode(os.path.join(workdir, 'TGLF' + str(index), 'out.tglf.localdump'))
        for name in ('NS', 'KY', 'RMIN_LOC', 'RMAJ_LOC', 'Q_LOC', 'RLTS_1', 'RLNS_1'):
            if name not in value:
                raise ValueError('TGLF{} local input is missing {}'.format(index, name))
            if not math.isfinite(float(value[name])):
                raise ValueError('TGLF{} has invalid {}'.format(index, name))
        if float(value['NS']) != int(value['NS']) or int(value['NS']) < 1:
            raise ValueError('TGLF{} has invalid NS'.format(index))
        value['USE_TRANSPORT_MODEL'] = True
        generated[float(radius)] = value.duplicate()
    record['inputs'] = generated
    # Some TGYRO versions omit transport outputs in prepare-only mode.
    # A complete validated local input set is sufficient for TGLF scans.
    if os.path.isfile(os.path.join(workdir, 'out.tgyro.control')):
        try:
            result = OMFITtgyro(workdir)
            result.keys()
            record['tgyro_output'] = result.duplicate()
        except Exception as exc:
            record['tgyro_output_error'] = str(exc)
    replacements = clone(generated)
    tgyro_output = clone(record['tgyro_output']) if 'tgyro_output' in record else None
    metadata = dict(run_id=run_id, profile_digest=profile_digest,
                    coordinate=coordinate, include_ions=include_ions, source=dict(source or {}))
    old = OMFITtree()
    cache_keys = ('input.tglf', 'tgyro_output', 'scanResults', 'scanResults_spectra',
        'scanResults2D', 'scanResults2D_spectra', 'UQResults', 'UQResults_spectra',
        'Experimental_fluxes', 'Experimental_spectra', '_scan_cache_provenance',
        '_radial_cache_provenance', '_input_cache_provenance', '_local_input_generation')
    for key in cache_keys:
        if key in root:
            old[key] = clone(root[key])
    record['previous_scan'] = old
    new_state = dict({'input.tglf': replacements}, _local_input_generation=metadata)
    if tgyro_output is not None:
        new_state['tgyro_output'] = tgyro_output
    try:
        for key in cache_keys:
            root.pop(key, None)
        root.update(new_state)
    except BaseException:
        for key in cache_keys:
            root.pop(key, None)
        root.update(old)
        raise
    record.update(dict(status='complete', finished=datetime.now(timezone.utc).isoformat()))
    print('TGLF: all 99 local inputs are ready in TGLF_scan/input.tglf')
except BaseException as exc:
    save_diagnostics()
    record.update(dict(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed',
                       error=str(exc), finished=datetime.now(timezone.utc).isoformat()))
    print('TGLF preparation failed; see TGLF_scan/TGYRO/RUN_DB/' + run_id)
    print('Remote directory: ' + remotedir)
    raise
