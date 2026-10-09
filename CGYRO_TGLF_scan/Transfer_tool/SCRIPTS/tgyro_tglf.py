# -*-Python-*-
"""Run TGYRO and download its outputs before constructing a local result tree."""
import os
from OMFITlib_transfer_workflow import tgyro_batch_settings
from OMFITlib_gacode_installations import program_guard

# OMFITx.execute() reads SHELL directly.  Desktop/VNC sessions may omit it.
if not os.environ.get('SHELL'):
    os.environ['SHELL'] = '/bin/bash'

setup = root['SETTINGS']['SETUP']
remote = root['SETTINGS'].get('REMOTE_SETUP', {})
selected = remote.get(str(remote.get('serverPicker', '') or ''), {}) or {}
environment = str(selected.get('environment', None) or remote.get('environment', None)
                  or setup.get('executable', '') or '')
p_tgyro = int(setup['p_tgyro'])
if p_tgyro < 2 or p_tgyro != float(setup['p_tgyro']):
    raise ValueError('Transfer_tool 的半径点数必须是至少为 2 的整数。')
batch = tgyro_batch_settings(root)
run_input = root['INPUTS']['input.tgyro'].duplicate()
run_input['DIR'].clear()
for k in range(1, p_tgyro + 1):
    run_input['DIR']['TGLF' + str(k)] = 1
inputs = [(root['INPUTS']['input.gacode'], 'input.gacode'),
          (root['INPUTS']['input.tglf'], 'input.tglf'), (run_input, 'input.tgyro')]
if 'input.profiles.geo' in root['INPUTS']:
    inputs.append((root['INPUTS']['input.profiles.geo'], 'input.profiles.geo'))
status_file = 'transfer_tgyro.exit'
outputs = ['out.tgyro.*', 'input.tgyro.gen', 'input.gacode*', 'TGLF*/out.tglf.*', status_file]
# A successful queue submission is not proof that TGYRO completed successfully.
executable = '#!/bin/bash\nset -e\ntrap \'status=$?; printf "%s\\n" "$status" > ' + status_file + "' EXIT\n"
if batch:
    allocation = 'SLURM_JOB_ID' if batch['batch_type'] == 'SLURM' else 'PBS_JOBID'
    executable += ('if [ -z "${' + allocation + ':-}" ]; then\n'
                   + '    echo "Transfer TGYRO requires a scheduler allocation." >&2\n    exit 1\nfi\n')
executable += (environment + '\n' + program_guard('tgyro')
               + '\nexport OMP_NUM_THREADS=1\nexport OMP_THREAD_LIMIT=1\ncommand -v tgyro >/dev/null\n')
for k in range(1, p_tgyro + 1):
    dirname = 'TGLF' + str(k)
    executable += 'mkdir -p ' + dirname + '\ncp input.tglf ' + dirname + '/input.tglf\n'
command = 'tgyro -e . -n ' + str(p_tgyro)
executable += command + '\n'
# Some GACODE launchers return 0 even when mpirun cannot start the binary.
# A real control/profile pair is required before the exit trap records success.
executable += ('for output in out.tgyro.control out.tgyro.profile input.tgyro.gen; do\n'
               '    [ -s "$output" ] || { echo "TGYRO did not generate $output." >&2; exit 1; }\n'
               'done\n')
workdir = setup['workDir']
if batch:
    print('Transfer_tool: {} submission on {}; nodes=1, MPI ranks={}, threads/rank=1.'.format(
        batch['batch_type'], batch['server'], p_tgyro))
    print('Transfer_tool: shared job directory: ' + batch['remotedir'])
else:
    print('Transfer_tool: explicit localhost execution; MPI ranks={}.'.format(p_tgyro))
print('Transfer_tool: ' + command)


def job_log_tail():
    details = []
    for filename in ('transfer_tgyro.err', 'transfer_tgyro.out'):
        path = os.path.join(workdir, filename)
        if not os.path.isfile(path):
            continue
        with open(path, 'rb') as stream:
            stream.seek(max(0, os.path.getsize(path) - 4000))
            content = stream.read().decode('utf-8', 'replace').strip()
        if content:
            details.append(filename + '：\n' + content)
    return '\n'.join(details)


if batch:
    outputs.extend(['transfer_tgyro.out', 'transfer_tgyro.err'])
    # The batch allocation and input.tgyro DIR layout request the same ranks.
    batch_option = ('#SBATCH --nodes=1\n#SBATCH --ntasks-per-node=' + str(p_tgyro)
                    + '\n#SBATCH --output=transfer_tgyro.out\n#SBATCH --error=transfer_tgyro.err'
                    if batch['batch_type'] == 'SLURM' else '#PBS -o transfer_tgyro.out\n#PBS -e transfer_tgyro.err')
    # submit_job creates batch.sh, invokes sbatch/qsub and waits before collecting
    # outputs.  Calling executable on the TGYRO body would run on the login host.
    OMFITx.submit_job(root, batch_command=executable, inputs=inputs, outputs=outputs,
                     ntasks=p_tgyro, nproc_per_task=1, out_name='TransferTGYRO', batch_option=batch_option,
                     std_out='transfer_tgyro.out', std_err='transfer_tgyro.err', workdir=workdir,
                     ignoreReturnCode=True, **batch)
else:
    ret_code = OMFITx.executable(root, inputs=inputs, outputs=outputs, executable=executable,
                                server='localhost', tunnel='', remotedir=workdir,
                                workdir=workdir, ignoreReturnCode=False)
    if ret_code != 0:
        raise RuntimeError('TGYRO failed with return code {}'.format(ret_code))
status_path = os.path.join(workdir, status_file)
if not os.path.isfile(status_path):
    details = job_log_tail()
    message = 'TGYRO 作业未进入或未完成执行脚本。'
    if batch:
        message += '共享作业目录：' + batch['remotedir']
    raise RuntimeError(message + ('\n' + details if details else ''))
with open(status_path) as stream:
    status = stream.read().strip()
if status != '0':
    details = job_log_tail()
    raise RuntimeError('TGYRO 运行失败，退出码：' + status + ('\n' + details if details else ''))
missing = [name for name in ('out.tgyro.control', 'out.tgyro.profile', 'input.tgyro.gen')
           if not os.path.isfile(os.path.join(workdir, name)) or os.path.getsize(os.path.join(workdir, name)) == 0]
if missing:
    details = job_log_tail()
    raise RuntimeError('TGYRO 未返回有效输出：' + '、'.join(missing) + '；已停止后续输入生成。'
                       + ('\n' + details if details else ''))
try:
    result = OMFITtgyro(workdir)
    result.keys()  # Validate/load before replacing the previous results.
    if 'rho' not in result:
        raise ValueError('TGYRO 输出中缺少半径数据 rho')
except Exception as exc:
    details = job_log_tail()
    raise RuntimeError('TGYRO 输出读取失败，原结果保留：' + str(exc)
                       + ('\n' + details if details else '')) from exc
root['OUTPUTS']['TGYRO'] = result
