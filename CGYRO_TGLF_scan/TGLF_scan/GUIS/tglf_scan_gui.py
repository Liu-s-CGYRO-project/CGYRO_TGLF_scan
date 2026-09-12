# -*-Python-*-
# Created by smithsp at 2013/11/07 15:41

OMFITx.TitleGUI('TGLF scan GUI')

root.setdefault('scanResults', OMFITtree())
root.setdefault('scanResults2D', OMFITtree())
root.setdefault('input.tglf', OMFITtree())
root.setdefault('tgyro_output', OMFITtree())

param = root['TGLF']['SETTINGS']['PHYSICS']['scanParameter']
param2 = root['TGLF']['SETTINGS']['PHYSICS']['scanParameter2D']


OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['tglf_input_load']",
    "Load input.tglf file - !load it before input.gacode!",
    default=False,
    updateGUI=True,
    help='This CheckBox oppens the GUI where the input.tglf file can be loaded. Click "Pick a different input.tglf file" to load a new file.',
)

OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['tglf_settings_from_TGYRO']",
    "Load TGLF settings tab from TGYRO GUI",
    default=False,
    updateGUI=True,
    help='This CheckBox loads the same GUI as in TGYRO module to specify TGLF settings, otherwise the old TGLF_scan GUI will be loaded.',
)

if not root['SETTINGS']['PHYSICS']['tglf_settings_from_TGYRO']:
    tglf_input_gui = root['TGLF']['GUIS']['TGLF_GUI']
    guis_loc = None  # this variable is not used in TGLF_GUI
    settings_loc_str = None
    inp_loc_tgyro_str = None
else:

    tglf_input_gui = root['TGLF']['GUIS']['TGLFfromTGYROgui']
    guis_loc = root['TGYRO']['GUIS']['TGLFinputGUI']
    settings_loc_str = treeLocation(root['TGYRO']['SETTINGS'])[-1]
    inp_loc_tgyro_str = treeLocation(root['TGYRO'])[-1]
    root['TGYRO']['SETTINGS']['PHYSICS']['Turb_Model'] = 'TGLF'


