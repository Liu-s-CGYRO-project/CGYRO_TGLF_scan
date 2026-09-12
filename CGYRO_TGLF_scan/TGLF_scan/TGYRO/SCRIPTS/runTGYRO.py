# -*-Python-*-
# Created by meneghini at 2013/03/28 14:35

defaultVars(
    auto_remove_bogus_parameters=scratch.setdefault('auto_remove_bogus_parameters', True),
    reload=root['SETTINGS']['PHYSICS']['reload'],
    save_profilesgen=True,
)

# reload
if reload:
    root['SCRIPTS']['load_remote'].run(load_input_gacode=True)
# run
else:
    # Check EPED_NN compatibility with device:
    if (
        is_device(root['SETTINGS']['EXPERIMENT']['device'], ['DIII-D', 'ITER', 'JET', 'KSTAR'])
        and 'IP_EXP' in input_gacode
        and 'RVBV' in input_gacode
    ):
        pass
    elif root['INPUTS']['input.tgyro']['TGYRO_PED_MODEL'] == 2:
        printw(
            "EPED_NN in TGYRO is not suited fortokamaks other than DIII-D, ITER, JET, KSTAR, disable pedestal evolution or run full EPED"
        )

    # this generates the input.gacode file for TGYRO (if not restarting)
    if not root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG']:

        if PROFILES_GEN is not None and root['SETTINGS']['PHYSICS']['runPROFILES_GEN']:
            PROFILES_GEN['SCRIPTS']['run_profiles_gen'].run(enforce_quasineutrality=True)

        # update the ion info in input.tgyro
        root['SCRIPTS']['update_ion_data'].run()

    # automatically remove deprecated and bous parameters from input.tgyro
    if scratch['auto_remove_bogus_parameters']:
        root['SCRIPTS']['removeBogusParams'].run()

    # run TGYRO
    if root['SETTINGS']['PHYSICS']['Turb_Model'] == 'OMFIT QLGYRO':
        root['SCRIPTS']['omfit_qlgyro'].run()
    else:
        root['SCRIPTS']['runTGYRObase'].run()

# save TGYRO run
root['SCRIPTS']['saveTGYRO'].run(save_profilesgen=save_profilesgen)

# print info
root['SCRIPTS']['print_residual_and_convergence'].run()
