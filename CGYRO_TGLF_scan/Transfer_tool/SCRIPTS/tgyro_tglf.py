# -*-Python-*-
"""Run TGYRO and download its outputs before constructing a local result tree."""
import os
import glob
setup = root['SETTINGS']['SETUP']
p_tgyro = int(setup['p_tgyro'])
numcore = int(setup['num_cores']) * int(setup['num_nodes'])
if setup.get('gacode_shared', False) and p_tgyro > 0 and numcore >= p_tgyro:
    # Use an even number of ranks per radius within the common CPU budget.
    numcore = (numcore // p_tgyro) * p_tgyro
if p_tgyro < 1 or numcore < p_tgyro or numcore % p_tgyro:
    raise ValueError('总进程数需不少于 TGYRO 半径数，并可均匀分配到各半径。请检查统一环境中的资源设置。')
coreppoint = numcore // p_tgyro
run_input = root['INPUTS']['input.tgyro'].duplicate()
run_input['DIR'].clear()
for k in range(1, p_tgyro + 1):
    run_input['DIR']['TGLF' + str(k)] = coreppoint
inputs = [(root['INPUTS']['input.gacode'], 'input.gacode'),
          (root['INPUTS']['input.tglf'], 'input.tglf'), (run_input, 'input.tgyro')]
if 'input.profiles.geo' in root['INPUTS']:
    inputs.append((root['INPUTS']['input.profiles.geo'], 'input.profiles.geo'))
outputs = ['out.tgyro.*', 'input.tgyro.gen', 'input.gacode*', 'TGLF*/out.tglf.*']
executable = setup.get('executable', '') + '\nset -e\ncommand -v tgyro >/dev/null\n'
for k in range(1, p_tgyro + 1):
    dirname = 'TGLF' + str(k)
    executable += 'mkdir -p ' + dirname + '\ncp input.tglf ' + dirname + '/input.tglf\n'
executable += 'tgyro -e . -n ' + str(numcore)
workdir = setup['workDir']
ret_code = OMFITx.executable(root, inputs=inputs, outputs=outputs, executable=executable,
                            workdir=workdir, ignoreReturnCode=False)
if ret_code != 0:
    raise RuntimeError('TGYRO failed with return code {}'.format(ret_code))
if not glob.glob(os.path.join(workdir, 'out.tgyro.*')):
    raise RuntimeError('TGYRO outputs were not downloaded to the local work directory')
result = OMFITtgyro(workdir)
result.keys()  # Validate/load before replacing the previous results.
root['OUTPUTS']['TGYRO'] = result
