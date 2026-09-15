# -*-Python-*-
# Modified by pvaezi at 2018/01/10 12:29
# Original script by meneghini

import chaospy as cp

OMFITx.TitleGUI('TGLF 不确定度分析')

defaultVars(showButtons=True, show_constraints=True)

s = r'''NS tglf_ns_in number of species including both electrons and ions 2
USE_TRANSPORT_MODEL tglf_use_transport_model_in .true.
GEOMETRY_FLAG tglf_geometry_flag_in geometry type (0=s-?, 1=Miller, 2=Fourier, 3=ELITE) 1
USE_BPER tglf_use_bper_in include transverse magnetic fluctuations, \delta A_\lVert .false.
USE_BPAR tglf_use_bpar_in include compressional magnetic fluctuations, \delta B_\lVert .false.
USE_BISECTION tglf_use_bisection_in use bisection search method to find width that maximizes growth rate .true.
USE_MHD_RULE tglf_use_mhd_rule_in ignore pressure gradient contribution to curvature drift .true.
SAT_RULE tglf_sat_rule_in 0=default saturation rule 0
KYGRID_MODEL tglf_kygrid_model_in 1=standard ky spectrum for transport model, 0=user defined with NKY modes up to KY equal spaced 1
XNU_MODEL tglf_xnu_model_in Collision model (2=new) 2
VPAR_MODEL tglf_vpar_model_in 0=low-Mach-number limit 0
VPAR_SHEAR_MODEL tglf_vpar_shear_model_in depricated parameter 0
SIGN_BT tglf_sign_bt_in sign of BT with repsect to CCW toroidal direction from top 1.0
SIGN_IT tglf_sign_it_in sign of IT with repsect to CCW toroidal direction from top 1.0
KY tglf_ky_in k_\theta \rho_{s,{\rm unit}}\,\! for single-mode call to TGLF 0.3
NEW_EIKONAL tglf_new_eikonal_in .true. = compute the eikonal, .false. = use the eikonal computed on the last call to TGLF made with tglf_new_eikonal_in = .true. .true.
VEXB tglf_vexb_in normalized of ExB velocity Doppler shift common to all species (not in use, see VPAR) 0.0
VEXB_SHEAR tglf_vexb_shear_in normalized toroidal ExB velocity Doppler shift gradient common to all species. For large ExB velocity ordering Vtor = VExB -SIGN(I_{tor})\frac{r}{ABS(q)} \frac{\partial}{\partial r} (\frac{V_{ExB}}{R})\frac{a}{c_s} 0.0
BETAE tglf_betae_in \beta_e\,\! defined with respect to B_{\rm unit}\,\! 0.0
XNUE tglf_xnue_in electron-ion collision frequency \frac{v_{ei}}{c_s/a} 0.0
ZEFF tglf_zeff_in effective ion charge 1.0
DEBYE tglf_debye_in Debye length/gyroradius 0.0
IFLUX tglf_iflux_in compute quasilinear weights and mode amplitudes .true.
IBRANCH tglf_ibranch_in 0 = find two most unstable modes one for each sign of frequency, 1 = find most unstable positive frequency modes (ion drift direction), 2 = find most unstable negative frequency mode (ion drift direction), -1 = sort the unstable modes by growthrate in rank order -1
NMODES tglf_nmodes_in number of modes to store for tglf_ibranch_in = -1 2
NBASIS_MAX tglf_nbasis_max_in maximum number of parallel basis functions 4
NBASIS_MIN tglf_nbasis_min_in minimum number of parallel basis functions 1
NXGRID tglf_nxgrid_in number of nodes in Gauss-Hermite quadrature 16
NKY tglf_nky_in number of poloidal modes in the high-k spectrum of TGLF_TM 12
ADIABATIC_ELEC tglf_adiabatic_elec_in use adiabatic electrons .false.
ALPHA_P tglf_alpha_p_in multiplies parallel velocity shear for all species 1.0
ALPHA_E tglf_alpha_e_in multiplies ExB velocity shear for spectral shift model 1.0
ALPHA_QUENCH tglf_alpha_quench_in 1.0 = use quench rule, 0.0 = use new spectral shift model 0.0
XNU_FACTOR tglf_xnu_factor_in multiplies the trapped/passing boundary electron-ion collision terms 1.0
DEBYE_FACTOR tglf_debye_factor_in multiplies the debye length 1.0
ETG_FACTOR tglf_etg_factor_in exponent for ETG saturation rule 1.25
WRITE_WAVEFUNCTION_FLAG tglf_write_wavefunction_flag_in Self-explanatory 0
WIDTH tglf_width_in maximum width of the Gaussian measure for the parallel Hermite polynomial basis 1.65
WIDTH_MIN tglf_width_min_in minimum width used in search for maximum growth rate 0.3
NWIDTH tglf_nwidth_in maximum number of widths used in search for maximum growth rate 21
FIND_WIDTH tglf_find_width_in .true. = find the width that maximizes the growth rate, .false. = use width .true.
RMIN_LOC tglf_rmin_loc_in flux surface centroid minor radius r/a\,\! 0.5
RMAJ_LOC tglf_rmaj_loc_in flux surface centroid major radius R_{maj}/a\,\! 3.0
ZMAJ_LOC tglf_zmaj_loc_in flux surface centroid elevation Z_{maj}/a\,\! 0.0
Q_LOC tglf_q_loc_in absolute value of the safety factor, ABS(q)\,\! 2.0
Q_PRIME_LOC tglf_q_prime_loc_in \frac{q^2 a^2}{r^2} s 16.0
P_PRIME_LOC tglf_p_prime_loc_in \frac{q a^2}{r B_{unit}^2} \frac{\partial p}{\partial r} 0.0
DRMINDX_LOC tglf_drmindx_loc_in allows for x different than r \frac{\partial r}{\partial x} 1.0
DRMAJDX_LOC tglf_drmajdx_loc_in \frac{\partial R_{maj}}{\partial x} 0.0
DZMAJDX_LOC tglf_dzmajdx_loc_in \frac{\partial Z_{maj}}{\partial x} 0.0
KAPPA_LOC tglf_kappa_loc_in elongation of flux surface, \kappa\,\! 1.0
S_KAPPA_LOC tglf_s_kappa_loc_in shear in elongation, \frac{r}{\kappa}\frac{\partial \kappa}{\partial r} 0.0
DELTA_LOC tglf_delta_loc_in 0.0
S_DELTA_LOC tglf_s_delta_loc_in shear in triangularity, r \frac{\partial \delta}{\partial r} 0.0
ZETA_LOC tglf_zeta_loc_in squareness, \zeta\,\!, of flux surface 0.0
S_ZETA_LOC tglf_s_zeta_loc_in shear in squareness, r \frac{\partial\zeta}{\partial r} 0.0
RMIN_SA tglf_rmin_sa_in normalized minor radius of flux surface r/a\,\! 0.5
RMAJ_SA tglf_rmaj_sa_in normalized major radius of flux surface R_{maj}/a\,\! 3.0
Q_SA tglf_q_sa_in absolute value of safety factor 2.0
SHAT_SA tglf_shat_sa_in magnetic shear \frac{r}{q}\frac{\partial q}{\partial r} 1.0
ALPHA_SA tglf_alpha_sa_in normalized pressure gradient 0.0
XWELL_SA tglf_xwell_sa_in magnetic well 0.0
THETA0_SA tglf_theta0_sa_in \theta_0 = \frac{k_x}{s k_y} 0.0
B_MODEL_SA tglf_b_model_sa_in 0/1 to exclude/include the B(theta) factor in k_per 1
FT_MODEL_SA tglf_ft_model_sa_in 1 uses trapped fraction at the outboard midplane 1
THETA_TRAPPED tglf_theta_trapped_in parameter to adjust trapped fraction model 0.7
PARK tglf_park_in multiplies the parallel gradient term 1.0
GHAT tglf_ghat_in multiplies the curvature drift closure terms 1.0
GCHAT tglf_gchat_in multiplies the curvature drift irreducible terms 1.0
WD_ZERO tglf_wd_zero_in cutoff for curvature drift eigenvalues to prevent zero 0.1
LINSKER_FACTOR tglf_linsker_factor_in multiplies the Linsker terms 0.0
GRADB_FACTOR tglf_gradB_factor_in multiplies the gradB terms 0.0
FILTER tglf_filter_in sets threshold for frequency/drift frequency to filter out non-driftwave instabilities 2.0'''
descs = [' '.join(x.split()[2:-1]) for x in s.splitlines()]
vars = [x.split()[0] for x in s.splitlines()]
wiki_descs = dict(list(zip(vars, descs)))


