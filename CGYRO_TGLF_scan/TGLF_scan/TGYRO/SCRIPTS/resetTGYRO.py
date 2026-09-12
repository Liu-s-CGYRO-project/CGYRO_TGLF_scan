# -*-Python-*-
# Created by meneghini at 2013/05/06 11:42

defaultVars(soft=None)

if soft:
    print('Reset TGYRO (soft)')
    if root['INPUTS']['input.tgyro']['LOC_RESTART_FLAG'] != 1:
        root['OUTPUTS'].clear()
else:
    print('Reset TGYRO')
    root['RUN_DB'].clear()
    root['OUTPUTS'].clear()
    # root['INPUTS'].clear() #This is more of a template

if PROFILES_GEN is not None and root['SETTINGS']['PHYSICS']['runPROFILES_GEN']:
    PROFILES_GEN['SCRIPTS']['reset'].runNoGUI(soft=soft)
