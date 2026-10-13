# -*-Python-*-
"""Generate profiles using the source selected by the Transfer GUI."""
import os
from OMFITlib_gacode_installations import program_guard
from OMFITlib_transfer_workflow import profiles_python_environment

# OMFITx.execute() reads SHELL directly.  Desktop/VNC sessions may omit it.
if not os.environ.get('SHELL'):
    os.environ['SHELL'] = '/bin/bash'


def prepare_profiles_input(input_nodes, selected=None):
    aliases = {'statefile': ('statefile', 'statefile.nc'), 'pfile': ('pfile',),
               'input.profiles': ('input.profiles',)}
    candidates = [selected] if selected in aliases else ['statefile', 'pfile', 'input.profiles']
    for kind in candidates:
        key = next((k for k in aliases[kind] if k in input_nodes), None)
        if key is None:
            continue
        name = 'statefile.nc' if kind == 'statefile' else kind
        inputs = [(input_nodes[key], name)]
        command = 'profiles_gen -i ' + name
        gkey = next((k for k in ('gEQDSK', 'gfile') if k in input_nodes), None)
        if kind == 'pfile' and gkey is None:
            raise ValueError('pfile generation requires a gEQDSK/gfile input')
        if gkey is not None and kind != 'input.profiles':
            inputs.append((input_nodes[gkey], 'gfile'))
            command += ' -g gfile'
        return inputs, command
    raise ValueError('Load the selected statefile, pfile or input.profiles before generation')


defaultVars(profile_source=None)
inputs, command = prepare_profiles_input(root['INPUTS'], profile_source or root['SETTINGS']['PHYSICS'].get('start_from', None))
setup = root['SETTINGS']['SETUP']
workdir = setup['workDir']
environment = setup.get('profiles_environment', None) or setup.get('executable', '')
status_file = 'profiles_gen.exit'
log_file = 'profiles_gen.log'
geometry = ' -g ' in command
execution_command = 'bash .omfit_profiles_gen.sh' + command[len('profiles_gen'):] if geometry else command
executable = ('#!/bin/bash\nset -e\n'
              + 'trap \'status=$?; printf "%s\\n" "$status" > ' + status_file + "' EXIT\n"
              + 'exec > ' + log_file + ' 2>&1\n'
              + environment + '\n' + program_guard('profiles')
              + profiles_python_environment(geometry=geometry)
              + execution_command + '\n'
              + '[ -s input.gacode ] || { echo "profiles_gen did not generate input.gacode; see preceding errors." >&2; exit 1; }\n')
# Download diagnostics even when conversion fails, then validate both process
# status and the real output ourselves. Native missing-output checks otherwise
# replace Python tracebacks with an uninformative "input.gacode not found".
ret_code = OMFITx.executable(root, inputs=inputs, outputs=['input.gacode', log_file, status_file],
                            executable=executable, workdir=workdir, ignoreReturnCode=True)
status_path = os.path.join(workdir, status_file)
status = None
if os.path.isfile(status_path):
    with open(status_path) as stream:
        status = stream.read().strip()
log_path = os.path.join(workdir, log_file)
log_tail = ''
if os.path.isfile(log_path):
    with open(log_path, 'rb') as stream:
        stream.seek(max(0, os.path.getsize(log_path) - 8000))
        log_tail = stream.read().decode('utf-8', 'replace').strip()
diagnostics = OMFITtree()
diagnostics.update(dict(command=execution_command, requested_command=command, return_code=ret_code, exit_code=status,
                        log_path=log_path, log_tail=log_tail))
if os.path.isfile(log_path):
    diagnostics['log'] = OMFITascii(log_path).duplicate()
root['OUTPUTS']['Profiles_gen_diagnostics'] = diagnostics
output_path = os.path.join(workdir, 'input.gacode')
if ret_code != 0 or status != '0' or not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
    raise RuntimeError('profiles_gen failed: process exit={}, script exit={}.\nLog: {}'.format(
        ret_code, status if status is not None else 'missing', log_path)
        + ('\n' + log_tail if log_tail else '\nNo conversion log returned; check the server connection and environment setup.'))
generated = OMFITinputgacode(output_path)
generated.keys()
root['OUTPUTS'].setdefault('Profiles_gen', OMFITtree())['input.gacode'] = generated
root['Transfer_file']['input.gacode'] = generated.duplicate()
