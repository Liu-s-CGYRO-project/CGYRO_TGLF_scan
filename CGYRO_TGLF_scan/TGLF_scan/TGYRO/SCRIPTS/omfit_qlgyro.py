defaultVars(
    relax=root['INPUTS']['input.tgyro']['LOC_RELAX'],
    iterations=root['INPUTS']['input.tgyro']['TGYRO_RELAX_ITERATIONS'],
    restart=root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG'],
    debug=True,
    dt_ionscale=0.005,
    evolve_density=root['SETTINGS']['PHYSICS']['evolve_density'],
    evolve_Te=root['INPUTS']['input.tgyro']['LOC_TE_FEEDBACK_FLAG'],
    evolve_Ti=root['INPUTS']['input.tgyro']['LOC_TI_FEEDBACK_FLAG'],
    evolve_omega=root['INPUTS']['input.tgyro']['LOC_ER_FEEDBACK_FLAG'],
    sat_rule=root['INPUTS']['input.tglf']['SAT_RULE'],
    bound='fixed',
)

# This legacy implementation explicitly models two active ions plus electrons.
# Refuse unsupported mappings before changing input files or submitting jobs.
if len(input_gacode['IONS']) != 2 or any(root['INPUTS']['input.tgyro'].get('TGYRO_CALC_FLAG%d' % i, 0) != 1 for i in (1, 2)):
    raise OMFITexception('OMFIT QLGYRO currently requires exactly two active ions; use TGLF for other species mappings')

input_tgyro_orig = root['INPUTS']['input.tgyro'].duplicate()

root['INPUTS']['input.tgyro']['LOC_RELAX'] = 1e-6
root['INPUTS']['input.tgyro']['LOC_DX_MAX'] = 1e-6
root['INPUTS']['input.tgyro']['TGYRO_RELAX_ITERATIONS'] = 1
root['INPUTS']['input.tgyro']['TGYRO_ITERATION_METHOD'] = 6
root['SETTINGS']['PHYSICS']['runPROFILES_GEN'] = False
runid = str(root['SETTINGS']['EXPERIMENT']['runid'])

from classes.omfit_tglf import intensity_sat, get_sat_params, sum_ky_spectrum, flux_integrals, get_zonal_mixing
from OMFITlib_general import save_qlgyro_tgyro_outputs


def set_vals():
    var = []
    for i in range(1, root['GYRO_scan']['INPUTS']['input.scan']['1D']['nvars'] + 1):
        var.append(root['GYRO_scan']['INPUTS']['input.scan']['1D']['var_{}'.format(i)])
    vals = np.zeros(
        (root['GYRO_scan']['INPUTS']['input.scan']['1D']['nvars'], len(root['GYRO_scan']['INPUTS']['input.scan']['1D']['vals_1']))
    )
    for i in range(1, root['GYRO_scan']['INPUTS']['input.scan']['1D']['nvars'] + 1):
        vals[i - 1, :] = root['GYRO_scan']['INPUTS']['input.scan']['1D']['vals_{}'.format(i)]
    root['GYRO_scan']['INPUTS']['input.scan']['1D']['vars'] = var
    root['GYRO_scan']['INPUTS']['input.scan']['1D']['vals'] = vals


def ig2it(ig, radii):
    radii_index = [np.argmin(abs(ig['rho'] - r)) for r in radii]
    return ig.inputtglf(radii_index)


