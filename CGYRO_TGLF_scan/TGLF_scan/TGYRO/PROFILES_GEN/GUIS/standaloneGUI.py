# -*-Python-*-
# Created by smithsp at 2014/05/12 12:53

OMFITx.TitleGUI('profiles_gen GUI')


def loadg(location=None):
    if scratch['geqdsk_fn']:
        try:
            root['INPUTS']['gEQDSK'] = OMFITgeqdsk(scratch['geqdsk_fn'])
            root['INPUTS']['gEQDSK'].keys()
        except Exception:
            root['INPUTS']['gEQDSK'] = OMFITpath(scratch['geqdsk_fn'])
        root['SETTINGS']['DEPENDENCIES']['gEQDSK'] = "root['INPUTS']['gEQDSK']"


def delg(location=None):
    del root['INPUTS']['gEQDSK']
    root['OUTPUTS'].clear()


def loadstate(location=None):
    if scratch['statefile_fn']:
        root['INPUTS']['statefile'] = OMFITnc(scratch['statefile_fn'])
        root['SETTINGS']['DEPENDENCIES']['profpowbal'] = "root['INPUTS']['statefile']"


def delstate(location=None):
    del root['INPUTS']['statefile']
    root['OUTPUTS'].clear()


def loadp(location=None):
    if scratch['pfile_fn']:
        root['INPUTS']['pfile'] = OMFITpFile(scratch['pfile_fn'])
        root['SETTINGS']['DEPENDENCIES']['profpowbal'] = "root['INPUTS']['pfile']"


def delp(location=None):
    del root['INPUTS']['pfile']
    root['OUTPUTS'].clear()


def load_cer(location=None):
    if scratch['cer_fn']:
        root['INPUTS']['CER'] = OMFITasciitable(scratch['cer_fn'])
        root['SETTINGS']['DEPENDENCIES']['CER'] = "root['INPUTS']['CER']"


def del_cer(location=None):
    del root['INPUTS']['CER']
    root['OUTPUTS'].clear()


def load_input_gacode(location=None):
    if scratch['input.gacode_fn']:
        for k in ['INPUTS', 'OUTPUTS']:
            if k == 'INPUTS' or scratch['input_ok_as_output']:
                root[k]['input.gacode'] = OMFITinputgacode(scratch['input.gacode_fn'])
                root[k]['input.gacode_base'] = OMFITinputgacode(scratch['input.gacode_fn'])

        root['SETTINGS']['DEPENDENCIES']['profpowbal'] = "root['INPUTS']['input.gacode']"


def del_input_gacode(location=None):
    if 'input.gacode' in root['INPUTS']:
        del root['INPUTS']['input.gacode']
    root['OUTPUTS'].clear()


def load_ods(location=None):
    root['SETTINGS']['DEPENDENCIES']['profpowbal'] = "root['INPUTS']['ods']"
    if scratch['input_ok_as_output']:
        root['OUTPUTS']['input.gacode'] = OMFITinputgacode('input.gacode').from_omas(root['INPUTS']['ods'])

choices = {'Statefile and g-file': 'statefile',
           'p-File and g-file': 'pfile',
           'input.gacode file': 'input.gacode'
           }

OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['start_from']",
    choices,
    lbl='Start from',
    updateGUI=True,
    default='statefile',
    postcommand=lambda location: root['SCRIPTS']['reset'].runNoGUI(),
)

ok = False
if root['SETTINGS']['PHYSICS']['start_from'] == 'ODS':

    OMFITx.ObjectPicker("root['INPUTS']['ods']", 'ODS', None, postcommand=load_ods, unset_postcommand=del_input_gacode)
    if profpowbal is None or not isinstance(profpowbal, ODS):
        OMFITx.CheckBox("scratch['input_ok_as_output']", 'Load ODS and use it as valid PROFILES_GEN output', default=True)
    if 'ods' in root['INPUTS']:
        ok = True

