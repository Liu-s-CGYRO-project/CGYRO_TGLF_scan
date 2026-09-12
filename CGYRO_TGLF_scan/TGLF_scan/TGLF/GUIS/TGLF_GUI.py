# -*-Python-*-
# Created by smithsp at 02 Sep 2015  21:39

OMFITx.TitleGUI('TGLF GUI')

defaultVars(
    inp_loc="root['FILES']['input.tglf']",
    guis_loc=None,
    settings_loc_str=None,  # need this only for TGLF settings from TGYRO GUI
    inp_loc_tgyro_str=None,
    showButtons=True,
    allowOptions=['TGLF', 'TGLF-NN', 'wavefunction'],
    showLocalTab=True,
    showNumSpecies=True,
)
try:
    input_tglf = eval(inp_loc)
except Exception:
    OMFITx.ObjectPicker(inp_loc, lbl='input.tglf file', objectType=OMFITgacode)
    OMFITx.End()
if 'USE_TRANSPORT_MODEL' not in input_tglf:
    OMFITx.Label("This GUI is only valid for a TGLF input file (usually named input.tglf)")
    OMFITx.End()

options = {
    'TGLF-NN': ("Get fluxes with neural-network model", [True, 1e6]),
    'TGLF': ("Get growth rate spectra and fluxes", [True, -1.0]),
    'wavefunction': ("Get wavefunction at set ky", [False, -1.0]),
}

OMFITx.ComboBox(
    [inp_loc + "['USE_TRANSPORT_MODEL']", inp_loc + "['NN_MAX_ERROR']"],
    {options[k][0]: options[k][1] for k in allowOptions},
    "TGLF mode",
    updateGUI=True,
    default=[True, -1.0],
)

if eval(inp_loc + "['USE_TRANSPORT_MODEL']") and eval(inp_loc + "['NN_MAX_ERROR']") > 0:
    for item in root['TEMPLATES']['input.tglf.nn']:
        OMFITx.Lock(inp_loc + "['%s']" % str(item), root['TEMPLATES']['input.tglf.nn'][item])


# GEOMETRY_FLAG tglf_geometry_flag_in geometry type (0=-, 1=Miller, 2=Fourier, 3=ELITE) 1
OMFITx.Tab("Physics Controls")
if showNumSpecies:
    OMFITx.Entry(inp_loc + "['NS']", lbl="Number of species including both electrons and ions", default=2, check=is_int, updateGUI=True)
OMFITx.CheckBox(inp_loc + "['USE_BPER']", lbl="Include transverse magnetic fluctuations (A_||)", default=True)
OMFITx.CheckBox(inp_loc + "['USE_BPAR']", lbl="Include compressional magnetic fluctuations (B_||)", default=True)
OMFITx.CheckBox(inp_loc + "['USE_MHD_RULE']", lbl="Ignore pressure gradient contribution to curvature drift (Phi)", default=False)
OMFITx.CheckBox(inp_loc + "['ADIABATIC_ELEC']", lbl="Use adiabatic electrons", default=False)
OMFITx.ComboBox(
    inp_loc + "['SAT_RULE']",
    {'0': 0, '1': 1, '2': 2},
    lbl="Saturation rule",
    updateGUI=True,
    default=1,
    help='''SAT0 - Spectral shift [Staebler 2013] and quasilinear weights from GYRO [Staebler 2007].
SAT1 - Spectral shift [Staebler 2013] and quasilinear weights from multiscale GYRO [Staebler 2017] or CGYRO [Staebler 2021].
SAT2 - Spectral shift [Staebler 2013] new collision model and quasilinear weights from CGYRO [Staebler 2021].''',
)
# These are deprecated parameters:
# OMFITx.Entry(inp_loc+"['XNU_MODEL']",
#  lbl="Collision model (2=new)",default=2,check=is_int)
# OMFITx.Entry(inp_loc+"['VPAR_MODEL']",
#  lbl="VPAR_MODEL (0=low-Mach-number limit)",default=0)
OMFITx.ComboBox(
    inp_loc + "['ALPHA_QUENCH']",
    {"Use quench rule": 1.0, "Use new spectral shift model": 0.0},
    lbl="Quench rule",
    default=0.0,
)
OMFITx.ComboBox(inp_loc + "['SIGN_BT']", [1, -1], lbl="Sign of Bt with respect to CCW toroidal direction from top", default=1)
OMFITx.ComboBox(inp_loc + "['SIGN_IT']", [1, -1], lbl="Sign of It with respect to CCW toroidal direction from top", default=1)