start_over = False
if 'input.gacode' in root['TGYRO']['PROFILES_GEN']['OUTPUTS'] or (
    'MULTI' in root['TGYRO']['PROFILES_GEN'] and len(root['TGYRO']['PROFILES_GEN']['MULTI'])
):

    def show_reset():
        OMFITx.Tab('Setup input profiles')
        if start_over:
            OMFITx.Button('Start over', "root['TGYRO']['PROFILES_GEN']['SCRIPTS']['reset']")
        else:
            OMFITx.CompoundGUI(root['TGYRO']['PROFILES_GEN']['GUIS']['standaloneGUI'])

    # setup
    if not len(root['input.tglf']):
        root['TGYRO']['INPUTS']['input.tglf']['USE_TRANSPORT_MODEL'] = True
        OMFITx.Tab("Setup TGLF input files")
        OMFITx.CompoundGUI(
            tglf_input_gui,
            inp_loc=treeLocation(root['TGYRO']['INPUTS']['input.tglf'])[-1],
            settings_loc_str=settings_loc_str,
            inp_loc_tgyro_str=inp_loc_tgyro_str,
            guis_loc=guis_loc,
            showLocalTab=False,
            showButtons=False,
            showNumSpecies=False,
        )
        if root['TGYRO']['PROFILES_GEN']['TRXPL']['SETTINGS']['EXPERIMENT']['multiwindow']:
            OMFITx.Button('Setup TGLF Inputs', "root['SCRIPTS']['setup_batch_tglf']")
        else:
            OMFITx.Button('Setup TGLF Inputs', "root['SCRIPTS']['setup_tglf']")
        show_reset()
        OMFITx.End()

    # -------------------------
    OMFITx.Tab('Run TGLF at specific radii')
    rho = root['SETTINGS']['PHYSICS']['rho']

    def show_single_rho():
        # make copy of experimental tglf input file
        def pick_rho(location=None):
            rho = eval(location)
            if 'input.tglf' in root and rho in root['input.tglf']:
                root['TGLF']['FILES']['input.tglf'] = copy.deepcopy(root['input.tglf'][rho])

        rad_lab = 'rho' if root['TGYRO']['INPUTS']['input.tgyro']['TGYRO_USE_RHO'] else 'r/a'
        OMFITx.ComboBox(
            "root['SETTINGS']['PHYSICS']['rho']",
            sorted(root['input.tglf'].keys()),
            'Radius (%s)' % rad_lab,
            default=0.5,
            updateGUI=True,
            state='normal',
            postcommand=pick_rho,
        )

    def show_tglf_detail():
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['show_TGLF_details']", lbl="Show TGLF details", default=False, updateGUI=True)
        if root['SETTINGS']['PHYSICS']['show_TGLF_details']:
            OMFITx.CompoundGUI(
                tglf_input_gui,
                inp_loc=treeLocation(root['input.tglf'][rho])[-1],
                guis_loc=guis_loc,
                showButtons=False,
                allowOptions=['TGLF', 'TGLF-NN'],
                title='',
                showLocalTab=False,
            )

    # -------------------------

    if rho in root['input.tglf']:
        OMFITx.ComboBox(
            "root['SETTINGS']['PHYSICS']['scanDimensions']",
            {'Radial': 0, '1D': 1, '2D': 2, 'UQ': 'UQ'},
            'Scan dimensions',
            default=0,
            updateGUI=True,
            state='readonly',
        )

    def showPlots():
        OMFITx.Separator()
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['plot_mks']", 'Plot fluxes in MKS units', default=True)
        OMFITx.CheckBox("root['TGLF']['SETTINGS']['PHYSICS']['combine_ions']", "Combine ions in plots", default=True)
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['tglf_sign_convention']", "Use TGLF Momentum Target Sign Convention", default=True)
        OMFITx.CheckBox("root['SETTINGS']['PLOTS']['Use_x_log']", "Plot x as log scale", default=True)
        OMFITx.CheckBox("root['SETTINGS']['PLOTS']['Use_y_log']", "Plot y as log scale", default=True)
        OMFITx.CheckBox("root['SETTINGS']['PLOTS']['Divided ky']", "Plot the data divided ky", default=True)
        OMFITx.Button('Plot %dD TGLF scan' % root['SETTINGS']['PHYSICS']['scanDimensions'], "root['PLOTS']['plotScanAtRho'].runNoGUI")
        if root['SETTINGS']['PHYSICS']['scanDimensions'] == 1:
            OMFITx.Button('Plot 1D TGLF scan spectra', "root['PLOTS']['plotScanSpecAtRho'].runNoGUI")
        OMFITx.Separator()
        OMFITx.Button(
            'Write %dD TGLF scan to file' % root['SETTINGS']['PHYSICS']['scanDimensions'],
            lambda: root['PLOTS']['plotScanAtRho'].runNoGUI(doSave=True),
        )

    def showUQPlots():
        OMFITx.Separator()
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['plot_mks']", 'Plot fluxes in MKS units', default=True)
        OMFITx.CheckBox("root['TGLF']['SETTINGS']['PHYSICS']['combine_ions']", "Combine ions in plots", default=True)
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['tglf_sign_convention']", "Use TGLF Momentum Target Sign Convention", default=True)
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['exp_prob']", "Plot experimental sub-window probabilities", default=False)
        OMFITx.Button(
            'Plot %dD TGLF scan UQ propagation' % root['TGLF']['SETTINGS']['PHYSICS']['scanDimensions'], "root['PLOTS']['plot_UQ'].runNoGUI"
        )

    # 1D scan
    if root['SETTINGS']['PHYSICS']['scanDimensions'] == 1 and rho in root['input.tglf']:
        start_over = True
        OMFITx.Tab("Run TGLF at specific radii")
        show_single_rho()
        show_tglf_detail()
        OMFITx.Tab('Scan')
        OMFITx.CompoundGUI(root['TGLF']['GUIS']['scanGUI'], showButtons=False, title='')
        OMFITx.Button('Run 1D TGLF scan', lambda: root['SCRIPTS']['runScanAtRho'].run(copy_inputTGLF_rho=False))

        if 'scanResults' in root and rho in root['scanResults'] and param in root['scanResults'][rho]:
            showPlots()

    # 2D scan
    elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 2 and rho in root['input.tglf']:
        start_over = True
        OMFITx.Tab("Run TGLF at specific radii")
        show_single_rho()
        show_tglf_detail()
        OMFITx.Tab('Scan')
        OMFITx.CompoundGUI(root['TGLF']['GUIS']['scan2DGUI'], showButtons=False, title='')
        OMFITx.Button('Run 2D TGLF scan at ' + str(rho), lambda: root['SCRIPTS']['runScanAtRho'].run(copy_inputTGLF_rho=False))
        if 'scanResults2D' in root and rho in root['scanResults2D'] and param2 + '+' + param in root['scanResults2D'][rho]:
            showPlots()

    # UQ scan
    elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 'UQ' and rho in root['input.tglf']:
        start_over = True
        OMFITx.Tab("Run TGLF at specific radii")
        show_single_rho()
        show_tglf_detail()
        OMFITx.Tab('UQ Scan')
        # Move rho information to TGLF submodule
        root['TGLF']['SETTINGS']['PHYSICS']['rho'] = root['SETTINGS']['PHYSICS']['rho']
        OMFITx.CompoundGUI(root['TGLF']['GUIS']['uqGUI'], showButtons=False, title='')
        uqparam = root['TGLF']['SETTINGS']['PHYSICS']['scanParameters']  # Gets set in uqGUI
        OMFITx.Button('Run TGLF UQ scan', lambda: root['SCRIPTS']['runScanAtRho'].run(copy_inputTGLF_rho=False))
        if 'UQResults' in root and rho in root['UQResults'] and '_'.join(uqparam) in root['UQResults'][rho]:
            showUQPlots()

    elif root['SETTINGS']['PHYSICS']['scanDimensions'] == 0:
        OMFITx.CompoundGUI(root['GUIS']['tglf_radial_gui'])

    show_reset()
else:
    # this ensures a reset of the scans if the inputs of PROFILES_GEN have changed
    # (PROFILES_GEN will clear the outputs if its inputs change)
    root['SCRIPTS']['reset'].runNoGUI()

    OMFITx.Tab('Setup input profiles')
    OMFITx.CompoundGUI(root['TGYRO']['PROFILES_GEN']['GUIS']['standaloneGUI'])

    if root['SETTINGS']['PHYSICS']['tglf_input_load']:
        inp_loc = "root['TGYRO']['INPUTS']['input.tglf']"

        OMFITx.ObjectPicker(inp_loc, lbl='input.tglf file', objectType=OMFITgacode)
