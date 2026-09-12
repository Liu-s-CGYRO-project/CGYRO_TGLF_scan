# -*-Python-*-
# Created by snoepg at 20 Jul 2017  15:00

runid = str(root['SETTINGS']['EXPERIMENT']['runid'])
if len(root['RUN_DB']) and runid in root['RUN_DB']:
    print('Loading cached simulation for runid `%s`' % runid)
    base = root['RUN_DB'][runid]
    if 'OUTPUTS' in base:
        root['OUTPUTS'] = copy.deepcopy(base['OUTPUTS'])
        if 'outputs' in root['OUTPUTS']:
            root['SCRIPTS']['print_residual_and_convergence'].run()
    if 'INPUTS' in base:
        root['INPUTS'] = copy.deepcopy(base['INPUTS'])
        root['SETTINGS']['PHYSICS']['n_rad'] = len(root['INPUTS']['input.tgyro']['DIR'])
    if 'PROFILES_GEN' in base:
        PROFILES_GEN['OUTPUTS'] = copy.deepcopy(base['PROFILES_GEN'])
    if 'auto_remove_bogus_parameters' in scratch:
        del scratch['auto_remove_bogus_parameters']
