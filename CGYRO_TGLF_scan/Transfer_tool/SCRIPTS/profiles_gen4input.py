# -*-Python-*-
"""Generate local parameter files and publish only complete successful output."""
import os
from OMFITlib_transfer_particles import MAIN_ION_RULE, close_local_input
particle_report = root['OUTPUTS'].get('Particle_processing', {})
if (particle_report.get('options', {}).get('main_ion_rule', '') != MAIN_ION_RULE
        or not particle_report.get('main_count', 0) or not particle_report.get('after', None)):
    raise ValueError('缺少本轮自动主离子识别记录，请从“运行 Transfer_tool”重新生成输入。')
inputs = [(root['INPUTS']['input.gacode'], 'input.gacode')]
outputs = ['input.tglf.locpargen', 'input.cgyro.locpargen']
setup = root['SETTINGS']['SETUP']
workdir = setup['workDir']
rho_arr = root['OUTPUTS']['TGYRO']['rho'][0][1:]
pending = {}
neutrality = {}
for k, rho in enumerate(rho_arr, 1):
    executable = (setup.get('executable', '') + '\nset -e\ncommand -v profiles_gen >/dev/null\n'
                  + 'profiles_gen -i input.gacode -loc_rho ' + str(float(rho)))
    ret_code = OMFITx.executable(root, inputs=inputs, outputs=outputs, workdir=workdir,
                                executable=executable, clean=True, ignoreReturnCode=False)
    if ret_code != 0:
        raise RuntimeError('locpargen failed at rho={} with code {}'.format(rho, ret_code))
    for code in ('tglf', 'cgyro'):
        path = os.path.join(workdir, 'input.' + code + '.locpargen')
        if not os.path.isfile(path):
            raise RuntimeError('Missing downloaded output: ' + path)
        obj = OMFITgacode(path)
        obj.keys()  # Read before the next execution cleans its working directory.
        neutrality['input.{}_{}'.format(code, k)] = close_local_input(
            obj, code, particle_report['main_count'], particle_report['after'])
        pending['input.{}_{}'.format(code, k)] = obj.duplicate()
root['OUTPUTS'].setdefault('Profiles_gen', OMFITtree()).update(pending)
root['OUTPUTS'].setdefault('Particle_processing', OMFITtree())['local_inputs'] = neutrality
