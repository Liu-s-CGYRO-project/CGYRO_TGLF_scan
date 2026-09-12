# -*-Python-*-
# Created by meneghini at 2014/03/20 14:58

OMFITx.TitleGUI('NEO GUI')

defaultVars(showRunButton=False, allowEPED=False)

# ----------------
# Sorting of ions
# ----------------
import OMFITlib_profilesgen

numd_ion_names = OMFITlib_profilesgen.numd_ion_names()

options = SortedDict()
if len(numd_ion_names):
    options['Start over'] = nan
else:
    options['(leave unchanged -- TIP: run w/o NEO option to quickly find out ions order)'] = None
if len(numd_ion_names) and len(numd_ion_names) < 5:
    for k in itertools.permutations(numd_ion_names):
        options[str(list(k))] = list(k)
OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['reorder_ion_names']",
    options,
    lbl='Reorder Ions',
    updateGUI=True,
    state='normal',
    postcommand=root['SCRIPTS']['reorder_ions'].runNoGUI,
)

if EPED is not None and allowEPED and 'PROFILES' in EPED and len(EPED['PROFILES']) > 1:
    OMFITx.Tab('EPED')
    OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['blendEPED']", "blend with EPED", updateGUI=True)
    if root['SETTINGS']['PHYSICS']['blendEPED']:
        OMFITx.CompoundGUI(root['GUIS']['blendEPEDgui'], '')

    OMFITx.Tab('NEO')


state = None
if 'input.gacode' in root['OUTPUTS']:
    if not sum(root['OUTPUTS']['input.gacode']['omega0']):
        state = "NOTE: input.gacode has no rotation profiles: run NEO to calculate one"
    else:
        state = "NOTE: input.gacode already has a rotation profile"


OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['calcEr']",
    "run NEO",
    state,
    updateGUI=True,
    help='Calculates Er, vtor, vpol, angrot, Jbt when choose to run NEO',
)

if root['SETTINGS']['PHYSICS']['start_from'] == 'statefile' and 'prad' in profpowbal and np.any(profpowbal['prad']['data'] > 0):
    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['removeHighZimpRad']",
        "Account for measured radiated power from TRANSP",
        default=False,
        updateGUI=False,
        help='Subtract radiated power in excess of calculated D and C radiation from the electron heating power',
    )

if root['SETTINGS']['PHYSICS']['calcEr']:
    model_options = {'Sauter': 0, 'Full NEO calculation': 2, 'Redl et al. (2021) analytic model': 5}
    OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['sim_model']", model_options, 'Simulation model')
    options = SortedDict()
    options[''] = None
    options['Low res'] = [15, 4, [17, 39]]
    options['High res (slow)'] = [17, 6, [17, 39]]
    # 1) a standard low res case: N_XI=15, N_ENERGY=4, N_SPECIES=3 (no beams) -- this option is more reasonable for running data analysis, e.g. with kinetic EFIT, etc.
    # 2) a high res case: N_XI=17, N_ENERGY=6, with or without beams -- this option -- this option is really better for "publication quality" research, particularly showing only the neo results
    def setPresets(location=None):
        if scratch['presets']:
            (
                root['SETTINGS']['PHYSICS']['vgen_N_XI'],
                root['SETTINGS']['PHYSICS']['vgen_N_ENERGY'],
                root['SETTINGS']['PHYSICS']['vgen_N_THETA'],
            ) = scratch['presets']
            scratch['presets'] = None

    OMFITx.ComboBox("scratch['presets']", options, 'Preset resolutions', postcommand=setPresets, default=None, updateGUI=True)
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['vgen_N_XI']", 'Pitch angle resolution (XI)')
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['vgen_N_ENERGY']", 'Energy resolution')
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['vgen_N_THETA']", 'min/max poloidal angle resolution (THETA)')

    # -----------------------
    # neglect last # of ions
    # -----------------------
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['neglect_last_ions']", 'Do not include last # of ions', default=0)
    rot_model_opts = SortedDict()
    rot_model_opts['Default'] = None
    rot_model_opts['Strong'] = 2
    rot_model_opts['Weak'] = 1
    help_txt = '''vel flag for vgen
Default: Strong rotation ordering (-vel 2) if CERFile is provided, weak (-vel 1) if not
Strong: Force strong rotation ordering (-vel 2)
Weak: Force weak rotation ordering (-vel 1)'''
    OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['rotation_ordering']", rot_model_opts, 'Rotation ordering', default=None, help=help_txt)
OMFITx.Tab('')

if not compoundGUI or showRunButton:
    txt = ['run PROFILES_GEN']
    if EPED is not None and allowEPED and 'OUTPUTS' in EPED and 'eped' in EPED['OUTPUTS'] and root['SETTINGS']['PHYSICS']['blendEPED']:
        txt.append('blend EPED')
    if root['SETTINGS']['PHYSICS']['calcEr']:
        txt.append('run NEO')
    # PV edit - adding multi subwindow capability
    if root['TRXPL']['SETTINGS']['EXPERIMENT']['multiwindow']:
        OMFITx.Button('  >  '.join(txt) + ' (MULTI)', root['SCRIPTS']['batch_profiles_gen'])
    else:
        OMFITx.Button('  >  '.join(txt), root['SCRIPTS']['run_profiles_gen'])

if len(root['OUTPUTS']):
    OMFITx.Separator()

what = []
if 'jboot' in root['OUTPUTS']:
    what += ['Jboot']
if 'Er' in root['OUTPUTS']:
    what += ['Er']
if 'input.gacode' in root['OUTPUTS']:
    what += ['Vpol']
if len(what):
    OMFITx.ComboBox(
        "scratch['plotUsePSI']", {'rho': 0, 'psi': 1}, 'Plot ' + ' and '.join(what) + ' as function of', default=0, updateGUI=True
    )
    with OMFITx.same_row():
        OMFITx.Label('Plot')
        if 'jboot' in root['OUTPUTS']:
            OMFITx.Button(
                'bootstrap current models',
                lambda: root['PLOTS']['plot_quantities'].plotFigure(quantity='Jboot', rho_name=['rho', 'psi'][scratch['plotUsePSI']]),
            )

        if 'Er' in root['OUTPUTS']:
            OMFITx.Button(
                'radial electric field',
                lambda: root['PLOTS']['plot_quantities'].plotFigure(quantity='Er', rho_name=['rho', 'psi'][scratch['plotUsePSI']]),
            )

        if 'input.gacode' in root['OUTPUTS']:
            OMFITx.Button(
                'poloidal velocities',
                lambda: root['PLOTS']['plot_quantities'].plotFigure(quantity='Vpol', rho_name=['rho', 'psi'][scratch['plotUsePSI']]),
            )

with OMFITx.same_row():
    if 'input.gacode' in root['OUTPUTS']:
        OMFITx.Label('Plot GACODE')
        OMFITx.Button('input.gacode', "root['OUTPUTS']['input.gacode'].plotFigure")
        if gEQDSK is not None:
            OMFITx.Button('Overlay geometry to gEQDSK', "root['PLOTS']['gEQDSKoverlay'].plotFigure")
