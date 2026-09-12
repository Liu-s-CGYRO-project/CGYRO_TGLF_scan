# -*-Python-*-
# Created by snoepg at 27 Sep 2017  02:05


def save_qlgyro_tgyro_outputs(iit=None):
    if iit is None:
        iit = len(root['QLGYRO_OUTPUTS']['fluxes']['efluxi_model']) - 1

    root['OUTPUTS']['output']['eflux_e_tot'][-1, :] = root['QLGYRO_OUTPUTS']['fluxes']['efluxe_model'][iit, :]

    root['OUTPUTS']['output']['eflux_i_tot'][-1, :] = root['QLGYRO_OUTPUTS']['fluxes']['efluxi_model'][iit, :]
    root['OUTPUTS']['output']['pflux_e_tot'][-1, :] = root['QLGYRO_OUTPUTS']['fluxes']['pflux_model'][iit, :]
    root['OUTPUTS']['output']['mflux_tot'][-1, :] = root['QLGYRO_OUTPUTS']['fluxes']['mflux_model'][iit, :]


def change_TGYRO_runid(origin, branch):
    if origin in root['RUN_DB']:
        root['SETTINGS']['EXPERIMENT']['runid'] = origin
        root['SCRIPTS']['reloadTGYRO'].runNoGUI()
    root['SETTINGS']['EXPERIMENT']['runid'] = branch
    if branch in root['RUN_DB']:
        del root['RUN_DB'][branch]


