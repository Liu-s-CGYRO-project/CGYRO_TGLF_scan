# -*-Python-*-
"""Submit bounded TGLF batches using the applied project queue and environment."""
from builtins import dict, enumerate, float, int, len, list, min, range, str
import copy
import os

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

# Submit at most `parallel` jobs at once, including on PBS without array throttles.
# Results are copied into OMFIT-owned directories before the next batch is staged.
for start in range(0, len(inputTGLF), parallel):
    stop = min(start + parallel, len(inputTGLF))
    inputs = []
    for index in range(start, stop):
        value = copy.deepcopy(inputTGLF[index])
        if constraints:
            namespace = dict(value)
            for name, expression in constraints.items():
                value[name] = eval(expression, globals(), namespace)
                namespace[name] = value[name]
        inputs.append((value, 'input_{}.tglf'.format(index)))
        body = '#!/bin/bash\nset -e\nmkdir -p {0}\ncp input_{0}.tglf {0}/input.tglf\ncd {0}\n'.format(index)
        body += "trap 'status=$?; printf \"%s\\n\" \"$status\" > tglf.exit' EXIT\n"
        body += '{\n' + environment + '\nexport OMP_NUM_THREADS=' + str(threads) + '\n'
        body += command + '\n} > run_log 2>&1\n'
        inputs.append(OMFITascii('tglf_{}.sh'.format(index), fromString=body))
    if scheduler == 'local':
        executable = '\n'.join('/bin/bash tglf_{}.sh &'.format(index) for index in range(start, stop)) + '\nwait\n'
        OMFITx.executable(root, inputs=inputs, outputs=['./'], executable=executable, queued=False,
                          server=remote.get('server', None), tunnel=remote.get('tunnel', None),
                          ignoreReturnCode=False)
    else:
        if scheduler == 'slurm':
            options = '#SBATCH --array={}-{}'.format(start, stop - 1)
            batch = '/bin/bash "tglf_${SLURM_ARRAY_TASK_ID}.sh"'
        else:
            options = '#PBS -J {}-{}'.format(start + 1, stop)
            batch = '/bin/bash "tglf_$((PBS_ARRAY_INDEX-1)).sh"'
        OMFITx.submit_job(root, batch_command=batch, inputs=inputs, outputs=['./'],
            environment='', partition=partition, job_time=wall_time, batch_type=scheduler.upper(),
            ntasks=threads if scheduler == 'pbs' else 1, nproc_per_task=threads,
            batch_option=options, out_name='tglf', server=remote.get('server', None),
            tunnel=remote.get('tunnel', None), ignoreReturnCode=False)
    for index in range(start, stop):
        directory = os.path.join(str(root['SETTINGS']['SETUP']['workDir']), str(index))
        log_text = ''
        try:
            log_path = os.path.join(directory, 'run_log')
            if os.path.isfile(log_path):
                with open(log_path, encoding='utf-8', errors='replace') as stream:
                    log_text = stream.read()[-8000:]
            with open(os.path.join(directory, 'tglf.exit')) as stream:
                status = stream.read().strip()
            if status != '0':
                raise RuntimeError('TGLF exit status: ' + status)
            output = OMFITtglf(directory)
            output.keys()
            if 'gbflux' not in output:
                raise RuntimeError('TGLF did not generate flux output')
            output['gbflux']['data']
            results[runIDs[index]] = output.duplicate()
        except Exception as exc:
            error = OMFITtree()
            error.update(dict(_load_error=str(exc), run_log=log_text))
            if os.path.isfile(log_path):
                error['log_file'] = OMFITascii(log_path).duplicate()
            results[runIDs[index]] = error
            failures.append(str(runIDs[index]))
            printe('TGLF {} failed: {}\n{}'.format(runIDs[index], exc, log_text))
if failures and not continue_on_error:
    raise RuntimeError('TGLF points failed: ' + ', '.join(failures))
