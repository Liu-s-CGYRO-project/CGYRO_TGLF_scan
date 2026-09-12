# -*-Python-*-
# Created by sciortinof at 30 Jul 2019  16:18

"""
Secondary GUI to get frequency and growth rates scans + transport coefficient sensitivity to TGLF inputs.
"""

root.setdefault('TGLF_inputs_to_scan', {})

OMFITx.Label('Indicate TGLF inputs to scan over')

# set defaults:
def load_default_vars():
    root['TGLF_inputs_to_scan'] = {}
    root['TGLF_inputs_to_scan']['aLTe'] = '$a/L_{Te}$'
    root['TGLF_inputs_to_scan']['aLTi'] = '$a/L_{Ti}$'
    root['TGLF_inputs_to_scan']['XNUE'] = r'$\frac{\nu_{ei}}{c_s a}$'
    root['TGLF_inputs_to_scan']['aLn'] = '$a/L_{n}$'
    # root['TGLF_inputs_to_scan']['ZEFF']='$Z_{eff}$'
    # root['TGLF_inputs_to_scan']['vtor']='$v_{tor}$'
    root['TGLF_inputs_to_scan']['ALPHA_P'] = r'$\alpha_{p}$'
    root['TGLF_inputs_to_scan']['taus'] = '$T_i/T_e$'


if len(root['TGLF_inputs_to_scan']) == 0:
    # initial loading + prevents GUI from having no scan parameters at all
    load_default_vars()


if 'input.tglf' in root['TGLF']['FILES']:

    # Select more/different inputs from input.tglf to scan over.
    # To scan over groups of quantities together, make sure that group labels are recognized as for,e.g., aLn (see runGrowthRateScans)
    OMFITx.CompoundGUI(
        root['GUIS']['selection_GUI'],
        dictionary_to_read=root['TGLF']['FILES']['input.tglf'],
        dictionary_to_write='TGLF_inputs_to_scan',
        title='',
    )

else:
    OMFITx.Label('input.tglf not found. Set up TGLF for scans to read all possible scan options. Defaults: ', align='left')
    def_options = {k: 1 for k in root['TGLF_inputs_to_scan'].keys()}
    OMFITx.CompoundGUI(root['GUIS']['selection_GUI'], dictionary_to_read=def_options, dictionary_to_write='TGLF_inputs_to_scan', title='')


OMFITx.Label('')
OMFITx.Button("Reload default scan variables", load_default_vars, updateGUI=True)


OMFITx.Label('')
OMFITx.Label('')

# ==============================

OMFITx.Tab("Frequency scans")

OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['Var_r']", 'rho for growth rate scans: ', default=0.6, help='Radial location for growth rate scan'
)
OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['NMODES']", 'Number of TGLF modes to store: ', default=2, help='Dominant: 1; first subdominant: 2, etc.'
)

OMFITx.Label('')
OMFITx.Separator()

# Relative change to single variables
for v in root['TGLF_inputs_to_scan'].keys():  # root['SETTINGS']['PHYSICS']['scan_vars']:
    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['RelativeChange_%s']" % v,
        'Relative Change in %s' % v,
        default=0.2,
        help='Fractional uncertainty for the variable',
    )

OMFITx.Label('')
OMFITx.Separator()

# Run scans
OMFITx.Button(
    "Scan for growth rates",
    lambda: root['SCRIPTS']['runGrowthRateScans'].run(NMODES=root['SETTINGS']['PHYSICS']['NMODES']),
    updateGUI=False,
)