def qlgyro(sims, ig, sat_rule_in=2):

    kys = []
    for sim in sims:
        kys.append(sim['input.cgyro.gen']['KY'])
        nfield = sim['input.cgyro.gen']['N_FIELD']
        npecies = sim['input.cgyro.gen']['N_SPECIES']
        rmin = sim['input.cgyro.gen']['RMIN']

    kys = np.array(kys)
    nfield = sim['input.cgyro.gen']['N_FIELD']
    nky = len(kys)
    ql_flux = zeros((nky, nspecies, 3, 3))
    gam = zeros(nky)
    ome = zeros(nky)

    for iky, sim in enumerate(sims):
        ky = sim['input.cgyro.gen']['KY']
        try:
            gam[iky] = sim['freq']['gamma'].isel(t=-1)
            ome[iky] = sim['freq']['omega'].isel(t=-1)
            if gam[iky] > 0.0:
                moments = ['particle', 'energy', 'momentum']

                for f in range(3):
                    if f < nfield:
                        for imom, mom in enumerate(moments):
                            for ispec in range(nspecies):
                                ql_flux[iky, ispec, f, imom] = ky * sim['qlflux_ky'][mom].isel(species=ispec, field=f).values[-1]
        except Exception:
            printw(f'Failed at ky = {ky}')
    cgyro_ql = DataArray(
        data=ql_flux[:, :, :, :],
        dims=['ky', 'species', 'field', 'moment'],
        coords={
            'ky': np.arange(nky),
            'moment': ['particle', 'energy', 'momentum'],
            'species': ['1', '2', '3'],
            'field': ['Phi', 'Apar', 'Bpar'],
        },
        attrs={"Species": "CGYRO orders the ions in decreasing prevalence and puts electrons as last species"},
    )

    # Add empty mode dimension to bring QL data into TGLF format:
    QL_data = cgyro_ql.expand_dims({'mode': 2}, axis=[1]).copy()
    # Set subdominant mode to zero
    QL_data.loc[dict(mode=1)].data.fill(0)
    # Need to reorder ions from D, C, e- to e-, D, C:
    QL_data = QL_data.roll(species=1, roll_coords=True)
    # QL_data.data dimensions are: nk, nmodes, ns, nfield, ntype

    # Collect weights for each moment
    cgyro_particle_QL = QL_data.sel(moment='particle')
    cgyro_energy_QL = QL_data.sel(moment='energy')
    cgyro_stresstor_QL = QL_data.sel(moment='momentum')
    cgyro_energy_QL = QL_data.sel(moment='energy')
    cgyro_stresstor_QL = QL_data.sel(moment='momentum')

    # sign of BT_EXP affects sign of gB normalization in CGYRO for QL weights
    sign_Bt = ig['BT_EXP'] / abs(ig['BT_EXP'])
    cgyro_particle_QL *= sign_Bt
    cgyro_energy_QL *= sign_Bt
    cgyro_stresstor_QL *= sign_Bt

    in0rad = ig2it(ig, [rmin])
    in0 = {}
    rad = in0rad.items()[0][0]

    for k, v in in0rad[rad].items():
        in0.setdefault(k, v)

    if sat_rule_in == 0:
        in0['ALPHA_QUENCH'] = 1
        in0['ALPHA_ZF'] = 0
        in0['UNITS'] = 'GYRO'
        in0['USE_AVE_ION_GRID'] = 0
    elif sat_rule_in == 1:
        in0['ALPHA_QUENCH'] = 0
        in0['ALPHA_ZF'] = 1
        in0['UNITS'] = 'GYRO'
        in0['USE_AVE_ION_GRID'] = 1
    else:
        in0['ALPHA_QUENCH'] = 0
        in0['ALPHA_ZF'] = 1
        in0['UNITS'] = 'CGYRO'
        in0['USE_AVE_ION_GRID'] = 1

    in0['ALPHA_E'] = 1

    in0['RLNP_CUTOFF'] = 18
    gammas = array([gam, gam * 0])
    gammas[gammas < 0] = 0.0

    in0['SAT_geo0_out'] = 1

    kx0_e, satgeo1, satgeo2, R_unit, bt0, bgeo0, gradr0, _, _, _, _ = get_sat_params(sat_rule_in, kys, gammas, **in0)

    in0['SAT_geo1_out'] = satgeo1
    in0['SAT_geo2_out'] = satgeo2
    in0['B_geo0_out'] = bgeo0
    in0['Bt0_out'] = bt0
    in0['grad_r0_out'] = gradr0
    in0['SAT_RULE'] = sat_rule_in

    cgyro_sat = sum_ky_spectrum(
        sat_rule_in,  #
        kys,  #
        gammas.T,  # get_sat_params expects gammas in different format than sum_ky_spectrum
        np.zeros(shape(kys)),  # avep0 - only needed for SAT0
        R_unit,  #
        kx0_e,  # spectral shift
        np.zeros(shape(gammas)),  # potential - only needed for SAT0
        cgyro_particle_QL,
        cgyro_energy_QL,
        cgyro_stresstor_QL,
        np.zeros(shape(cgyro_stresstor_QL)),
        np.zeros(shape(cgyro_stresstor_QL)),
        **in0,
    )
    cgyro_flux = np.sum(np.sum(cgyro_sat['energy_flux_integral'], axis=2), axis=0)
    cgyro_particle_flux = np.sum(np.sum(cgyro_sat['particle_flux_integral'], axis=2), axis=0)
    cgyro_mom_flux = np.sum(np.sum(cgyro_sat['toroidal_stresses_integral'], axis=2), axis=0)

    return cgyro_flux, cgyro_particle_flux, cgyro_mom_flux