def diff_and_pinch(ion_name, A, Z, runs, n_ids, ip, n_id, blend=True, axis_core_rho=0.3, core_ped_rho=0.8, ped_tur_mult=0.1):
    """
    Calculate diffusion and pinch (convection) coefficients given two ion species

    :param A: Impurity atomic number

    :param Z: Impurity charge (single number or radial profile)

    :param run1: first OMFITtgyro run

    :param n_id1: number of first ion species to use

    :param run2: second OMFITtgyro run (can be same as run1)

    :param n_id2: number of second ion species to use

    :param ip: base input.gacode

    :param n_id: number of ion species to assign D and v to

    :param blend: blend D/v profiles according to G. Snoep recipe

    :param axis_core_rho: transition point between axis and core region

    :param core_ped_rho: transition point between core and pedestal region

    :param ped_tur_mult: turbulence multiplier in the pedestal region

    :return: dictionary with neoclassical and turbulent D, v, and v/D
    """

    nruns = len(runs)
    s_idp = 'e' if n_id == 0 else 'i_' + str(n_id)
    s_id = 'e' if n_id == 0 else 'i' + str(n_id)
    s_ids = ['e' if n_id == 0 else 'i' + str(i) for i in n_ids]

    rho = runs[0]['rho'][-1]
    ne = interp(rho, ip['rho'], ip['ne'])
    ni = interp(rho, ip['rho'], ip['n%s' % s_idp])
    rmin = runs[0]['rmin'][-1] * 1e-2  # m
    a = runs[0]['a'] / 100  # m

    n = np.array([r['n' + s][-1, :] * 1e6 for r, s in zip(runs, s_ids)])  # 1e19m^-3?
    dndr = np.array([-r['a/Ln%s' % s][-1] / a for r, s in zip(runs, s_ids)])  # 1/m

    pflux_neo = np.array([r['pflux_%s_neo' % s][-1] for r, s in zip(runs, s_ids)])
    pflux_tur = np.array([r['pflux_%s_tur' % s][-1] for r, s in zip(runs, s_ids)])
    gamma_gb = np.array([r['Gamma_GB'][-1] * 1e19 for r in runs])

    # Particle flux/density in MKS units
    gamma_n = pflux_neo * gamma_gb / n
    gamma_t = pflux_tur * gamma_gb / n

    nr = len(rho)
    # Compute the neoclassical and turbulent diffusion coefficients and pinch velocities
    D_tur, v_tur, r_tur = np.ma.zeros(nr), np.ma.zeros(nr), np.zeros(nr) + inf
    D_neo, v_neo, r_neo = np.ma.zeros(nr), np.ma.zeros(nr), np.zeros(nr) + inf

    # robust method, tries to find runs where the gradient flux relation is strongly nonlinear and remove them
    for ir in range(1, nr):

        resids = []
        combs = []
        transp_coeffs = []
        # try all combinations of 3, choose the one which is nearest to straight line
        if nruns > 3:
            from itertools import combinations

            sets = combinations(range(nruns), 3)
        else:
            sets = [range(nruns)]

        for c in sets:
            M = c_[-dndr[c, ir], ones_like(c)]
            DV, r = np.linalg.lstsq(M, gamma_t[c, ir])[:2]
            if len(r) == 0:
                r = np.inf

            resids.append(r)
            combs.append(c)
            transp_coeffs.append(DV)

        best = argmin(resids)

        D_tur[ir], v_tur[ir] = transp_coeffs[best]
        r = resids[best]
        r_tur[ir] = r if np.isfinite(r) else 0

    for ir in range(1, nr):
        (D_neo[ir], v_neo[ir]), r, rr, s = np.linalg.lstsq(c_[-dndr[:, ir], ones_like(n_ids)], gamma_n[:, ir])
        r_neo[ir] = r if len(r) else 0

    # remove cases with large error in linear gradient flux relation
    D_tur.mask = r_tur > 1
    v_tur.mask = r_tur > 1
    D_neo.mask = r_neo > 0.01
    v_neo.mask = r_neo > 0.01

    if any((D_neo < 0) & ~D_neo.mask):
        v_neo.mask[D_neo < 0] = True
        D_neo.mask[D_neo < 0] = True
        printe('Negative neoclassical diffusion!')
    if any(D_tur < 0):
        v_tur.mask[D_tur < 0] = True
        D_tur.mask[D_tur < 0] = True
        printe('Negative turbulent diffusion!')

    # conversion factor for coordinate transformation r_min ->  r_V used in STRAHL

    PROFILES_GEN['OUTPUTS']['input.gacode'].load()

    vol = input_gacode.volume()

    r_V = np.sqrt(vol / (2 * pi**2 * ip['rmaj']))
    drV_drm = np.interp(rho, ip['rho'], gradient(r_V, ip['rmin']))

    # calculate asymmetry correction factors
    from scipy.constants import e, m_p

    ionM = 2.0  # deuterium atomic number
    R, z = input_gacode.rz_geometry(200)  # m

    Rlfs = R[0]
    omg = input_gacode['omega0']  # rad/s
    Ti = ip['Ti_1'] * 1e3  # eV
    Te = ip['Te'] * 1e3  # eV
    zeff = ip['z_eff']
    # approximation, but it is rather accurate
    lam = m_p * A * omg**2 / (2 * Ti * e) * (1 - Z * ionM / A * zeff * Te / (Ti + zeff * Te))

    # impurity density profile n_z/n_z_lfs
    prof = np.exp(lam * (R**2 - Rlfs[None] ** 2))

    # do flux surface averaging
    dV = 2 * pi * R * np.linalg.det(np.array((gradient(z), gradient(R))).T).T

    # n_ratio and V_conv are outputs from NEO which are not passed to TGYRO output
    n_ratio = safe_divide(np.sum(dV, 0), np.sum(prof * dV, 0), 1)

    V_conv = -gradient(n_ratio, ip['rmin'] / a) / n_ratio
    if rmin[0] == 0:
        V_conv[0] = 0  # correct on-axis value
    n_ratio = np.interp(rho, ip['rho'], n_ratio)
    V_conv = np.interp(rho, ip['rho'], V_conv)

    chi = calc_heat_conductivity(tgyro_output=runs[0])
    chi_eff = chi['chi_eff_tglf']

    D_and_v = OMFITtree()
    D_and_v.update(
        {
            'D_neo_%s' % s_id: D_neo,
            'D_tur_%s' % s_id: D_tur,
            'v_neo_%s' % s_id: v_neo,
            'v_tur_%s' % s_id: v_tur,
            'aV_tot_%s/chi_eff' % s_id: a * safe_divide(v_tur + v_neo, chi_eff),
            'D_tot_%s/chi_eff' % s_id: safe_divide(maximum(D_tur, 0) + D_neo, chi_eff),
            'rho': rho,
            'rmin': rmin,
            'a': a,
            'ne': ne,
            'n%s' % s_id: ni,
            'drV_drm': drV_drm,
            'n_ratio': n_ratio,
            'V_conv': V_conv,
            'n_id': n_id,
            'ion_name': ion_name,
        }
    )

    # D_and_v blender
    Dv_blender(axis_core_rho, core_ped_rho, ped_tur_mult, D_and_v)

    return D_and_v


