# -*-Python-*-
# Created by avdeevag at 01 Mar 2023  07:25

OMFITx.TitleGUI('TGLF 参数设置')

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
    OMFITx.ObjectPicker(inp_loc, lbl='input.tglf 输入文件', objectType=OMFITgacode)
    OMFITx.End()
if 'USE_TRANSPORT_MODEL' not in input_tglf:
    OMFITx.Label('此页面需要有效的 TGLF 输入文件，通常为 input.tglf。')
    OMFITx.End()

options = {
    'TGLF-NN': ('使用神经网络模型计算通量', [True, 1e6]),
    'TGLF': ('计算增长率谱与通量', [True, -1.0]),
    'wavefunction': ('计算指定 ky 的本征函数', [False, -1.0]),
}

OMFITx.ComboBox(
    [inp_loc + "['USE_TRANSPORT_MODEL']", inp_loc + "['NN_MAX_ERROR']"],
    {options[k][0]: options[k][1] for k in allowOptions},
    'TGLF 计算模式',
    updateGUI=True,
    default=[True, -1.0],
)

if eval(inp_loc + "['USE_TRANSPORT_MODEL']") and eval(inp_loc + "['NN_MAX_ERROR']") > 0:
    for item in root['TEMPLATES']['input.tglf.nn']:
        OMFITx.Lock(inp_loc + "['%s']" % str(item), root['TEMPLATES']['input.tglf.nn'][item])

root['SETTINGS']['PHYSICS']['Turb_Model'] = 'TGLF'
OMFITx.CompoundGUI(guis_loc, inp_loc=inp_loc)