def new_prof(rmin_ig, prof_ig, rmin_tp, z_tp, a):

    ibound = np.argmin((rmin_tp[-1] - rmin_ig) ** 2)
    z_ig = np.interp(rmin_ig[: ibound + 2], rmin_tp, z_tp)
    z_ig[np.isnan(z_ig)] = 0.0
    prof_new = copy.deepcopy(prof_ig)

    for i in range(ibound + 1, 0, -1):
        prof_new[i - 1] = prof_new[i] * np.exp(-0.5 * (z_ig[i - 1] + z_ig[i]) * (rmin_ig[i - 1] - rmin_ig[i]) / a)
    return prof_new


if not restart:
    root['PROFILES_GEN']['OUTPUTS']['input.gacode_base'] = root['PROFILES_GEN']['OUTPUTS']['input.gacode'].duplicate()
    ig_new = root['PROFILES_GEN']['OUTPUTS']['input.gacode_base'].duplicate()
else:
    ig_new = root['PROFILES_GEN']['OUTPUTS']['input.gacode'].duplicate()


if 'GYRO_scan' not in root:
    OMFIT.loadModule('GYRO_scan', rootName + "['GYRO_scan']")

if 'TGLF_GACODE' not in root:
    OMFIT.loadModule('TGLF_GACODE', rootName + "['TGLF_GACODE']")

rho_tp = root['SETTINGS']['PHYSICS']['radii']
rho_ig = ig_new['rho']
rmin_ig = ig_new['rmin']
irhos = [np.argmin((rho_tp[i] - rho_ig) ** 2) for i in range(len(rho_tp))]
nrad = len(irhos) + 1

if not restart:
    iinit = 0
    root['QLGYRO_OUTPUTS'] = OMFITtree()
    root['QLGYRO_OUTPUTS']['fluxes'] = OMFITtree()
    root['QLGYRO_OUTPUTS']['fluxes']['efluxi_model'] = np.zeros([iterations, nrad])
    root['QLGYRO_OUTPUTS']['fluxes']['efluxi_target'] = np.zeros([iterations, nrad])

    root['QLGYRO_OUTPUTS']['fluxes']['efluxe_model'] = np.zeros([iterations, nrad])
    root['QLGYRO_OUTPUTS']['fluxes']['efluxe_target'] = np.zeros([iterations, nrad])

    root['QLGYRO_OUTPUTS']['fluxes']['pflux_model'] = np.zeros([iterations, nrad])
    root['QLGYRO_OUTPUTS']['fluxes']['pflux_target'] = np.zeros([iterations, nrad])

    root['QLGYRO_OUTPUTS']['fluxes']['mflux_model'] = np.zeros([iterations, nrad])
    root['QLGYRO_OUTPUTS']['fluxes']['mflux_target'] = np.zeros([iterations, nrad])
else:
    iinit = len(root['QLGYRO_OUTPUTS']['fluxes']['efluxi_model'])
    root['QLGYRO_OUTPUTS']['fluxes']['efluxi_model'] = np.concatenate(
        (root['QLGYRO_OUTPUTS']['fluxes']['efluxi_model'], np.zeros([iterations, nrad]))
    )
    root['QLGYRO_OUTPUTS']['fluxes']['efluxi_target'] = np.concatenate(
        (root['QLGYRO_OUTPUTS']['fluxes']['efluxi_target'], np.zeros([iterations, nrad]))
    )

    root['QLGYRO_OUTPUTS']['fluxes']['efluxe_model'] = np.concatenate(
        (root['QLGYRO_OUTPUTS']['fluxes']['efluxe_model'], np.zeros([iterations, nrad]))
    )
    root['QLGYRO_OUTPUTS']['fluxes']['efluxe_target'] = np.concatenate(
        (root['QLGYRO_OUTPUTS']['fluxes']['efluxe_target'], np.zeros([iterations, nrad]))
    )

    root['QLGYRO_OUTPUTS']['fluxes']['pflux_model'] = np.concatenate(
        (root['QLGYRO_OUTPUTS']['fluxes']['pflux_model'], np.zeros([iterations, nrad]))
    )
    root['QLGYRO_OUTPUTS']['fluxes']['pflux_target'] = np.concatenate(
        (root['QLGYRO_OUTPUTS']['fluxes']['pflux_target'], np.zeros([iterations, nrad]))
    )

    root['QLGYRO_OUTPUTS']['fluxes']['mflux_model'] = np.concatenate(
        (root['QLGYRO_OUTPUTS']['fluxes']['mflux_model'], np.zeros([iterations, nrad]))
    )
    root['QLGYRO_OUTPUTS']['fluxes']['mflux_target'] = np.concatenate(
        (root['QLGYRO_OUTPUTS']['fluxes']['mflux_target'], np.zeros([iterations, nrad]))
    )


