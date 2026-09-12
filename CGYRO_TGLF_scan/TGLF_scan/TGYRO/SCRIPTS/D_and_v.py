# -*-Python-*-
# Created by snoepg at 02 Oct 2017  17:35

"""
Calculate diffusion and pinch coefficients either

using double impurity method [modify_intrinsic=False]:
    Single TGYRO run with two impurity profiles such that sum of them is equal to density and gradient of the original
    1. the first  one with an zero gradient and half density of the original
    2. the second one with doubled gradient and half density of the original species

using intrinsic impurity [modify_intrinsic=True]:
    Two TGYRO runs with intrinsic impurity profiles:
    The idea in this case is to have two TGYRO runs:
    1. the first one with an zero gradient and half density of the original
    2. the second one with doubled gradient and half density of the original species

First impurity should be the method of choice but in certain cases
where trace impurities cannot be added (eg. when using NN models)
"""
# modify_intrinsic must be =True if running with NNs
modify_intrinsic = (
    'TGYRO_TGLF_NN_MAX_ERROR' in root['INPUTS']['input.tgyro'] and root['INPUTS']['input.tgyro']['TGYRO_TGLF_NN_MAX_ERROR'] > 0
)
root['SETTINGS']['PHYSICS'].setdefault('extendedProfiles', False)
root['SETTINGS']['PHYSICS'].setdefault('robustDVprofiles', False)


axis_core_rho = root['INPUTS']['input.tgyro']['TGYRO_RMIN']
core_ped_rho = root['INPUTS']['input.tgyro']['TGYRO_RMAX']
if not root['INPUTS']['input.tgyro']['TGYRO_USE_RHO']:
    # convert r/a to rho
    rmin = root['OUTPUTS']['input.gacode']['rmin']
    axis_core_rho = interp(axis_core_rho, rmin / rmin[-1], input_gacode['rho'])
    core_ped_rho = interp(core_ped_rho, rmin / rmin[-1], input_gacode['rho'])


defaultVars(
    imp_ion_num=root['SETTINGS']['PHYSICS']['ZERO_DENS_GRAD_FLAG'],
    extendedProfiles=root['SETTINGS']['PHYSICS']['extendedProfiles'],
    robustDVprofiles=root['SETTINGS']['PHYSICS']['robustDVprofiles'],
    modify_intrinsic=modify_intrinsic,
    axis_core_rho=axis_core_rho,
    core_ped_rho=core_ped_rho,
    imp_ion_name=root['SETTINGS']['PHYSICS'].get('trace_imp_name', None),
    imp_Z=root['SETTINGS']['PHYSICS'].get('trace_imp_Z', None),
    imp_A=root['SETTINGS']['PHYSICS'].get('trace_imp_M', None),
    imp_therm=True,
    update_blend_only=False,
    include_thermodiffusion=True,
    imp_scale=1e-4,
)

import OMFITlib_general

add_trace = imp_ion_name is not None
ncpu = root['SETTINGS']['SETUP']['n_cpu_rad']

if not include_thermodiffusion and not add_trace:
    printe('Thermodiffusion can be removed only for a trace impurity')
    OMFITx.End()


runid = root['SETTINGS']['EXPERIMENT']['runid']
runid_trace = runid + '_intrinsic_Dv' if modify_intrinsic else runid + '_trace_Dv'
root['SCRIPTS']['saveTGYRO'].runNoGUI()

if update_blend_only:

    ion_names = input_gacode.ion_names()
    ion_name = ion_names[imp_ion_num - 1]
    scale = np.linspace(-2, 2, 5) * 0.1
    imp_pos = imp_ion_num + 1

    if add_trace:
        imp_pos = len(ion_names) + 1
    # ['Compute D and v']
    D_and_v = OMFITlib_general.diff_and_pinch(
        ion_name=imp_ion_name,
        A=imp_A,
        Z=imp_Z,
        runs=[root['RUN_DB'][runid_trace + '_modified' + str(i)]['OUTPUTS']['output'] for i, s in enumerate(scale)],
        n_ids=[imp_pos] * len(scale),
        ip=root['RUN_DB'][runid]['OUTPUTS']['input.gacode'],
        n_id=imp_ion_num,
        axis_core_rho=axis_core_rho,
        core_ped_rho=core_ped_rho,
        ped_tur_mult=None,
    )

    root['OUTPUTS']['D_and_v'] = D_and_v
    root['SCRIPTS']['saveTGYRO'].run()
    OMFITx.End()


for item in [runid_trace, runid_trace + '_modified']:
    if item in root['RUN_DB']:
        del root['RUN_DB'][item]

# backup all root['SETTINGS']
bkp_input_gacode_dep = copy.deepcopy(root['SETTINGS']['DEPENDENCIES']['input_gacode'])


