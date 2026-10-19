# -*-Python-*-
"""Submit bounded TGLF batches using the applied project queue and environment."""
from builtins import dict, enumerate, float, int, len, list, min, range, set, sorted, str
import copy
import glob
import os
import posixpath
import uuid
from omfit_classes.omfit_python import OMFITworkDir

if not os.environ.get('SHELL', None):
    os.environ['SHELL'] = '/bin/bash'


defaultVars(inputTGLF=None, runIDs=None, results=None, enforce_constraints=False,
            parallel=None, continue_on_error=False)
if inputTGLF is None:
    raise OMFITexception('No inputs given.')
if results is None:
    results = root['batch'] = OMFITcollection()
runIDs = list(range(len(inputTGLF))) if runIDs is None else list(runIDs)
if len(runIDs) != len(inputTGLF):
    raise ValueError('TGLF runIDs do not match inputs')
try:
    unique_ids = len(set(runIDs)) == len(runIDs)
except TypeError:
    raise ValueError('TGLF runIDs must be valid mapping keys')
if not unique_ids:
    # Every solver point needs one result slot. Reject collisions before any
    # submission; otherwise a later point silently overwrites an earlier one.
    raise ValueError('TGLF runIDs must be unique')
if not inputTGLF:
    OMFITx.End()
parallel = root['SETTINGS']['PHYSICS'].get('parallelScan', 3) if parallel is None else parallel
if int(parallel) < 1 or int(parallel) != float(parallel):
    raise ValueError('TGLF parallel tasks must be a positive integer')
parallel = int(parallel)
remote = root['SETTINGS']['REMOTE_SETUP']
selected = remote.get(str(remote.get('serverPicker', '')), {})
scheduler = str(selected.get('scheduler', remote.get('scheduler', ''))).lower()
if scheduler not in ('local', 'slurm', 'pbs'):
    raise ValueError('Apply the project environment and queue before running TGLF')
partition = selected.get('queue', remote.get('queue', ''))
wall_time = str(selected.get('w', remote.get('w', '')))
if scheduler != 'local' and (not partition or not wall_time):
    raise ValueError('TGLF queue and wall time are required')
environment = str(selected.get('environment', remote.get('environment', '')) or '')
command = str(selected.get('executable', '') or '')
if not command:
    lines = str(root['SETTINGS']['SETUP']['executable']).splitlines()
    environment, command = '\n'.join(lines[:-1]), lines[-1]
threads = int(selected.get('cpus_per_task', 1))
if threads < 1:
    raise ValueError('TGLF threads per task must be positive')
constraints = root.get('constraint_vars', {}) if enforce_constraints else {}
failures = []
local_base = str(root['SETTINGS']['SETUP']['workDir'] or '')
if not local_base or not os.path.isabs(local_base):
    raise ValueError('TGLF local working directory must be an absolute path')
remote_base = str(remote.get('workDir', None) or OMFITworkDir(root, remote.get('server', '')))
if not posixpath.isabs(remote_base):
    raise ValueError('TGLF remote working directory must be an absolute path')
run_token = uuid.uuid4().hex


def read_log(path):
    with open(path, encoding='utf-8', errors='replace') as stream:
        return stream.read()[-8000:]


def batch_diagnostics(workdir, index):
    paths = [os.path.join(workdir, name) for name in ('tglf.submit.log', 'tglf.submit.exit')]
    paths += sorted(glob.glob(os.path.join(workdir, 'tglf_*_{}.err'.format(index))))
    paths += sorted(glob.glob(os.path.join(workdir, 'tglf_*_{}.out'.format(index))))
    paths += sorted(glob.glob(os.path.join(workdir, 'tglf.e*')))
    paths += sorted(glob.glob(os.path.join(workdir, 'tglf.o*')))
    text = []
    files = OMFITtree()
    for path in paths:
        if os.path.isfile(path):
            name = os.path.basename(path)
            content = read_log(path)
            if content.strip():
                text.append(name + ':\n' + content)
            files[name] = OMFITascii(path).duplicate()
    return '\n\n'.join(text), files