def Dv_blender(axis_core_rho, core_ped_rho, ped_tur_mult, D_and_v=None, blend=True):

    if D_and_v is None:
        D_and_v = root['OUTPUTS']['D_and_v']

    n_id = D_and_v['n_id']
    s_id = ['e', 'i%d' % n_id][n_id != 0]
    D_neo = maximum(D_and_v['D_neo_%s' % s_id], 1e-3)
    D_tur = maximum(D_and_v['D_tur_%s' % s_id], 1e-3)

    v_neo = D_and_v['v_neo_%s' % s_id]
    v_tur = D_and_v['v_tur_%s' % s_id]
    rho = D_and_v['rho']
    rmin = D_and_v['rmin']
    ne = D_and_v['ne']
    ni = D_and_v['n%s' % s_id]

    # total D/v with optional blending rule
    D_tot = D_neo + D_tur
    v_tot = v_neo + v_tur

    # blender
    axis = rho < axis_core_rho
    core = (rho >= axis_core_rho) & (rho <= core_ped_rho)
    ped = rho > core_ped_rho

    if blend:
        # axis transport is usually neoclassical, but neoclassical theory breaks down inside of the potato orbit width
        # replace D and V by extrapolations. Use total v and D to avoid discontinuities at axis_core_rho
        D_tot.mask[axis] = True
        v_tot.mask[axis] = True

        valid = ~D_tot.mask
        # fill the gaps

        D_tot = interp(rho, rho[valid], D_tot[valid])
        v_tot = interp(rho, rho[valid], v_tot[valid] / rho[valid]) * rho

        if ped_tur_mult is None and sum(ped) > 1:
            # constant D after core_ped_rho
            D_tot[ped] = D_tot[core][-1]
            # v from zero flux electron density profile
            dnedrmin = gradient(ne, rmin)
            v_tot[ped] = dnedrmin[ped] / ne[ped] * D_tot[ped]
        else:
            D_tot[ped] = D_neo[ped] + ped_tur_mult * D_tur[ped]
            v_tot[ped] = v_neo[ped]

    # Compute zero flux impurity density profile
    try:
        prof_neo = integz(rmin, -safe_divide(v_neo, D_neo), 0, 1, rmin)
    except Exception:
        prof_neo = rmin * 0 + nan
    try:
        prof_tur = integz(rmin, -safe_divide(v_tur, D_tur), 0, 1, rmin)
    except Exception:
        prof_tur = rmin * 0 + nan

    try:
        prof_tot = integz(rmin, -safe_divide(v_tot, D_tot), 0, 1, rmin)
    except Exception:
        prof_tot = rmin * 0 + nan

    norm = mean(ni[core])
    if norm == 0:
        norm = 1

    prof_neo *= norm / mean(prof_neo[core])  # same units as input.gacode
    prof_tur *= norm / mean(prof_tur[core])
    prof_tot *= norm / mean(prof_tot[core])
    D_and_v.update(
        {
            'D_blend_%s' % s_id: D_tot,
            'v_blend_%s' % s_id: v_tot,
            'n_tur_%s' % s_id: prof_tur,
            'n_neo_%s' % s_id: prof_neo,
            'n_blend_%s' % s_id: prof_tot,
            'rho': rho,
            'axis_core_rho': axis_core_rho,
            'core_ped_rho': core_ped_rho,
        }
    )
    D_and_v.sort()
    return D_and_v


