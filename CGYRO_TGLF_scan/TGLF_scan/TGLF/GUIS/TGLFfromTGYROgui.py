# -*-Python-*-
# Created by avdeevag at 01 Mar 2023  07:25

OMFITx.TitleGUI('TGLF GUI')

defaultVars(
    inp_loc="root['FILES']['input.tglf']",
    guis_loc=None,
    settings_loc_str=None,
    inp_loc_tgyro_str=None,
    showButtons=True,
    allowOptions=['TGLF', 'TGLF-NN', 'wavefunction'],
    showLocalTab=True,
    showNumSpecies=True,
)
try:
    input_tglf = eval(inp_loc)
except Exception:
    OMFITx.ObjectPicker(inp_loc, lbl='input.tglf file', objectType=OMFITgacode)
    OMFITx.End()
if 'USE_TRANSPORT_MODEL' not in input_tglf:
    OMFITx.Label("This GUI is only valid for a TGLF input file (usually named input.tglf)")
    OMFITx.End()

options = {
    'TGLF-NN': ("Get fluxes with neural-network model", [True, 1e6]),
    'TGLF': ("Get growth rate spectra and fluxes", [True, -1.0]),
    'wavefunction': ("Get wavefunction at set ky", [False, -1.0]),
}

OMFITx.ComboBox(
    [inp_loc + "['USE_TRANSPORT_MODEL']", inp_loc + "['NN_MAX_ERROR']"],
    {options[k][0]: options[k][1] for k in allowOptions},
    "TGLF mode",
    updateGUI=True,
    default=[True, -1.0],
)

if eval(inp_loc + "['USE_TRANSPORT_MODEL']") and eval(inp_loc + "['NN_MAX_ERROR']") > 0:
    for item in root['TEMPLATES']['input.tglf.nn']:
        OMFITx.Lock(inp_loc + "['%s']" % str(item), root['TEMPLATES']['input.tglf.nn'][item])

root['SETTINGS']['PHYSICS']['Turb_Model'] = 'TGLF'
OMFITx.CompoundGUI(guis_loc, inp_loc=inp_loc)