def set_kys(kys):
    dts = []
    for ky in kys:
        if ky < 1:
            dts.append(dt_ionscale)
        elif ky < 10:
            dts.append(dt_ionscale * 0.2)
        else:
            dts.append(dt_ionscale * 0.1)

    root['GYRO_scan']['INPUTS']['input.scan']['dims'] = '1D'
    root['GYRO_scan']['INPUTS']['input.scan']['1D']['nvars'] = 2
    root['GYRO_scan']['INPUTS']['input.scan']['1D']['var_1'] = 'KY'
    root['GYRO_scan']['INPUTS']['input.scan']['1D']['var_2'] = 'DELTA_T'
    root['GYRO_scan']['INPUTS']['input.scan']['1D']['vals_1'] = kys
    root['GYRO_scan']['INPUTS']['input.scan']['1D']['vals_2'] = dts

    set_vals()


a = np.interp([1], rho_ig, rmin_ig)[0]


root['GYRO_scan']['GYRO_GACODE']['SETTINGS']['SETUP']['code'] = root['GYRO_scan']['INPUTS']['input.scan']['code'] = 'cgyro'
root['GYRO_scan']['GYRO_GACODE']['SETTINGS']['PHYSICS']['mode'] = 'experimental'
server = root['GYRO_scan']['SETTINGS']['REMOTE_SETUP']['serverPicker']
root['GYRO_scan']['GYRO_GACODE']['SETTINGS']['REMOTE_SETUP'][server]['w'] = '02:00:00'


root['GYRO_scan']['INPUTS'][runid] = OMFITtree()
root['GYRO_scan']['OUTPUTS'][runid] = OMFITtree()
root['GYRO_scan']['GYRO_GACODE']['INPUTS']['input.cgyro'] = input_cgyro = root['GYRO_scan']['GYRO_GACODE']['TEMPLATES']['CGYRO'][
    'l_d3d_ion_scale'
]
input_cgyro['DELTA_T_METHOD'] = 1
input_cgyro['MAX_TIME'] = 1e3
input_cgyro['FREQ_TOL'] = 0.01
input_cgyro['ERROR_TOL'] = 0.001
if root['INPUTS']['input.tglf']['USE_BPER']:
    input_cgyro['N_FIELD'] = 2
if root['INPUTS']['input.tglf']['USE_BPAR']:
    input_cgyro['N_FIELD'] = 3

nspecies = 1
for i in range(1, 10):
    if f'TGYRO_CALC_FLAG{i}' in input_tgyro_orig and input_tgyro_orig[f'TGYRO_CALC_FLAG{i}']:
        nspecies = nspecies + 1