def calc_heat_conductivity(tgyro_output=None):
    if tgyro_output is None:
        tgyro_output = root['OUTPUTS']['output']
    from scipy.constants import e

    chi = root['OUTPUTS']['chi'] = OMFITtree()

    rho = input_gacode['rho']

    Pe = input_gacode['pow_e']  # [GW] convective +diffusive electron heat flux
    Pi = input_gacode['pow_i']  # [GW] convective +diffusive ion heat flux
    Pie = input_gacode['pow_ei']  # [GW]  ion-electron exchange flux
    r = input_gacode['rmin']

    vol = input_gacode.volume()

    surf = surf_ = gradient(vol, r)
    Q_GB = tgyro_output['Q_GB'][-1, :] * 1e6  # W/m^-2
    rho_tgyro = tgyro_output['rho'][-1, :]
    rho_tgyro = np.ma.array(rho_tgyro, mask=rho_tgyro == 0)
    # if the profiles was generated from TRANSP
    # correction for a heat flux definition used by TRANSP vs GACODE
    if 'TRXPL' in PROFILES_GEN and 'statefile' in PROFILES_GEN['TRXPL']['OUTPUTS']:
        TRXPL_state = PROFILES_GEN['TRXPL']['OUTPUTS']['statefile']
        rho_trans = TRXPL_state['rho']['data']
        surf = TRXPL_state['surf']['data'] + 1e-6  # to avoid zero divison
        surf = interp(rho, rho_trans, surf)
        Q_GB *= interp(rho_tgyro, rho, surf_ / surf)
    else:
        printe('Surface area correction could not be done')

    a = tgyro_output['a'] * 1e-2  # m
    rmin = input_gacode['rmin']  # m
    n_ions = root['INPUTS']['input.tgyro']['LOC_N_ION']
    ions = range(1, n_ions + 1)
    Te_tgyro = tgyro_output['te'][-1, :] * 1e3  # eV
    Te_exp = input_gacode['Te'] * 1e3  # eV
    Ti_tgyro = tgyro_output['ti1'][-1, :] * 1e3  # eV
    Ti_exp = input_gacode['Ti_1'] * 1e3  # eV
    ni_tgyro = sum([tgyro_output['ni%d' % i][-1, :] for i in ions], 0) * 1e6  # m^-3
    ne_tgyro = tgyro_output['ne'][-1, :] * 1e6  # m^-3
    ni_exp = sum([input_gacode['ni_%d' % i] for i in ions], 0) * 1e19  # m^-3
    ne_exp = input_gacode['ne'] * 1e19  # m^-3

    # get temperature gradients
    aLte_tgyro = tgyro_output['a/Lte'][-1, :]
    aLti_tgyro = tgyro_output['a/Lti1'][-1, :]
    # tgyro
    dTedr_tgyro = aLte_tgyro / a * Te_tgyro  # eV/m
    dTidr_tgyro = aLti_tgyro / a * Ti_tgyro  # eV/m

    # experiment
    dTedr_exp = -gradient(Te_exp, rmin)  # eV/m
    dTidr_exp = -gradient(Ti_exp, rmin)  # eV/m

    # two different ways how to calculate heat flux, should give the same results
    chi['Qe_exp_target'] = tgyro_output['eflux_e_target'][-1, :] * Q_GB  # W/m^-2
    chi['Qi_exp_target'] = tgyro_output['eflux_i_target'][-1, :] * Q_GB  # W/m^-2
    chi['Qe_exp'] = Pe / surf * 1e6  # W/m^-2
    chi['Qi_exp'] = Pi / surf * 1e6  # W/m^-2
    chi['Qie_exp'] = Pie / surf * 1e6  # W/m^-2

    # NOTE TGLF flux is not normalised by a surface area but by dV/dr

    chi['Qe_tglf'] = tgyro_output['eflux_e_tur'][-1, :] * Q_GB  # W/m^2
    chi['Qi_tglf'] = sum([tgyro_output[f'eflux_i{i}_tur'][-1, :] for i in ions], 0) * Q_GB  # W/m^-2

    chi['Qe_neo'] = tgyro_output['eflux_e_neo'][-1, :] * Q_GB  # W/m^2
    chi['Qi_neo'] = sum([tgyro_output['eflux_i%d_neo' % i][-1, :] for i in ions], 0) * Q_GB  # W/m^2
    # chi['Qi_neo'] = tgyro_output['eflux_i1_neo'][-1,:]*Q_GB#W/m^2

    if 'Experimental_fluxes' in root:
        # TGLF_scan module
        chi['Qe_tglf_scan'] = zeros_like(rho_scan)
        chi['Qi_tglf_scan'] = zeros_like(rho_scan)
        rho_scan = root['Experimental_spectra'].KEYS()
        for i, data in enumerate(root['Experimental_fluxes']['data']):
            chi['Qe_tglf_scan'][i] = data[0][2]  # electron heat flux
            chi['Qi_tglf_scan'][i] = data[1][2]  # ion heat flux

        chi['Qe_tglf_scan'] *= interp(rho_scan, rho_tgyro, Q_GB)  # W/m^2
        chi['Qi_tglf_scan'] *= interp(rho_scan, rho_tgyro, Q_GB)  # W/m^2

        chi['chi_e_tglf_scan'] = chi['Qe_tglf_scan'] / interp(rho_scan, rho_tgyro, dTedr_tgyro * ne_tgyro * e)  # m^2/s
        chi['chi_i_tglf_scan'] = chi['Qi_tglf_scan'] / interp(rho_scan, rho_tgyro, dTidr_tgyro * ni_tgyro * e)  # m^2/s
        chi['rho_scan'] = rho_scan

    chi['chi_e_exp_target'] = chi['Qe_exp_target'] / interp(rho_tgyro, rho, dTedr_exp * ne_exp * e)  # m^2/s
    chi['chi_i_exp_target'] = chi['Qi_exp_target'] / interp(rho_tgyro, rho, dTidr_exp * ni_exp * e)  # m^2/s
    chi['chi_eff_exp_target'] = (chi['Qi_exp_target'] + chi['Qe_exp_target']) / interp(
        rho_tgyro, rho, dTidr_exp * ni_exp * e + dTedr_exp * ne_exp * e
    )  # m^2/s

    chi['chi_e_exp'] = chi['Qe_exp'] / (dTedr_exp * ne_exp * e)  # m^2/s
    chi['chi_i_exp'] = chi['Qi_exp'] / (dTidr_exp * ni_exp * e)  # m^2/s
    chi['chi_eff_exp'] = (chi['Qi_exp'] + chi['Qe_exp']) / (dTidr_exp * ni_exp * e + dTedr_exp * ne_exp * e)  # m^2/s

    chi['chi_e_neo'] = safe_divide(chi['Qe_neo'], dTedr_tgyro * ne_tgyro * e)  # m^2/s
    chi['chi_i_neo'] = safe_divide(chi['Qi_neo'], dTidr_tgyro * ni_tgyro * e)
    chi['chi_eff_neo'] = safe_divide(chi['Qi_neo'] + chi['Qe_neo'], dTidr_tgyro * ni_tgyro * e + dTedr_tgyro * ne_tgyro * e)

    chi['chi_e_tglf'] = safe_divide(chi['Qe_tglf'], dTedr_tgyro * ne_tgyro * e)  # m^2/s
    chi['chi_i_tglf'] = safe_divide(chi['Qi_tglf'], dTidr_tgyro * ni_tgyro * e)
    chi['chi_eff_tglf'] = safe_divide(chi['Qi_tglf'] + chi['Qe_tglf'], dTidr_tgyro * ni_tgyro * e + dTedr_tgyro * ne_tgyro * e)

    chi['rho_tgyro'] = rho_tgyro
    chi['rho_input'] = rho

    return chi