if 'scans' in root['TGLF_SCAN_DB']:
    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['plot_gamma_lims']",
        'Growth rate plot range',
        default=[None, None],
        help="Leave to [None,None] to have automatic ylims",
    )

    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['plot_mode_number']",
        'TGLF mode rank to plot',
        default=1,
        help='Dominant: 1; first subdominant: 2, etc.',
    )
    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['normalized_freq']",
        'Plot normalized growth rates ',
        default=True,
        updateGUI=False,
        help='Plotting growth rates normalized by ktheta*rhos helps assessing the importance of multiscale effects on transport',
    )
    OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['separate_freq_plot']", 'Separate real frequency plot ', default=False, updateGUI=True)
    if root['SETTINGS']['PHYSICS']['separate_freq_plot']:
        OMFITx.Entry(
            "root['SETTINGS']['PHYSICS']['plot_freq_lims']",
            'Real frequency plot range',
            default=[None, None],
            help="Leave to [None,None] to have automatic ylims",
        )

    OMFITx.Button(
        "Plot growth rates/frequencies scans",
        lambda: root['PLOTS']['plotGrowthRateScans'].run(
            normalized_freq=root['SETTINGS']['PHYSICS']['normalized_freq'],
            separate_freq_plot=root['SETTINGS']['PHYSICS']['separate_freq_plot'],
            plot_gamma_lims=root['SETTINGS']['PHYSICS']['plot_gamma_lims'],
            plot_freq_lims=root['SETTINGS']['PHYSICS']['plot_freq_lims']
            if root['SETTINGS']['PHYSICS']['separate_freq_plot']
            else [None, None],
        ),
        updateGUI=False,
    )


# ========================
# scan for impurity transport coefficients
OMFITx.Tab("Transport coefficients scans")

OMFITx.Label('NB: TGYRO will be used to get input.tglf files if species are modified from a previous run.', align='left')


def get_ion_list_short():
    ions = root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode']['IONS']
    ion_list = [ions[k][0] for k in ions.keys()]

    ion_list.insert(len(ion_list), root['SETTINGS']['PHYSICS']['impElement'])
    return ion_list


# specify impurity to be scanned
ions = root['TGYRO']['PROFILES_GEN']['OUTPUTS']['input.gacode']['IONS']
ion_list = [ions[k][0] for k in ions.keys()]
OMFITx.Label('Original Ion List:{}'.format(ion_list))
OMFITx.Label('Specify impurity for which transport coefficients should be found')

OMFITx.Entry("root['SETTINGS']['PHYSICS']['impElement']", 'Impurity Element', default='Ca', updateGUI=False)

# allow specification of particle charge in case one wants to study transport of partially-ionized species
OMFITx.Entry("root['SETTINGS']['PHYSICS']['impZ']", 'Impurity Charge (Z)', default=20, updateGUI=False)

try:
    atom = atomic_element(symbol=root['SETTINGS']['PHYSICS']['impElement'])
    M = atom[list(atom.keys())[0]]['mass']
    root['SETTINGS']['PHYSICS']['impM'] = M
except ValueError:
    raise OMFITexception('Atomic element symbol not recognized in DV_scans_subgui.py!')


OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['transport_matrix_method']",
    'Use matrix inversion method to obtain transport coefficients ',
    default=True,
    updateGUI=True,
    help="If checked, transport coefficients are computed via a matrix inversion, "
    "using a single TGLF run with multiple impurities rather than multiple runs with different inputs.",
)


if root['SETTINGS']['PHYSICS']['transport_matrix_method']:
    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['compute_thermodiffusion']",
        'Compute thermodiffusion',
        default=True,
        updateGUI=True,
        help="If checked, compute diffusion (D), thermodiffusion (vT) and the residual convection term (vp), rather than just D,v. ",
    )

    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['compute_rotodiffusion']",
        'Compute rotodiffusion',
        default=True,
        updateGUI=True,
        help="If checked, compute rotodiffusion (vR) as well as thermodiffusion (vT).",
    )


# display how many ions are expected to be included in TGLF runs, based on user choices above
OMFITx.Label('Ion list including new trace impurities:{}'.format(get_ion_list_short()))


def delete_rel_change_vars():
    '''Function used to update the default number of fields in 'RelativeChange_*_list' based on number of input radii'''
    for v in root['TGLF_inputs_to_scan'].keys():
        del root['SETTINGS']['PHYSICS']['RelativeChange_%s_list' % v]