input_cgyro['N_SPECIES'] = nspecies
try:
    for it in range(iinit, iterations + iinit):
        root['GYRO_scan']['OUTPUTS'].clear()

        root['GYRO_scan']['GYRO_GACODE']['PROFILES_GEN_GACODE']['OUTPUTS']['input.gacode'] = ig_new
        root['PROFILES_GEN']['OUTPUTS']['input.gacode'] = ig_new

        cgyro_fluxes = np.zeros([3, nrad])
        cgyro_particle_fluxes = np.zeros([3, nrad])
        cgyro_mom_fluxes = np.zeros([3, nrad])

        input_tglfs = ig_new.inputtglf(irhos=irhos)
        kys_all = []
        for ir, rho in enumerate(input_tglfs):
            root['TGLF_GACODE']['FILES']['input.tglf'] = input_tglfs[rho]
            root['TGLF_GACODE']['FILES']['input.tglf']['NS'] = nspecies
            for item in root['INPUTS']['input.tglf']:
                root['TGLF_GACODE']['FILES']['input.tglf'][item] = root['INPUTS']['input.tglf'][item]
            root['TGLF_GACODE']['SCRIPTS']['runTGLF'].run()

            if debug:
                cgyro_fluxes[:, ir + 1] = sum(
                    sum(root['TGLF_GACODE']['FILES']['sum_flux_spectrum']['energy'].values[:, :, :], axis=1), axis=1
                )
                cgyro_particle_fluxes[:, ir + 1] = sum(
                    sum(root['TGLF_GACODE']['FILES']['sum_flux_spectrum']['particle'].values[:, :, :], axis=1), axis=1
                )
                cgyro_mom_fluxes[:, ir + 1] = -1 * sum(
                    sum(root['TGLF_GACODE']['FILES']['sum_flux_spectrum']['toroidal_stress'].values[:, :, :], axis=1), axis=1
                )
            else:
                kys = root['TGLF_GACODE']['FILES']['sum_flux_spectrum']['ky'].values
                kys_all.append(kys)
                set_kys(kys)
                root['GYRO_scan']['GYRO_GACODE']['INPUTS']['input.cgyro']['RMIN'] = rmin_ig[irhos[ir]] / a
                root['GYRO_scan']['INPUTS']['input.scan']['1D']['lab'] = f'RMIN_{ir+1}_KY'
                root['GYRO_scan']['SCRIPTS']['runGYROscan'].run(
                    test=False,
                    parallel=True,
                    wait=False,
                    submit_converged=True,
                    check_pending_running=True,
                )
        if not debug:
            for i in root['GYRO_scan']['OUTPUTS'][runid]['1D']:
                root['GYRO_scan']['OUTPUTS'][runid]['1D'][i]['job_run'].wait()

            for ir in range(1, nrad):
                root['GYRO_scan']['INPUTS']['input.scan']['1D']['lab'] = f'RMIN_{ir}_KY'
                root['GYRO_scan']['SCRIPTS']['downsyncGYROscan'].run(
                    downsync_running=True,
                    downsync_converged=True,
                )
                kys = kys_all[ir - 1]

                cgyro_sims = [
                    root['GYRO_scan']['OUTPUTS'][runid]['1D'][f'RMIN_{ir}_KY_{ik+1}']['OUTPUTS']['cgyro'] for ik in range(len(kys))
                ]
                cgyro_fluxes[:, ir], cgyro_particle_fluxes[:, ir], cgyro_mom_fluxes[:, ir] = qlgyro(
                    cgyro_sims, root['GYRO_scan']['GYRO_GACODE']['PROFILES_GEN_GACODE']['OUTPUTS']['input.gacode']
                )

        # Run TGYRO one step to update neoclassical and power balance
        root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG'] = 0
        root['SCRIPTS']['runTGYRObase'].run()
        root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG'] = restart

        tgyro_output = root['OUTPUTS']['output']
        rmin_ig = ig_new['rmin']
        # pivot 1 grid point out from transport grid to ensure scale lengths are calculated correctly
        rmin_pivot = np.zeros(nrad)
        rmin_pivot[1:] = ig_new['rmin'][np.array(irhos)]

        # Relax Ti
        efluxi_model = tgyro_output['eflux_i1_neo'][-1, :] + tgyro_output['eflux_i2_neo'][-1, :] + sum(cgyro_fluxes[1:, :], axis=0)
        efluxi_target = tgyro_output['eflux_i_target'][-1, :]
        Ti_ig = copy.deepcopy(ig_new['Ti_1'])
        zti_tp = tgyro_output['a/Lti1'][-1, :]
        zti_new = tgyro_output['a/Lti1'][-1, :] * (
            1 + relax * (efluxi_target - efluxi_model) / sqrt(efluxi_target**2 + efluxi_model**2)
        )
        zti_new[0] = 0
        if bound == 'scale_length':
            zti_new[-1] = zti_new[-2]
        Ti_new = new_prof(rmin_ig, Ti_ig, rmin_pivot, zti_new, a)

        # Relax Te
        efluxe_model = tgyro_output['eflux_e_neo'][-1, :] + cgyro_fluxes[0, :]
        efluxe_target = tgyro_output['eflux_e_target'][-1, :]
        Te_ig = copy.deepcopy(ig_new['Te'])
        zte_tp = tgyro_output['a/Lte'][-1, :]
        zte_new = tgyro_output['a/Lte'][-1, :] * (1 + relax * (efluxe_target - efluxe_model) / sqrt(efluxe_target**2 + efluxe_model**2))
        zte_new[0] = 0
        if bound == 'scale_length':
            zte_new[-1] = zte_new[-2]
        Te_new = new_prof(rmin_ig, Te_ig, rmin_pivot, zte_new, a)

        # Relax omega0
        pflux_model = tgyro_output['pflux_e_neo'][-1, :] + cgyro_particle_fluxes[0, :]
        pflux_target = tgyro_output['pflux_e_target'][-1, :]
        ne_ig = copy.deepcopy(ig_new['ne'])
        zne_tp = tgyro_output['a/Lne'][-1, :]
        zne_new = tgyro_output['a/Lne'][-1, :] * (1 + relax * (pflux_target - pflux_model) / sqrt(pflux_target**2 + pflux_model**2))
        zne_new[0] = 0
        if bound == 'scale_length':
            zne_new[-1] = zne_new[-2]
        ne_new = new_prof(rmin_ig, ne_ig, rmin_pivot, zne_new, a)

        mflux_model = tgyro_output['mflux_i1_neo'][-1, :] + tgyro_output['mflux_i2_neo'][-1, :] + sum(cgyro_mom_fluxes[:-1, :], axis=0)
        mflux_target = tgyro_output['mflux_target'][-1, :]
        omega0_ig = copy.deepcopy(ig_new['omega0'])
        zomega0_tp = -1 * tgyro_output['a/dw0dr'][-1, :] / tgyro_output['w0'][-1, :]
        zomega0_new = zomega0_tp * (
            1 + sign(mflux_target) * relax * (mflux_target - mflux_model) / sqrt(mflux_target**2 + mflux_model**2)
        )
        zomega0_new[0] = 0
        if bound == 'scale_length':
            zomega0_new[-1] = zomega0_new[-2]
        omega0_new = new_prof(rmin_ig, omega0_ig, rmin_pivot, zomega0_new, a)

        # Save iteration fluxes
        root['QLGYRO_OUTPUTS']['fluxes']['efluxi_model'][it, :] = efluxi_model
        root['QLGYRO_OUTPUTS']['fluxes']['efluxi_target'][it, :] = efluxi_target

        root['QLGYRO_OUTPUTS']['fluxes']['efluxe_model'][it, :] = efluxe_model
        root['QLGYRO_OUTPUTS']['fluxes']['efluxe_target'][it, :] = efluxe_target

        root['QLGYRO_OUTPUTS']['fluxes']['pflux_model'][it, :] = pflux_model
        root['QLGYRO_OUTPUTS']['fluxes']['pflux_target'][it, :] = pflux_target

        root['QLGYRO_OUTPUTS']['fluxes']['mflux_model'][it, :] = mflux_model
        root['QLGYRO_OUTPUTS']['fluxes']['mflux_target'][it, :] = mflux_target

        # Update profiles
        if evolve_density:
            old_ne = np.array(ig_new['ne'], copy=True)
            if np.any(old_ne <= 0):
                raise OMFITexception('Cannot rescale ion densities with nonpositive electron density')
            ig_new['ni_1'] = ne_new * ig_new['ni_1'] / old_ne
            ig_new['ni_2'] = ne_new * ig_new['ni_2'] / old_ne
            ig_new['ne'] = ne_new

        if evolve_Te:
            ig_new['Te'] = Te_new

        if evolve_Ti:
            for i in range(1, nspecies + 1):
                ig_new['Ti_1'] = Ti_new
                ig_new['Ti_2'] = Ti_new

        if evolve_omega:
            ig_new['omega0'] = omega0_new

        ig_new['ptot'] = ig_new.calc_ptot()

        root['OUTPUTS'][f'input.gacode'] = ig_new = ig_new.duplicate()

        root['QLGYRO_OUTPUTS'][f'input.gacode_{it}'] = ig_new = ig_new.duplicate()
        root['QLGYRO_OUTPUTS'][f'tgyro_output_{it}'] = tgyro_output.duplicate()
    save_qlgyro_tgyro_outputs()

except Exception:
    root['INPUTS']['input.tgyro'] = input_tgyro_orig
    raise

root['INPUTS']['input.tgyro'] = input_tgyro_orig