def fit_ne_EPED1(debug_plot=False):
    from omfit_classes.utils_fusion import pedestal_finder

    psi = input_gacode['polflux']
    psi = psi * sign(psi[-1] - psi[0])
    psin = (psi - min(psi)) / (max(psi) - min(psi))
    ne = input_gacode['ne']
    zeff = input_gacode['z_eff']
    ne_ped, width, psin_fit, ne_fit = pedestal_finder(profile=ne, psi_norm=psin, eped_definition=True, return_fit=True, doPlot=debug_plot)

    data = {}
    data['psin'] = psin
    data['psin_fit'] = psin_fit
    data['ne'] = ne
    data['z_eff'] = zeff
    data['ne_fit'] = ne_fit
    data['width'] = width
    data['ne_ped'] = ne_ped
    index_fit = numpy.argmin(numpy.abs(ne_fit - ne_ped))
    data['zeff_ped'] = numpy.interp(fp=zeff, xp=psin, x=psin_fit)[index_fit]
    if debug_plot:
        fig = figure(num='input_gacode EPED1 density fit')
        clf()
        ax1 = fig.use_subplot(1, 2, 1)
        ax1.plot(psin, ne)
        ax1.set_title('n_e')
        ax2 = fig.use_subplot(1, 2, 2, sharex=ax1)
        ax2.plot(psin, zeff)
        ax2.set_title('zeff')
        ax1.plot(data['psin_fit'], data['ne_fit'], label='0')
        ax1.plot(psin_fit[index_fit], data['ne_ped'], 'ob')
        ax2.plot(psin_fit[index_fit], data['zeff_ped'], 'ob')
        ax1.axvline(psin_fit[index_fit], color='k', ls='--')

    return data