if 'input.tglf' in root['FILES']:
    choices = {}
    charges = [0] * root['FILES']['input.tglf']['NS']
    masses = [0] * root['FILES']['input.tglf']['NS']
    for k, v in root['FILES']['input.tglf'].items():
        if k[0:3] == 'ZS_':
            ind = int(k.split('_')[1]) - 1
            if ind > root['FILES']['input.tglf']['NS'] - 1:
                continue
            charges[ind] = v
            masses[ind] = root['FILES']['input.tglf']['MASS_%d' % (ind + 1)]

        elif isinstance(v, type(float(0))) and v != 0:

            if not k.startswith('MASS_'):
                if k in wiki_descs:
                    choices['%s: %s' % (k, wiki_descs[k])] = k
                else:
                    choices[k] = k
    param_desc = (
        ('RLNS_', 'density scale length'),
        ('AS_', 'density ratio to ne'),
        ('VPAR_', 'parallel velocity'),
        ('VPAR_SHEAR_', 'parallel velocity shear'),
        ('RLTS_', 'temperature scale length'),
        ('TAUS_', 'temperature ratio to Te'),
    )
    for param, desc in param_desc:
        uniq_charges = []
        for ic, c in enumerate(charges, 1):
            spec = 'Ion Z=%g A/D=%g' % (c, masses[ic - 1])
            if c == -1:
                spec = 'Electron'
            if c == 1:
                if masses[ic - 1] == 1:
                    spec = 'Deuterium'
                elif masses[ic - 1] == 0.5:
                    spec = 'Hydrogen'
                elif masses[ic - 1] == 1.5:
                    spec = 'Tritium'
            if c == 6:
                spec = 'Carbon'
            if c == 2:
                spec = 'Helium'
            uniq_charges.append(spec)
            nc = uniq_charges.count(spec)
            if spec != 'Electron':
                spec = spec + str(nc)
                if (param == 'RLTS_' or param == 'TAUS_') and root['SETTINGS']['PHYSICS']['single_Ti'] and nc == 1:
                    if root['FILES']['input.tglf']['%s%d' % (param, ic)] == root['FILES']['input.tglf']['%s2' % (param)]:
                        spec = "Thermal ions'"
                choices['%s %s' % (spec, desc)] = param + str(ic)
            elif nc > 2:
                raise OMFITexception('It does not make sense to have more than one species of electrons')
            elif param == 'AS_' or param == 'TAUS_':
                pass
            else:
                choices['%s %s' % (spec, desc)] = param + str(ic)
            if param + str(ic) in choices:
                del choices[param + str(ic)]

    # get the scan dimensions
    scan_dims = root['SETTINGS']['PHYSICS']['scanDimensions']
    input_dist = []
    input_dist_norm = []
    input_win_data = []

    # defining the input parameters
    OMFITx.ComboBox(
        "root['SETTINGS']['PHYSICS']['scanDimensions']",
        {'一维': 1, '二维': 2, '3D': 3, '4D': 4, '5D': 5},
        '不确定度扫描维数',
        default=1,
        updateGUI=True,
        state='readonly',
    )

    root['SETTINGS']['PHYSICS']['scanParameters'] = []
    for paramN in range(1, scan_dims + 1):
        if show_constraints:
            OMFITx.Tab("Parameter " + str(paramN))
        OMFITx.ComboBox(
            "root['SETTINGS']['PHYSICS']['scanParameter%s']" % str(paramN),
            choices,
            '选择扫描变量',
            updateGUI=True,
            default='RLNS_%s' % paramN,
            width='50',
        )
        param = root['SETTINGS']['PHYSICS']['scanParameter' + str(paramN)]
        value = root['FILES']['input.tglf'][root['SETTINGS']['PHYSICS']['scanParameter' + str(paramN)]]
        if (param.startswith('RLTS_') or param.startswith('TAUS_')) and not param.endswith('_1'):
            OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['single_Ti']", '全部热离子采用相同温度')

        OMFITx.Label("Experimental Value=%g" % value)

        if not root['SETTINGS']['PHYSICS']['multiWindowDist']:
            OMFITx.ComboBox(
                "root['SETTINGS']['PHYSICS']['inputParameterDistribution']",
                ["Normal Distribution"],
                '选择分布类型',
                updateGUI=True,
                width='40',
                default="Normal Distribution",
            )
            if root['SETTINGS']['PHYSICS']['inputParameterDistribution'] == "Normal Distribution":
                # Mean of normal distribution
                OMFITx.Entry(
                    "root['SETTINGS']['PHYSICS']['scanParameter%sMean']" % str(paramN),
                    '分布均值',
                    updateGUI=True,
                    default=value,
                )
                # Std of normal distribution
                OMFITx.Entry(
                    "root['SETTINGS']['PHYSICS']['scanParameter%sStd']" % str(paramN),
                    '分布标准差',
                    updateGUI=True,
                    default=0.1 * value,
                )
            else:
                raise NotImplementedError(
                    'Need to implement %s type of distribution' % root['SETTINGS']['PHYSICS']['inputParameterDistribution']
                )

        root['SETTINGS']['PHYSICS']['scanParameters'].append(param)

    # Sampling details
    OMFITx.Tab('采样设置')
    # Sampling options based on Chaospy definitions
    sampling_opts = {
        "Hammersley Sequence Sampling": "M",
        "Latin Hypercube": "L",
        # "Regular Grid": "RG", #TODO: fix regular grid directory creation problem.
    }
    OMFITx.ComboBox(
        "root['SETTINGS']['PHYSICS']['inputParameterSamplingMethod']",
        sampling_opts,
        '采样方法',
        updateGUI=True,
        default='M',
        width='40',
    )
    # Number of samples
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['scanParameterSamples']", '样本数（运行次数）', updateGUI=True, default=15)
    # Number of parallel runs
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['parallelScan']", '并行运行数', updateGUI=True, default=16)

    # Fix the dimension mismatch if only one input parameter
    if root['SETTINGS']['PHYSICS']['UQInputSamples'].ndim == 1:
        root['SETTINGS']['PHYSICS']['UQInputSamples'] = np.array([root['SETTINGS']['PHYSICS']['UQInputSamples']])

    if show_constraints:
        OMFITx.Tab("Constraints")
        OMFITx.CompoundGUI(root['GUIS']['constraints_GUI'], input_tglf=root['FILES']['input.tglf'], title='')
        OMFITx.Tab("")

    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['multiWindowDist']",
        '对实验子时间窗数据拟合多元正态分布',
        default=False,
        updateGUI=True,
    )

else:
    OMFITx.Label('请先在 FILES 中准备 input.tglf')
    OMFITx.ObjectPicker("root['FILES']['input.tglf']", "input.tglf", OMFITgacode)