OMFITx.Tab("Numerical Controls")
OMFITx.CheckBox(inp_loc + "['USE_BISECTION']", lbl="Use bisection search method to find width that maximizes growth rate", default=True)
# Not relevant
# OMFITx.CheckBox(inp_loc+"['NEW_EIKONAL']",
#  lbl="Recompute the eikonal, (unclicking means to use the eikonal computed "
#  "on the last call to TGLF made with NEW_EIKONAL set)", default=True)
OMFITx.CheckBox(inp_loc + "['IFLUX']", lbl="Compute quasilinear weights and mode amplitudes", default=True)


def check_nky(s):
    if not is_int(s):
        return False
    maxky0 = 480
    if s > maxky0:
        printe('For the user defined ky spectrum, the max number of NKY is ' + str(maxky0))
        return False
    else:
        return True


if not input_tglf['USE_TRANSPORT_MODEL']:
    OMFITx.Entry(inp_loc + "['KY']", "k_y for single-mode call to TGLF", default=0.3)
else:
    OMFITx.ComboBox(
        inp_loc + "['KYGRID_MODEL']",
        {"Standard ky spectrum for transport model": 1, "User defined with NKY modes up to KY equal spaced": 0},
        lbl='ky Grid Model',
        default=1,
        updateGUI=True,
    )
    if input_tglf['KYGRID_MODEL'] == 0:
        OMFITx.Entry(inp_loc + "['KY']", lbl="Max KY for user defined KY grid", default=0.3)
        OMFITx.Entry(inp_loc + "['NKY']", lbl="Number of KY for user defined KY grid", default=12, check=check_nky)
    else:
        OMFITx.Entry(inp_loc + "['NKY']", lbl="Number of poloidal modes in the high-k spectrum of TGLF_TM", default=12, check=is_int)

    def set_nky(location=None):
        if location is None:
            return
        ibranch = eval(location)
        if ibranch in [-1]:
            input_tglf['NMODES'] = 2

    OMFITx.ComboBox(
        inp_loc + "['IBRANCH']",
        {
            "Find two most unstable modes; one for each sign of frequency": 0,
            # Remove these two options, because TGLF does not seem to do as directed
            # "Find most unstable positive frequency mode (electron drift direction)":1,
            # "Find most unstable negative frequency mode (ion drift direction)":2,
            "Sort the unstable modes by growthrate in rank order": -1,
        },
        lbl="Which modes?",
        default=-1,
        updateGUI=True,
        postcommand=set_nky,
    )
    if input_tglf['IBRANCH'] == -1:
        OMFITx.Entry(inp_loc + "['NMODES']", lbl="Number of unstable modes to store", default=2, check=is_int)
# Note to self, add NMODES =2 for ibranch=0 for linear run, check for ibranch behavior

OMFITx.Entry(inp_loc + "['NBASIS_MIN']", lbl="Minimum number of parallel basis functions", default=2, check=is_int)
OMFITx.Entry(inp_loc + "['NBASIS_MAX']", lbl="Maximum number of parallel basis functions", default=4, check=is_int)
OMFITx.Entry(inp_loc + "['NXGRID']", lbl="Number of nodes in Gauss-Hermite quadrature", default=16, check=is_int)

# Convert to on/off
OMFITx.Tab("Physics Switches")
OMFITx.CheckBox(inp_loc + "['ALPHA_P']", lbl="Include parallel velocity shear for all species", default=1.0, mapFalseTrue=[0.0, 1.0])
OMFITx.CheckBox(inp_loc + "['ALPHA_E']", lbl="Include ExB velocity shear for spectral shift model", default=1.0, mapFalseTrue=[0.0, 1.0])
OMFITx.CheckBox(
    inp_loc + "['XNU_FACTOR']",
    lbl="Include the trapped/passing boundary electron-ion collision terms",
    default=1.0,
    mapFalseTrue=[0.0, 1.0],
)
OMFITx.CheckBox(inp_loc + "['DEBYE_FACTOR']", lbl="Include the Debye length term", default=1.0, mapFalseTrue=[0.0, 1.0])

