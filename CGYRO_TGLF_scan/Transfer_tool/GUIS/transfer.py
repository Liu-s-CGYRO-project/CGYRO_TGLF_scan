# -*-Python-*-
"""Transfer inputs and run only workflows present in this module."""
OMFITx.TitleGUI('Transfer files')
physics = root['SETTINGS']['PHYSICS']
physics.setdefault('start_from', 'statefile')


def load_profile(location=None):
    kind = root['SETTINGS']['PHYSICS']['start_from']
    filename = scratch.get('profile_filename', '')
    if not filename:
        return
    readers = {'statefile': OMFITnc, 'pfile': OMFITpFile,
               'input.profiles': OMFITgacode, 'input.gacode': OMFITinputgacode}
    root['INPUTS'][kind] = readers[kind](filename)
    if kind == 'input.gacode':
        root['Transfer_file']['input.gacode'] = root['INPUTS'][kind].duplicate()


def load_equilibrium(location=None):
    filename = scratch.get('equilibrium_filename', '')
    if filename:
        root['INPUTS']['gEQDSK'] = OMFITgeqdsk(filename)


def load_conversion_inputs(location=None):
    # Each picker replaces only its requested input, preserving the other files.
    for key in ('input.cgyro', 'input.tglf', 'input.gacode'):
        filename = scratch.get('convert_' + key, '')
        if filename:
            reader = OMFITinputgacode if key == 'input.gacode' else OMFITgacode
            root['Transfer_file'][key] = reader(filename)
            scratch['convert_' + key] = ''


def generate_profiles(location=None):
    root['SCRIPTS']['profiles_gen.py'].run()


def convert_inputs(location=None):
    root['SCRIPTS']['convert_file'].run()


OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['start_from']",
               {'Statefile': 'statefile', 'p-file': 'pfile',
                'input.profiles': 'input.profiles', 'input.gacode': 'input.gacode'},
               lbl='Profile source', default='statefile', updateGUI=True)
if physics['start_from'] not in ('statefile', 'pfile', 'input.profiles', 'input.gacode'):
    physics['start_from'] = 'input.gacode'
OMFITx.FilePicker("scratch['profile_filename']", 'Profile input', default='',
                  updateGUI=True, postcommand=load_profile)
if physics['start_from'] in ('statefile', 'pfile'):
    OMFITx.FilePicker("scratch['equilibrium_filename']", 'Equilibrium g-file', default='',
                      updateGUI=True, postcommand=load_equilibrium)
if physics['start_from'] != 'input.gacode':
    OMFITx.Button('Generate input.gacode', generate_profiles, updateGUI=True)

OMFITx.Label('Local parameter conversion: load the relevant inputs, select one direction, then convert.')
for key in ('input.cgyro', 'input.tglf', 'input.gacode'):
    OMFITx.FilePicker("scratch['convert_" + key + "']", key, default='',
                      updateGUI=True, postcommand=load_conversion_inputs)
OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['Transfer to cgyro']", 'TGLF → CGYRO', default=True)
OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['Transfer to tglf']", 'CGYRO → TGLF', default=False)
OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['tglf_is_out_tglf_localdump']",
                'TGLF input is out.tglf.localdump', default=False)
OMFITx.Button('Convert local inputs', convert_inputs, updateGUI=True)
OMFITx.Label('NEO / ion ordering is available in the parent main → PROFILES_GEN GUI.')
