# -*-Python-*-
"""Generate local parameter files and publish only complete successful output."""
import os
from OMFITlib_transfer_particles import close_local_input
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
        neutrality['input.{}_{}'.format(code, k)] = close_local_input(obj, code)
        pending['input.{}_{}'.format(code, k)] = obj.duplicate()
root['OUTPUTS'].setdefault('Profiles_gen', OMFITtree()).update(pending)
root['OUTPUTS'].setdefault('Particle_processing', OMFITtree())['local_inputs'] = neutrality
