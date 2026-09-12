# -*-Python-*-
"""Generate profiles using the source selected by the Transfer GUI."""
import os


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


inputs, command = prepare_profiles_input(root['INPUTS'], root['SETTINGS']['PHYSICS'].get('start_from'))
setup = root['SETTINGS']['SETUP']
workdir = setup['workDir']
executable = setup.get('executable', '') + '\nset -e\ncommand -v profiles_gen >/dev/null\n' + command
ret_code = OMFITx.executable(root, inputs=inputs, outputs=['input.gacode'],
                            executable=executable, workdir=workdir, ignoreReturnCode=False)
if ret_code != 0:
    raise RuntimeError('profiles_gen failed with return code {}'.format(ret_code))
output_path = os.path.join(workdir, 'input.gacode')
if not os.path.isfile(output_path):
    raise RuntimeError('profiles_gen did not return input.gacode to the local work directory')
generated = OMFITinputgacode(output_path)
root['OUTPUTS'].setdefault('Profiles_gen', OMFITtree())['input.gacode'] = generated
root['Transfer_file']['input.gacode'] = generated.duplicate()