# radial locations to scan:
OMFITx.Entry(
    "root['TGLF_SCAN_DB']['%s']['rhoList']" % root['SETTINGS']['PHYSICS']['runs_label'],
    'Radii (rho)',
    default=[0.6, 0.8],
    updateGUI=True,
    help='Radii at which to scan inputs to find transport coefficients sensitivity.',
    postcommand=lambda location=None: delete_rel_change_vars(),
)

# ========================
# User input for uncertainties for each variable at each location
for v in root['TGLF_inputs_to_scan'].keys():
    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['RelativeChange_%s_list']" % v,
        'Relative Change in %s at chosen radii' % v,
        default=[0.2] * len(root['TGLF_SCAN_DB'][root['SETTINGS']['PHYSICS']['runs_label']]['rhoList']),
        updateGUI=True,
        help='Indicate local uncertainty at each radius. This list must be as long as the number of radii!',
    )

# =======================
# Run D,V scan
OMFITx.Button("Scan for transport coefficients", "root['SCRIPTS']['DVscan'].run", updateGUI=False)
OMFITx.Label('')
OMFITx.Separator()
OMFITx.Label('')

# =========================

if (
    'D_and_v_' + root['SETTINGS']['PHYSICS']['runs_label'] in root['TGLF_SCAN_DB']
    and 'D' in root['TGLF_SCAN_DB']['D_and_v_' + root['SETTINGS']['PHYSICS']['runs_label']]
):  # check that transport coefficients have been saved

    # set defaults:
    root.setdefault('scan_vars_to_plot', {})
    root['SETTINGS']['PHYSICS'].setdefault('plot_STRAHL_corrections', True)
    root['SETTINGS']['PHYSICS'].setdefault('plot_normalized_coeffs', False)

    def load_default_DV_plot_vars():
        root['scan_vars_to_plot'] = {}
        if root['SETTINGS']['PHYSICS']['plot_STRAHL_corrections']:
            extra_str = '_corr'
        else:
            extra_str = ''

        if root['SETTINGS']['PHYSICS']['compute_thermodiffusion']:
            root['scan_vars_to_plot']['D' + extra_str] = '$D [m^2/s]$'
            root['scan_vars_to_plot']['v' + extra_str] = '$v_p [m/s]$'
            root['scan_vars_to_plot']['vT' + extra_str] = '$v_T [m/s]$'
            root['scan_vars_to_plot']['vtot_D' + extra_str] = '$v_{tot}/D [1/m]$'
        else:
            root['scan_vars_to_plot']['D' + extra_str] = '$D [m^2/s]$'
            root['scan_vars_to_plot']['v' + extra_str] = '$v [m/s]$'
            root['scan_vars_to_plot']['v_D' + extra_str] = '$v/D$ [1/m]'

    # Select quantities to plot, also indicating labels:
    OMFITx.Label('Indicate scan output variables to be plotted')
    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['plot_STRAHL_corrections']",
        'Include STRAHL-like corrections to all transport coefficients',
        default=True,
        updateGUI=True,
        help='Apply corrections to transport coefficients that allow comparison with STRAHL. These account for poloidal asymmetries and different radial coordinates',
        postcommand=lambda location=None: load_default_DV_plot_vars(),
    )
    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['plot_normalized_coeffs']",
        'Plot transport coefficients normalized by chi_i',
        default=False,
        updateGUI=False,
    )

    if len(root['scan_vars_to_plot']) == 0:
        load_default_DV_plot_vars()

    OMFITx.Button("Reload default scan variables to plot", load_default_DV_plot_vars, updateGUI=True)

    OMFITx.CompoundGUI(
        root['GUIS']['selection_GUI'],
        dictionary_to_read=root['TGLF_SCAN_DB']['D_and_v_' + root['SETTINGS']['PHYSICS']['runs_label']],
        dictionary_to_write='scan_vars_to_plot',
        title='',
    )

    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['shade_DV']",
        'Shadow over D,V range ',
        default=True,
        updateGUI=True,
        help="Color plot between up and down scans. This is a purely graphical effect to better show sensitivity ranges.",
    )

    OMFITx.Button("Plot D,V scans", lambda: root['PLOTS']['plot_DV_scan'].run(), updateGUI=False)