if showLocalTab:
    OMFITx.Tab("Local parameters")
    OMFITx.Entry(
        inp_loc + "['VEXB_SHEAR']",
        lbl="Normalized toroidal ExB velocity Doppler shift gradient common to all " "species. For large ExB velocity ordering",
        default=0.0,
    )
    OMFITx.Entry(inp_loc + "['BETAE']", lbl='Beta_e defined with respect to B_unit', default=0.0)
    OMFITx.Entry(inp_loc + "['XNUE']", lbl='Electron-ion collision frequency / (c_s/a)', default=0.0)
    OMFITx.Entry(inp_loc + "['ZEFF']", lbl='Effective ion charge (Zeff)', default=1.0)
    OMFITx.Entry(inp_loc + "['DEBYE']", lbl='Debye length/gyroradius', default=0.0)
    OMFITx.ComboBox(
        "scratch['tglf_species_num']", list(range(1, input_tglf['NS'] + 1)) + ['all'], lbl='Show which species', default=1, updateGUI=True
    )
    if scratch['tglf_species_num'] == 'all':
        spec_nums = list(range(1, input_tglf['NS'] + 1))

    else:
        spec_nums = [scratch['tglf_species_num']]
    for spec_num in spec_nums:
        OMFITx.Entry(inp_loc + "['ZS_%s']" % spec_num, lbl="Species #%s Charge number (Z)" % spec_num, default=1)
        OMFITx.Entry(inp_loc + "['MASS_%s']" % spec_num, lbl="Species #%s Mass / Deuterium Mass" % spec_num, default=1)
        OMFITx.Entry(inp_loc + "['RLNS_%s']" % spec_num, lbl="Species #%s Normalized density gradient -(a/n)(dn/dr)" % spec_num, default=1)
        OMFITx.Entry(
            inp_loc + "['RLTS_%s']" % spec_num, lbl="Species #%s Normalized temperature gradient -(a/n)(dT/dr)" % spec_num, default=3
        )
        OMFITx.Entry(inp_loc + "['TAUS_%s']" % spec_num, lbl="Species #%s Temperature / Te" % spec_num, default=1)
        OMFITx.Entry(inp_loc + "['AS_%s']" % spec_num, lbl="Species #%s Density / ne" % spec_num, default=1)
        OMFITx.Entry(
            inp_loc + "['VPAR_%s']" % spec_num, lbl="Species #%s Parallel velocity sign(It)(R_maj V_tor/R)(a/c_s)" % spec_num, default=0
        )
        OMFITx.Entry(
            inp_loc + "['VPAR_SHEAR_%s']" % spec_num,
            lbl="Species #%s Parallel velocity shear -sign(It)R_maj(d/dr(V_tor/R))(a/c_s)" % spec_num,
            default=0,
        )

# Provide means of scaling one variable with another
OMFITx.Tab("Constraints")
OMFITx.CompoundGUI(root['GUIS']['constraints_GUI'], input_tglf=input_tglf, title='')

if showButtons:
    # Run
    OMFITx.Tab("")
    OMFITx.Separator()
    if input_tglf['USE_TRANSPORT_MODEL']:
        OMFITx.Button("Run TGLF to get fluxes", "root['SCRIPTS']['runTGLF']")
        if 'eigenvalue_spectrum' in root['FILES']:
            OMFITx.Button("Plot eigenvalue spectra", "root['FILES']['eigenvalue_spectrum'].plotFigure")
            OMFITx.Button("Plot discrete spectra", "root['PLOTS']['plotSpectrumDiscrete']")
    else:
        OMFITx.Button("Run TGLF to get wavefunction", "root['SCRIPTS']['runTGLFlinear']")
        if 'wavefunction' in root['FILES']:
            OMFITx.Button("Plot wavefunctions", "root['FILES']['wavefunction'].plot")
