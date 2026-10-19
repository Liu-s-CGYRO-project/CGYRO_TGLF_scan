# -*-Python-*-
"""Generate local parameter files and publish only complete successful output."""
import os
from OMFITlib_transfer_particles import (EQUIVALENT_RULE, SEPARATE_FAST_RULE, MAIN_ION_RULE, NEUTRALITY_RULE,
                                        close_local_input, validate_local_neutrality)
from OMFITlib_transfer_equivalent import equivalent_local_input, separate_fast_local_input, locpargen_rhostar
from OMFITlib_gacode_installations import program_guard
from OMFITlib_transfer_workflow import profiles_python_environment
from OMFITlib_transfer_zeff import prescribe_local_zeff

# OMFITx.execute() reads SHELL directly.  Desktop/VNC sessions may omit it.
if not os.environ.get('SHELL'):
    os.environ['SHELL'] = '/bin/bash'

particle_report = root['OUTPUTS'].get('Particle_processing', {})
if (particle_report.get('options', {}).get('main_ion_rule', '') != MAIN_ION_RULE
        or particle_report.get('options', {}).get('neutrality_rule', '') != NEUTRALITY_RULE
        or particle_report.get('source_neutrality', {}).get('rule', '') != NEUTRALITY_RULE
        or not particle_report.get('main_count', 0) or not particle_report.get('after', None)):
    raise ValueError('缺少本轮自动主离子识别记录，请从“运行 Transfer_tool”重新生成输入。')
particle_mode = particle_report['options'].get('particle_mode', 'all')
equivalent_rule = {'equivalent': EQUIVALENT_RULE, 'separate_fast': SEPARATE_FAST_RULE}.get(particle_mode, None)
if equivalent_rule is not None and particle_report['options'].get('equivalent_rule', '') != equivalent_rule:
    raise ValueError('等效杂质规则已更新，请从“运行 Transfer_tool”重新生成输入。')
inputs = [(root['INPUTS']['input.gacode'], 'input.gacode')]
outputs = ['input.tglf.locpargen', 'input.cgyro.locpargen', 'out.locpargen']
setup = root['SETTINGS']['SETUP']
workdir = setup['workDir']
rho_arr = root['OUTPUTS']['TGYRO']['rho'][0][1:]
pending = {}
neutrality = {}
for k, rho in enumerate(rho_arr, 1):
    environment = setup.get('profiles_environment', None) or setup.get('executable', '')
    executable = ('#!/bin/bash\nset -e\n' + environment + '\n' + program_guard('profiles')
                  + profiles_python_environment()
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
    rhostar = locpargen_rhostar(os.path.join(workdir, 'out.locpargen'), local['cgyro'])
    for code, obj in local.items():
        if particle_mode == 'separate_fast':
            result = separate_fast_local_input(obj, code, particle_report['main_count'], particle_report['after'], rhostar)
        elif particle_mode == 'equivalent':
            # Use the frozen generation choice, never a live GUI selection that
            # may have changed while TGYRO / locpargen was running.
            result = equivalent_local_input(obj, code, particle_report['main_count'], particle_report['after'], rhostar,
                                            temperature_mode=particle_report['options']['equivalent_temperature'])
        else:
            result = close_local_input(obj, code, particle_report['main_count'], particle_report['after'], rhostar)
        result['rho'] = float(rho)
        result['rhostar'] = rhostar
        if particle_report['options'].get('particle_mode', 'all') == 'main_only':
            result['prescribed_zeff'] = prescribe_local_zeff(obj, code, particle_report.get('prescribed_zeff', {}))
        # Re-read actual final fields after every transform, including Zeff.
        # A saved correction residual alone is not proof that the card is neutral.
        result['final_neutrality'] = validate_local_neutrality(obj, code, rhostar)
        # rho describes the source radius, not a CGYRO/TGLF input parameter.
        # Keep it in the audit record; solver files must contain solver keys only.
        neutrality['input.{}_{}'.format(code, k)] = result
        pending['input.{}_{}'.format(code, k)] = obj.duplicate()
# Replace the completed set atomically so a new, shorter radial grid cannot
# leave stale input.cgyro_N / input.tglf_N entries from an earlier run.
complete = OMFITtree()
complete.update(pending)
root['OUTPUTS']['Profiles_gen'] = complete
root['OUTPUTS'].setdefault('Particle_processing', OMFITtree())['local_inputs'] = neutrality
