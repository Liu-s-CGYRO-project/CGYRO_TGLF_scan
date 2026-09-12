# -*-Python-*-
# Created by meneghini at 2015/02/12 10:14

defaultVars(deadstart=False, test=True)


def setdefault(location=None):
    if root['SETTINGS']['PHYSICS']['rho_nml'] == 0:
        root['SETTINGS']['PHYSICS']['rho_core'] = 0.1
        root['SETTINGS']['PHYSICS']['rho_ped'] = 0.0
    if root['SETTINGS']['PHYSICS']['rho_nml'] != 0 and root['SETTINGS']['PHYSICS']['rho_ped'] == 0:
        root['SETTINGS']['PHYSICS']['rho_core'] = 0.3
        root['SETTINGS']['PHYSICS']['rho_ped'] = 0.9


nml = root['SETTINGS']['PHYSICS']['rho_nml']
if root['SETTINGS']['PHYSICS']['rho_nml'] <= 0:
    nml = 0.8

setdefault()
OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['rho_nml']", "Use EPED profiles", mapFalseTrue=[nml, 0.0], updateGUI=True, postcommand=setdefault
)
if root['SETTINGS']['PHYSICS']['rho_nml'] != 0:
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['rho_core']", 'Core domain', updateGUI=True)
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['rho_nml']", "no-man's-land domain", updateGUI=True)
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['rho_ped']", "Pedestal domain", updateGUI=True)

if deadstart:
    OMFITx.Button("Preview dead-start profiles", lambda: root['SCRIPTS']['blendEPED'].runNoGUI(deadstart=deadstart, test=True))
    OMFITx.TitleGUI("EPED dead-start")
else:
    if 'input.gacode_base' in root['OUTPUTS']:
        OMFITx.Button("Preview blend profiles", lambda: root['SCRIPTS']['blendEPED'].runNoGUI(deadstart=deadstart, test=True))
    else:
        OMFITx.Label("No input.gacode to show preview")
    OMFITx.TitleGUI("EPED profiles blender")