# Submit at most `parallel` jobs at once, including on PBS without array throttles.
# Each run and wave owns its staging directories; no scan cleans another scan.
# Results and diagnostics are copied into OMFIT before the next wave is staged.
for start in range(0, len(inputTGLF), parallel):
    stop = min(start + parallel, len(inputTGLF))
    leaf = ('tglf_runs', run_token, 'batch_{:06d}'.format(start))
    workdir = os.path.join(local_base, *leaf)
    remotedir = posixpath.join(remote_base, *leaf) + '/'
    execution = dict(workdir=workdir, remotedir=remotedir, clean=False,
                     server=remote.get('server', None), tunnel=remote.get('tunnel', None),
                     ignoreReturnCode=False)
    inputs = []
    for index in range(start, stop):
        value = copy.deepcopy(inputTGLF[index])
        if constraints:
            namespace = dict(value)
            for name, expression in constraints.items():
                value[name] = eval(expression, globals(), namespace)
                namespace[name] = value[name]
        inputs.append((value, 'input_{}.tglf'.format(index)))
        body = '#!/bin/bash\nset -e\ntglf_point_dir="$PWD/{0}"\ntglf_point_phase=preparing\n'.format(index)
        body += "trap 'status=$?; printf \"%s\\n\" \"$status\" > \"$tglf_point_dir/tglf.exit\"; "
        body += "printf \"%s\\n\" \"$tglf_point_phase\" > \"$tglf_point_dir/tglf.phase\"' EXIT\n"
        body += 'mkdir -p "$tglf_point_dir"\nexec > "$tglf_point_dir/run_log" 2>&1\n'
        body += 'cp input_{}.tglf "$tglf_point_dir/input.tglf"\ncd "$tglf_point_dir"\n'.format(index)
        body += 'tglf_point_phase=environment\n' + environment + '\n'
        body += 'cd "$tglf_point_dir"\nexport OMP_NUM_THREADS=' + str(threads) + '\n'
        body += 'tglf_point_phase=running\n' + command + '\ntglf_point_phase=complete\n'
        inputs.append(OMFITascii('tglf_{}.sh'.format(index), fromString=body))
    submission_error = None
    try:
        if scheduler == 'local':
            submit = '#!/bin/bash\npids=""\n'
            for index in range(start, stop):
                submit += '/bin/bash tglf_{}.sh &\npids="$pids $!"\n'.format(index)
            submit += 'status=0\nfor pid in $pids; do\n  if ! wait "$pid"; then status=1; fi\ndone\n'
            submit += 'printf "%s\\n" "$status" > tglf.submit.exit\nexit 0\n'
            inputs.append(OMFITascii('submit_tglf.sh', fromString=submit))
            OMFITx.executable(root, inputs=inputs, outputs=['./'], executable='/bin/bash submit_tglf.sh',
                              queued=False, **execution)
        elif scheduler == 'slurm':
            if '\n' in str(partition) + wall_time or '\r' in str(partition) + wall_time:
                raise ValueError('TGLF queue and wall time must each be a single line')
            batch = ('#!/bin/bash\n#SBATCH -p {queue}\n#SBATCH --ntasks=1\n'
                     '#SBATCH --cpus-per-task={threads}\n#SBATCH --mem-per-cpu=2GB\n'
                     '#SBATCH --time={time}\n#SBATCH --export=all\n'
                     '#SBATCH --output=tglf_%A_%a.out\n#SBATCH --error=tglf_%A_%a.err\n'
                     '#SBATCH --array={start}-{last}\n\n'
                     '/bin/bash "tglf_${{SLURM_ARRAY_TASK_ID}}.sh"\n').format(
                         queue=partition, threads=threads, time=wall_time, start=start, last=stop - 1)
            inputs.append(OMFITascii('batch.sh', fromString=batch))
            # --wait waits for the whole array, unlike early/empty accounting polls.
            # Save the scheduler status and collect files even on a job failure;
            # every point still requires exit 0 and a readable flux output below.
            submit = r'''#!/bin/bash
for binding in ${!SLURM_CPU_BIND@}; do unset "$binding"; done
cancel_submission() {
  job_id=$(awk '/^Submitted batch job [0-9]+$/ {id=$4} END {print id}' tglf.submit.log)
  if [ -n "$job_id" ]; then scancel "$job_id"; fi
  kill "$submit_pid" 2>/dev/null || true
  printf '130\n' > tglf.submit.exit
  exit 130
}
LC_ALL=C sbatch --wait --chdir="$PWD" batch.sh > tglf.submit.log 2>&1 &
submit_pid=$!
trap cancel_submission INT TERM HUP
heartbeat=0
while kill -0 "$submit_pid" 2>/dev/null; do
  sleep 30
  heartbeat=$((heartbeat+30))
  if [ "$heartbeat" -ge 60 ] && kill -0 "$submit_pid" 2>/dev/null; then
    echo '[heartbeat] Waiting for the TGLF array to finish.'
    heartbeat=0
  fi
done
wait "$submit_pid"
status=$?
trap - INT TERM HUP
cat tglf.submit.log
printf '%s\n' "$status" > tglf.submit.exit
exit 0
'''
            inputs.append(OMFITascii('submit_tglf.sh', fromString=submit))
            OMFITx.executable(root, inputs=inputs, outputs=['./'], executable='/bin/bash submit_tglf.sh',
                              queued=False, **execution)
        else:
            options = '#PBS -J {}-{}'.format(start + 1, stop)
            batch = '/bin/bash "tglf_$((PBS_ARRAY_INDEX-1)).sh"'
            OMFITx.submit_job(root, batch_command=batch, inputs=inputs, outputs=['./'],
                environment='', partition=partition, job_time=wall_time, batch_type='PBS',
                ntasks=threads, nproc_per_task=threads, batch_option=options, out_name='tglf', **execution)
    except Exception as exc:
        submission_error = exc
        # A submission/transport exception must not discard available job logs.
        try:
            OMFITx.executable(root, inputs=[], outputs=['./'], executable='true', queued=False, **execution)
        except Exception as collection_error:
            printe('TGLF diagnostic collection failed: ' + str(collection_error))
    batch_status = None
    status_path = os.path.join(workdir, 'tglf.submit.exit')
    if os.path.isfile(status_path):
        batch_status = read_log(status_path).strip()
    batch_failed = []
    for index in range(start, stop):
        directory = os.path.join(workdir, str(index))
        log_path = os.path.join(directory, 'run_log')
        log_text = ''
        scheduler_log, diagnostic_files = batch_diagnostics(workdir, index)
        try:
            if os.path.isfile(log_path):
                log_text = read_log(log_path)
            if scheduler in ('local', 'slurm') and batch_status is None:
                raise RuntimeError('TGLF submission did not return a completion record')
            exit_path = os.path.join(directory, 'tglf.exit')
            if not os.path.isfile(exit_path):
                raise RuntimeError('TGLF did not return a point exit record; submission status: ' + str(batch_status))
            with open(exit_path) as stream:
                status = stream.read().strip()
            if status != '0':
                phase_path = os.path.join(directory, 'tglf.phase')
                phase = read_log(phase_path).strip() if os.path.isfile(phase_path) else 'unknown'
                raise RuntimeError('TGLF exit status: {} (stage: {})'.format(status, phase))
            output = OMFITtglf(directory)
            output.keys()
            if 'gbflux' not in output:
                raise RuntimeError('TGLF did not generate flux output')
            output['gbflux']['data']
            results[runIDs[index]] = output.duplicate()
        except Exception as exc:
            error = OMFITtree()
            message = str(exc)
            if submission_error is not None:
                message += '\nSubmission/collection error: ' + str(submission_error)
            if scheduler_log:
                log_text += '\n\n' + scheduler_log
            error.update(dict(_load_error=message, run_log=log_text.strip(), files=diagnostic_files,
                              local_directory=directory, remote_directory=remotedir + str(index)))
            if os.path.isfile(log_path):
                error['log_file'] = OMFITascii(log_path).duplicate()
            results[runIDs[index]] = error
            failures.append(str(runIDs[index]))
            batch_failed.append(str(runIDs[index]))
            printe('TGLF {} failed: {}\n{}'.format(runIDs[index], message, log_text))
    if submission_error is not None:
        raise submission_error
    if scheduler in ('local', 'slurm') and batch_status != '0' and not batch_failed:
        raise RuntimeError('TGLF submission exit status: {}\n{}'.format(batch_status, scheduler_log))
if failures and not continue_on_error:
    raise RuntimeError('TGLF points failed: ' + ', '.join(failures))
