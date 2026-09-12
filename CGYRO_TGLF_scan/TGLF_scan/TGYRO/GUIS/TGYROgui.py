# -*-Python-*-
# Created by meneghini at 2013/05/06 11:49
OMFITx.TitleGUI('TGYRO GUI')

if not compoundGUI and input_gacode is None:
    OMFITx.CompoundGUI(PROFILES_GEN['GUIS']['standaloneGUI'])
    OMFITx.End()


def no_spaces(x):
    if re.findall(r'[\s,/,\\,(,)]', x):
        return False
    return True


OMFITx.ComboBox(
    "root['SETTINGS']['EXPERIMENT']['runid']",
    list(root['RUN_DB'].keys()),
    'Simulation run-ID',
    postcommand=lambda location=None: root['SCRIPTS']['reloadTGYRO'].runNoGUI(),
    updateGUI=True,
    state='normal',
    check=no_spaces,
)

OMFITx.Tab('Run TGYRO')
OMFITx.CompoundGUI(root['GUIS']['Rungui'], '')

if 'input.gacode' in root['OUTPUTS'] or 'output' in root['OUTPUTS']:
    OMFITx.Tab('Plot results')
    OMFITx.CompoundGUI(root['GUIS']['Plotgui'], '')

    OMFITx.Tab('D&v profiles')
    OMFITx.CompoundGUI(root['GUIS']['D_and_v_gui'], '')

if 'input.gacode' in root['OUTPUTS']:
    OMFITx.Tab('Export')
    OMFITx.Separator()

    def ip_2_ods():
        root['OUTPUTS']['ods'] = root['OUTPUTS']['input.gacode'].to_omas()

    OMFITx.Button("Generate ODS from input.gacode", ip_2_ods)

    OMFITx.Separator('IMAS')
    OMFITx.ComboBox(
        "scratch['serverPicker']",
        {'ITER IMAS': 'iter_login', 'GATEWAY IMAS': 'itm_gateway'},
        'Server',
        default='iter_login',
        help='IMAS server',
    )
    OMFITx.Entry("scratch['machine']", 'Machine', default=root['SETTINGS']['EXPERIMENT']['device'], help='IMAS machine')
    OMFITx.Entry("scratch['pulse']", 'Pulse', check=is_int, default=root['SETTINGS']['EXPERIMENT']['shot'], help='IMAS pulse')
    OMFITx.Entry("scratch['run']", 'Run', check=is_int, default=root['SETTINGS']['EXPERIMENT']['time'], help='IMAS run')

    def ip_2_ids():
        if 'ods' not in root['OUTPUTS']:
            root['OUTPUTS']['ods'] = root['OUTPUTS']['input.gacode'].to_omas()
        for item in root['OUTPUTS']['ods']:
            if 'time' not in root['OUTPUTS']['ods']:
                root['OUTPUTS']['ods'][item]['time'] = [0.0]
        save_omas_imas_remote(
            scratch['serverPicker'],
            root['OUTPUTS']['ods'],
            pulse=scratch['pulse'],
            machine=scratch['machine'],
            run=scratch['run'],
            new=True,
        )

    e = OMFITx.Button('Save to IMAS', ip_2_ids, help='Choose a shot/run/device to export data to a IMAS database.')
