# -*-Python-*-
# Created by jinyue_liu at 28 Sep 2025  15:04


OMFITx.TitleGUI('CYTG GUI')

#root.setdefault('scanResults', OMFITtree())
#root.setdefault('scanResults2D', OMFITtree())
#root.setdefault('input.tglf', OMFITtree())
#root.setdefault('tgyro_output', OMFITtree())

#param = root['TGLF']['SETTINGS']['PHYSICS']['scanParameter']
#param2 = root['TGLF']['SETTINGS']['PHYSICS']['scanParameter2D']


OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['tglf_input_load']",
    "Load input.tglf file - !load it before input.gacode!",
    default=False,
    updateGUI=True,
    help='This CheckBox oppens the GUI where the input.tglf file can be loaded. Click "Pick a different input.tglf file" to load a new file.',
)

OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['tglf_settings_from_TGYRO']",
    "Load TGLF settings tab from TGYRO GUI",
    default=False,
    updateGUI=True,
    help='This CheckBox loads the same GUI as in TGYRO module to specify TGLF settings, otherwise the old TGLF_scan GUI will be loaded.',
)



OMFITx.Tab('Transfer_input_file')

OMFITx.CompoundGUI(root['TGLF_scan']['TGYRO']['PROFILES_GEN']['GUIS']['standaloneGUI'])
