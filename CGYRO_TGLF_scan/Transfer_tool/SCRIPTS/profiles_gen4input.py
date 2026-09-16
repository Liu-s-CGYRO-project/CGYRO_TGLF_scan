# -*-Python-*-
"""Generate local parameter files and publish only complete successful output."""
import os
from OMFITlib_transfer_particles import EQUIVALENT_RULE, MAIN_ION_RULE, close_local_input
from OMFITlib_transfer_equivalent import equivalent_local_input, locpargen_rhostar

# OMFITx.execute() reads SHELL directly.  Desktop/VNC sessions may omit it.
if not os.environ.get('SHELL'):
    os.environ['SHELL'] = '/bin/bash'

particle_report = root['OUTPUTS'].get('Particle_processing', {})
if (particle_report.get('options', {}).get('main_ion_rule', '') != MAIN_ION_RULE
        or not particle_report.get('main_count', 0) or not particle_report.get('after', None)):
    raise ValueError('缺少本轮自动主离子识别记录，请从“运行 Transfer_tool”重新生成输入。')
equivalent = particle_report['options'].get('particle_mode', 'all') == 'equivalent'
if equivalent and particle_report['options'].get('equivalent_rule', '') != EQUIVALENT_RULE:
    raise ValueError('等效杂质规则已更新，请从“运行 Transfer_tool”重新生成输入。')
inputs = [(root['INPUTS']['input.gacode'], 'input.gacode')]
outputs = ['input.tglf.locpargen', 'input.cgyro.locpargen']
if equivalent:
    outputs.append('out.locpargen')
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
    local = {}
    for code in ('tglf', 'cgyro'):
        path = os.path.join(workdir, 'input.' + code + '.locpargen')
        if not os.path.isfile(path):
            raise RuntimeError('Missing downloaded output: ' + path)
        obj = OMFITgacode(path)
        obj.keys()  # Read before the next execution cleans its working directory.
        local[code] = obj
    rhostar = locpargen_rhostar(os.path.join(workdir, 'out.locpargen'), local['cgyro']) if equivalent else None
    for code, obj in local.items():
        if equivalent:
            result = equivalent_local_input(obj, code, particle_report['main_count'], particle_report['after'], rhostar)
        else:
            result = close_local_input(obj, code, particle_report['main_count'], particle_report['after'])
        result['rho'] = float(rho)
        neutrality['input.{}_{}'.format(code, k)] = result
        pending['input.{}_{}'.format(code, k)] = obj.duplicate()
root['OUTPUTS'].setdefault('Profiles_gen', OMFITtree()).update(pending)
root['OUTPUTS'].setdefault('Particle_processing', OMFITtree())['local_inputs'] = neutrality