elif root['SETTINGS']['PHYSICS']['start_from'] in ['statefile', 'pfile']:
    ok = True

    if root['SETTINGS']['PHYSICS']['start_from'] == 'statefile':
        OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['use_trxpl']", 'Use TRXPL', default=False, updateGUI=True)
        if root['SETTINGS']['PHYSICS']['use_trxpl'] == True:
            OMFITx.CompoundGUI(root['TRXPL']['GUIS']['TRXPLgui'], '')
            root['SETTINGS']['DEPENDENCIES']['profpowbal'] = "root['TRXPL']['OUTPUTS']['statefile']"
            root['SETTINGS']['DEPENDENCIES']['gEQDSK'] = "root['TRXPL']['OUTPUTS']['gEQDSK']"
        if 'statefile' not in root['INPUTS'] and (profpowbal is None or not isinstance(profpowbal, OMFITnc)):
            OMFITx.FilePicker("scratch['statefile_fn']", 'Power-balance file', updateGUI=True, postcommand=loadstate, default='')
            ok = False
        elif (profpowbal is not None and isinstance(profpowbal, OMFITnc)) and "root['INPUTS']" not in root['SETTINGS']['DEPENDENCIES'][
            'profpowbal'
        ]:
            OMFITx.Label(' * Statefile dependency ' + root['SETTINGS']['DEPENDENCIES']['profpowbal'] + ' is satisfied', align='left')
        else:
            OMFITx.Button('Change statefile', delstate, updateGUI=True)
    if root['SETTINGS']['PHYSICS']['start_from'] == 'pfile':
        if 'pfile' not in root['INPUTS'] and (profpowbal is None or not isinstance(profpowbal, OMFITpFile)):
            OMFITx.FilePicker("scratch['pfile_fn']", 'Osborne p-File', updateGUI=True, postcommand=loadp, default='')
            ok = False
        elif (profpowbal is not None and isinstance(profpowbal, OMFITpFile)) and "root['INPUTS']" not in root['SETTINGS']['DEPENDENCIES'][
            'profpowbal'
        ]:
            OMFITx.Label(' * pFile dependency ' + root['SETTINGS']['DEPENDENCIES']['profpowbal'] + ' is satisfied', align='left')
        else:
            OMFITx.Button('Change p-File', delp, updateGUI=True)

    if 'gEQDSK' not in root['INPUTS'] and gEQDSK is None:
        if root['SETTINGS']['PHYSICS']['start_from'] == 'pfile':
            OMFITx.FilePicker("scratch['geqdsk_fn']", 'equilibrium file', updateGUI=True, postcommand=loadg, default='')
            ok = False
        else:
            OMFITx.FilePicker("scratch['geqdsk_fn']", 'equilibrium file (optional)', updateGUI=True, postcommand=loadg, default='')
    elif gEQDSK is not None and "root['INPUTS']" not in root['SETTINGS']['DEPENDENCIES']['gEQDSK']:
        OMFITx.Label(' * gEQDSK dependency ' + root['SETTINGS']['DEPENDENCIES']['gEQDSK'] + ' is satisfied', align='left')
    else:
        OMFITx.Button('Change g file', delg, updateGUI=True)

    if 'CER' not in root['INPUTS'] and CER is None:
        OMFITx.FilePicker("scratch['cer_fn']", 'CER file (optional)', updateGUI=True, postcommand=load_cer, default='')
    elif CER is not None and "root['INPUTS']" not in root['SETTINGS']['DEPENDENCIES']['CER']:
        OMFITx.Label(' * CER dependency ' + root['SETTINGS']['DEPENDENCIES']['CER'] + ' is satisfied', align='left')
    else:
        OMFITx.Button('Change CER file', del_cer, updateGUI=True)

elif root['SETTINGS']['PHYSICS']['start_from'] == 'input.gacode':
    ok = True

    if 'input.gacode' not in root['INPUTS'] and (profpowbal is None or not isinstance(profpowbal, OMFITgacode)):
        OMFITx.FilePicker("scratch['input.gacode_fn']", 'input.gacode file', updateGUI=True, postcommand=load_input_gacode, default='')
        OMFITx.CheckBox("scratch['input_ok_as_output']", 'Load `input.gacode` and use it as valid PROFILES_GEN output', default=True)
        ok = False
    elif (profpowbal is not None and isinstance(profpowbal, OMFITgacode)) and "root['INPUTS']" not in root['SETTINGS']['DEPENDENCIES'][
        'profpowbal'
    ]:
        OMFITx.Label(' * input.gacode dependency ' + root['SETTINGS']['DEPENDENCIES']['profpowbal'] + ' is satisfied', align='left')
    else:
        OMFITx.Button('Change input_gacode', del_input_gacode, updateGUI=True)

if ok:
    OMFITx.CompoundGUI(root['GUIS']['vgenGUI'], showRunButton=True)

OMFITx.Button('Plot selected inputs', "root['PLOTS']['plot_input'].runNoGUI")
