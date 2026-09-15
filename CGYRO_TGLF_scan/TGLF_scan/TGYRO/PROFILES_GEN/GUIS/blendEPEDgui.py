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
    "root['SETTINGS']['PHYSICS']['rho_nml']", '使用 EPED 剖面', mapFalseTrue=[nml, 0.0], updateGUI=True, postcommand=setdefault
)
if root['SETTINGS']['PHYSICS']['rho_nml'] != 0:
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['rho_core']", '芯部区域', updateGUI=True)
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['rho_nml']", '过渡区域', updateGUI=True)
    OMFITx.Entry("root['SETTINGS']['PHYSICS']['rho_ped']", '台基区域', updateGUI=True)

if deadstart:
    OMFITx.Button('预览初始剖面', lambda: root['SCRIPTS']['blendEPED'].runNoGUI(deadstart=deadstart, test=True))
    OMFITx.TitleGUI('EPED 初始剖面')
else:
    if 'input.gacode_base' in root['OUTPUTS']:
        OMFITx.Button('预览混合剖面', lambda: root['SCRIPTS']['blendEPED'].runNoGUI(deadstart=deadstart, test=True))
    else:
        OMFITx.Label('尚无 input.gacode，无法预览。')
    OMFITx.TitleGUI('EPED 剖面混合')
