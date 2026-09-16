# -*-Python-*-
"""Run TGYRO and download its outputs before constructing a local result tree."""
import os
import glob
from OMFITlib_transfer_workflow import tgyro_batch_settings

setup = root['SETTINGS']['SETUP']
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
executable = '#!/bin/bash\ntrap \'status=$?; printf "%s\\n" "$status" > ' + status_file + "' EXIT\n"
executable += setup.get('executable', '') + '\nset -e\nexport OMP_NUM_THREADS=1\ncommand -v tgyro >/dev/null\n'
for k in range(1, p_tgyro + 1):
    dirname = 'TGLF' + str(k)
    executable += 'mkdir -p ' + dirname + '\ncp input.tglf ' + dirname + '/input.tglf\n'
command = 'tgyro -e . -n ' + str(p_tgyro)
executable += command + '\n'
workdir = setup['workDir']
print('Transfer_tool：' + command + ('（' + batch['batch_type'] + '）' if batch else ''))
if batch:
    outputs.extend(['transfer_tgyro.out', 'transfer_tgyro.err'])
    # The batch allocation and input.tgyro DIR layout request the same ranks.
    batch_option = ('#SBATCH --nodes=1\n#SBATCH --output=transfer_tgyro.out\n#SBATCH --error=transfer_tgyro.err'
                    if batch['batch_type'] == 'SLURM' else '#PBS -o transfer_tgyro.out\n#PBS -e transfer_tgyro.err')
    OMFITx.submit_job(root, batch_command=executable, inputs=inputs, outputs=outputs,
                     ntasks=p_tgyro, nproc_per_task=1, out_name='TransferTGYRO', batch_option=batch_option,
                     std_out='transfer_tgyro.out', std_err='transfer_tgyro.err', workdir=workdir,
                     ignoreReturnCode=False, **batch)
else:
    ret_code = OMFITx.executable(root, inputs=inputs, outputs=outputs, executable=executable,
                                workdir=workdir, ignoreReturnCode=False)
    if ret_code != 0:
        raise RuntimeError('TGYRO failed with return code {}'.format(ret_code))
status_path = os.path.join(workdir, status_file)
if not os.path.isfile(status_path):
    raise RuntimeError('TGYRO 未完成，请查看作业输出。')
with open(status_path) as stream:
    status = stream.read().strip()
if status != '0':
    raise RuntimeError('TGYRO 运行失败，退出码：' + status)
if not glob.glob(os.path.join(workdir, 'out.tgyro.*')):
    raise RuntimeError('TGYRO outputs were not downloaded to the local work directory')
result = OMFITtgyro(workdir)
result.keys()  # Validate/load before replacing the previous results.
root['OUTPUTS']['TGYRO'] = result
