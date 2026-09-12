# -*-Python-*-
# Created by smithsp at 2013/05/23 09:38

defaultVars(save_profilesgen=True)

print('Saving simulation to cache with runid `%s`' % root['SETTINGS']['EXPERIMENT']['runid'])

root.setdefault('RUN_DB', OMFITtree())
save_location = root['RUN_DB'].setdefault(evalExpr(root['SETTINGS']['EXPERIMENT']['runid']), OMFITtree())

save_location['INPUTS'] = copy.deepcopy(root['INPUTS'])
save_location['OUTPUTS'] = copy.deepcopy(root['OUTPUTS'])
if save_profilesgen:
    save_location['PROFILES_GEN'] = copy.deepcopy(PROFILES_GEN['OUTPUTS'])
