# -*-Python-*-
# Created by meneghini at 2013/05/06 11:48

defaultVars(soft=True)

if soft:
    print('Reset PROFILES_GEN (soft)')
    if 'input.gacode' in root['OUTPUTS']:
        del root['OUTPUTS']['input.gacode']
else:
    print('Reset PROFILES_GEN')
    root['OUTPUTS'].clear()
    root['INPUTS'].clear()
    root['SETTINGS']['PHYSICS']['reorder_ion_names'] = None