def radii(radial_distribution=None, doPlot=False):
    if radial_distribution is None:
        radial_distribution = root['SETTINGS']['PHYSICS']['radial_distribution']

    if radial_distribution.endswith('_z') or doPlot:
        x = input_gacode['rho']
        zTe = calcz(x, input_gacode['Te'], consistent_reconstruction=False)
        zTi = calcz(x, input_gacode['Ti_1'], consistent_reconstruction=False)
        zne = calcz(x, input_gacode['ne'], consistent_reconstruction=False)

        # average profiles scale-length
        z = sqrt(zTe**2 + zTi**2 + zne**2)
        if doPlot:
            figure(num='TGYRO radial distribution')
            plot(x, z)
    # uniform radial distribution of points
    if radial_distribution == 'uniform_r':
        xu = linspace(
            root['INPUTS']['input.tgyro']['TGYRO_RMIN'], root['INPUTS']['input.tgyro']['TGYRO_RMAX'], root['SETTINGS']['PHYSICS']['n_rad']
        )

    # distribution of points to more or less uniformely sample z
    elif radial_distribution == 'uniform_z':
        zu = deriv(x, z)
        zu[zu < 0] = 0
        zu += 0.1
        z1 = cumtrapz(zu, x, initial=0)
        # if doPlot:
        #    plot(x,z1) #monotonically increasing scale-length
        m = interp1d(x, z1)(root['INPUTS']['input.tgyro']['TGYRO_RMIN'])
        M = interp1d(x, z1)(root['INPUTS']['input.tgyro']['TGYRO_RMAX'])
        zu = linspace(m, M, root['SETTINGS']['PHYSICS']['n_rad'])
        xu = interp1d(z1, x)(zu)

    # z variations
    elif radial_distribution == 'variation_z':
        xu = linspace(root['INPUTS']['input.tgyro']['TGYRO_RMIN'], root['INPUTS']['input.tgyro']['TGYRO_RMAX'], 100)
        zu = interp1d(x, z)(xu)
        xu, zu = autoknot(xu, zu, root['SETTINGS']['PHYSICS']['n_rad'], s=1, minDist=0.1, allKnots=True)

    # used defined
    elif radial_distribution == 'user':
        xu = root['SETTINGS']['PHYSICS']['radii']

    else:
        raise OMFITexception('Unknown radial distribution strategy `%s`' % radial_distribution)

    if doPlot:
        zu = interp1d(x, z)(xu)
        figure(num='TGYRO radial distribution')
        plot(xu, zu, 'o', label=radial_distribution)  # actual samples
        legend(loc=0)
        title('Average profiles scale lengths')
        if root['INPUTS']['input.tgyro']['TGYRO_USE_RHO']:
            xlabel('rho')
        else:
            xlabel('r/a')

    return xu


def setup_radii(radial_distribution=None):
    if radial_distribution is None:
        radial_distribution = root['SETTINGS']['PHYSICS']['radial_distribution']

    if radial_distribution == 'uniform_r':
        xu = None
    else:
        xu = radii()

    root['SETTINGS']['PHYSICS']['radii'] = radii()
    root['SETTINGS']['PHYSICS']['n_rad'] = len(radii())
    input_tgyro = root['INPUTS']['input.tgyro']
    input_tgyro['DIR'] = SortedDict()
    turb_model = root['SETTINGS']['PHYSICS']['Turb_Model']
    if turb_model == 'OMFIT QLGYRO':
        turb_model = 'TGLF'
    parallel_jacobian = 0
    if root['INPUTS']['input.tgyro']['TGYRO_ITERATION_METHOD'] == 5:
        for k in ['LOC_TE_FEEDBACK_FLAG', 'LOC_NE_FEEDBACK_FLAG', 'LOC_TI_FEEDBACK_FLAG', 'LOC_ER_FEEDBACK_FLAG']:
            parallel_jacobian += root['INPUTS']['input.tgyro'].get(k, 0)

    for i in range(1, root['SETTINGS']['PHYSICS']['n_rad'] + 1):
        nmpi = root['SETTINGS']['SETUP']['n_cpu_rad'] * (1 + parallel_jacobian)

        if xu is None:
            input_tgyro['DIR']['%s%d' % (turb_model, i)] = nmpi
        else:
            input_tgyro['DIR']['%s%d' % (turb_model, i)] = [nmpi, f'X={xu[i-1]}']