try:

    OMFITlib_general.change_TGYRO_runid(runid, runid_trace)

    root['SETTINGS']['PHYSICS']['runPROFILES_GEN'] = False
    input_tgyro = root['INPUTS']['input.tgyro']

    # use flux matched profile
    input_gacode = root['INPUTS']['input.gacode'] = root['OUTPUTS']['input.gacode'].duplicate()
    root['SETTINGS']['DEPENDENCIES']['input_gacode'] = "root['INPUTS']['input.gacode']"
    root['INPUTS']['input.gacode']['test'] = 0

    if len(root['OUTPUTS']):
        root['OUTPUTS'].clear()

    ion_names = input_gacode.ion_names()
    # {Geometry} - modify the geometry to extend the flux profiles
    if extendedProfiles:
        server = SERVER(root['SETTINGS']['REMOTE_SETUP']['serverPicker'])
        if server == 'iris':
            n_radial = 20
        elif server == 'saturn':
            n_radial = 48
        elif server == 'engaging':
            n_radial = 64
        elif server == 'portal':
            n_radial = 32
        else:
            # just guess
            n_radial = 32

        root['SETTINGS']['PHYSICS']['n_rad'] = n_radial  # Number of radii
        root['SETTINGS']['SETUP']['n_cpu_rad'] = 1
        axis_core_rho = 0.2
        core_ped_rho = 0.9
        input_tgyro['TGYRO_RMIN'] = 1.0 / n_radial  # From rho
        input_tgyro['TGYRO_RMAX'] = 1 - 1.0 / n_radial  # To rho

    # {Solver Controls}
    input_tgyro['TGYRO_RELAX_ITERATIONS'] = 0  # Number of iterations
    input_tgyro['TGYRO_ITERATION_METHOD'] = 1  # 0 iterations requires iteration method <=4
    input_tgyro['LOC_RESTART_FLAG'] = 0
    # input_tgyro['TGYRO_NEO_N_THETA'] = 11  # bump up NEO resolution (must be odd number)

    # {Scale parameters}
    input_tgyro['LOC_LOCK_PROFILE_FLAG'] = 1  # Use exact profiles in iteration 0
    input_tgyro['TGYRO_CONSISTENT_FLAG'] = 0  # Integrated scale-lengths match profiles

    # density variation must be fixed, else it calculates nonsences.
    input_tgyro['LOC_TI_FEEDBACK_FLAG'] = 1
    for i in range(10):
        input_tgyro['TGYRO_DEN_METHOD%d' % i] = 0

    # {use NEO}
    input_tgyro['TGYRO_NEO_METHOD'] = 2
    # input_tgyro['LOC_CHANG_HINTON_FLAG'] = 1

    ion_name = ion_names[imp_ion_num - 1]
    n = input_gacode['ni_%d' % imp_ion_num]
    rmin = input_gacode['rmin']

    if add_trace:
        # add trace impurity to the end
        imp_pos = len(ion_names) + 1
    else:
        # impurity included in the input.gacode
        imp_ion_name, imp_Z, imp_A, imp_therm = input_gacode['IONS'][imp_ion_num]
        imp_therm = imp_therm == 'therm'
        imp_pos = imp_ion_num + 1

    if not modify_intrinsic and not robustDVprofiles:

        n_aux = np.exp(-5 * rmin)
        # profile must be positive after substration
        n_aux /= amax(n_aux / n) * 3
        # always positive profiles, n = n1+n2, dn = dn1 + dn2, dlnn1-dlnn2 != 0
        n1 = n / 2.0 + n_aux
        n2 = n / 2.0 - n_aux

        # NOTE two impurities in TGLF can not have the same Z and A => we will slighly modify A
        deltaA = 1e-3
        deltaZ = 1e-3

        print('Adding first %s trace impurity species' % imp_ion_name)
        # Modify the ions section in input.gacode to include the trace impurity

        input_gacode.add_ion(
            ion_num=imp_pos,
            ion=imp_ion_name,
            Z=imp_Z + deltaZ,
            A=imp_A - deltaA,
            ni=n1 * imp_scale,
            thermal=imp_therm,
            remove_density_from_ion=ion_name,
            temperature_and_velocities_from_ion=ion_name,
        )

        for shift in arange(9, imp_pos, -1):
            input_tgyro[f'TGYRO_CALC_FLAG{shift}'] = input_tgyro[f'TGYRO_CALC_FLAG{shift-1}']
        input_tgyro[f'TGYRO_CALC_FLAG{imp_pos}'] = 1

        if add_trace:
            print('Adding second %s trace impurity species' % imp_ion_name)
            # Modify the ions section in input.gacode to include the trace impurity -- with modified scale length
            input_gacode.add_ion(
                ion_num=imp_pos + 1,
                ion=imp_ion_name,
                Z=imp_Z,
                A=imp_A + deltaA,
                ni=n2 * imp_scale,
                thermal=imp_therm,
                remove_density_from_ion=ion_name,
                temperature_and_velocities_from_ion=ion_name,
            )

            for shift in arange(9, imp_pos + 1, -1):
                input_tgyro[f'TGYRO_CALC_FLAG{shift}'] = input_tgyro[f'TGYRO_CALC_FLAG{shift-1}']
            input_tgyro[f'TGYRO_CALC_FLAG{imp_pos+1}'] = 1

            # set trace temperature gradient to zero
            if not include_thermodiffusion:
                ind = (input_gacode['rho'] > axis_core_rho) & (input_gacode['rho'] < core_ped_rho)
                input_gacode[f'Ti_{imp_pos}'][:] = input_gacode[f'Ti_{imp_pos}'][ind].mean()
                input_gacode[f'Ti_{imp_pos + 1}'][:] = input_gacode[f'Ti_{imp_pos+1}'][ind].mean()

        else:
            imp_pos -= 1

        # Run TGYRO
        all_species = input_gacode.ion_names()
        species = [s for i, s in enumerate(all_species) if input_tgyro['TGYRO_CALC_FLAG' + str(i + 1)]]

        print('Run TGYRO with species: %s' % (', '.join(species)))

        root['SCRIPTS']['runTGYRO'].run(save_profilesgen=False)

        runs = [root['OUTPUTS']['output'], root['OUTPUTS']['output']]
        n_ids = [imp_pos, imp_pos + 1]

    else:

        if not modify_intrinsic:
            input_gacode.add_ion(
                ion_num=imp_pos,
                ion=imp_ion_name,
                Z=imp_Z,
                A=imp_A,
                ni=rmin * 0 + imp_scale,
                thermal=imp_therm,
                remove_density_from_ion=ion_name,
                temperature_and_velocities_from_ion=ion_name,
            )
            imp_ion_num = imp_pos

        # Modify the intrinsic/trace impurity
        if robustDVprofiles:
            scale = np.linspace(-2, 2, 5) * 0.1
        else:
            scale = [0, 1]

        for i, v in enumerate(scale):
            print('%%' * 5, '%d of %d iteration' % (i + 1, len(scale)), '%%' * 5)
            # Switch runid
            OMFITlib_general.change_TGYRO_runid(runid_trace, runid_trace + '_modified' + str(i))

            # Modify the intrinsic impurity
            print('Modify scale length of %s impurity species' % ion_name)
            input_gacode['ni_%d' % imp_ion_num] = exp(v * rmin) / mean(exp(v * rmin)) * imp_scale
            input_gacode.enforce_quasineutrality()

            root['INPUTS']['input.gacode'] = input_gacode

            # Run TGYRO
            print('Run TGYRO with species: %s' % root['INPUTS']['input.gacode'].ion_names())
            root['SCRIPTS']['runTGYRO'].run(save_profilesgen=False)
            root['OUTPUTS']['output'].load()  # force load to make sure run completed

        runs = [root['RUN_DB'][runid_trace + '_modified' + str(i)]['OUTPUTS']['output'] for i, s in enumerate(scale)]
        n_ids = [imp_ion_num] * len(scale)

    # ['Compute D and v']
    D_and_v = OMFITlib_general.diff_and_pinch(
        ion_name=imp_ion_name,
        A=imp_A,
        Z=imp_Z,
        runs=runs,
        n_ids=n_ids,
        ip=root['RUN_DB'][runid]['OUTPUTS']['input.gacode'],
        n_id=imp_ion_num,
        axis_core_rho=axis_core_rho,
        core_ped_rho=core_ped_rho,
        ped_tur_mult=None,
    )

    root['OUTPUTS']['D_and_v'] = D_and_v
    root['SCRIPTS']['saveTGYRO'].run(save_profilesgen=False)

    # save the D/v info in the original runid
    root['SETTINGS']['EXPERIMENT']['runid'] = runid
    root['SCRIPTS']['reloadTGYRO'].run()
    root['OUTPUTS']['D_and_v'] = D_and_v

    # Save the run with the D_and_v information in the runDB
    root['SCRIPTS']['saveTGYRO'].run()

finally:
    root['SETTINGS']['EXPERIMENT']['runid'] = runid
    root['SCRIPTS']['reloadTGYRO'].run()
    root['SETTINGS']['DEPENDENCIES']['input_gacode'] = bkp_input_gacode_dep
    root['SETTINGS']['SETUP']['n_cpu_rad'] = ncpu
