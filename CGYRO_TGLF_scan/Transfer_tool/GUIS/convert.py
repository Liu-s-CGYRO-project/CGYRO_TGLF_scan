# -*-Python-*-
"""Local-input conversion, separate from profile generation."""
from collections import OrderedDict
from OMFITlib_transfer_workflow import loaded_file
from omfit_classes.utils_base import evalExpr

OMFITx.TitleGUI('局部输入互转')
physics = root['SETTINGS']['PHYSICS']
if 'conversion_mode' not in physics:
    def flag(key):
        value = evalExpr(physics.get(key, False))
        return str(value).strip().lower() in ('true', '.true.', '1', '1.0')
    physics['conversion_mode'] = ('cgyro_to_tglf' if flag('Transfer to tglf') else
                                  ('dump_to_cgyro' if flag('tglf_is_out_tglf_localdump') else 'tglf_to_cgyro'))


def load_input(key, location=None):
    field = 'convert_' + key
    filename = scratch.get(field, '')
    if not filename:
        return
    reader = OMFITinputgacode if key == 'input.gacode' else OMFITgacode
    value = reader(filename)
    value.keys()
    root['Transfer_file'][key] = value
    scratch[field] = ''


def convert_inputs(location=None):
    mode = physics['conversion_mode']
    physics['Transfer to tglf'] = mode == 'cgyro_to_tglf'
    physics['Transfer to cgyro'] = mode != 'cgyro_to_tglf'
    physics['tglf_is_out_tglf_localdump'] = mode == 'dump_to_cgyro'
    root['SCRIPTS']['convert_file'].run()


OMFITx.Label('转换已有局部输入。目标文件自动生成，完成后到“生成结果与传递”选择使用。', align='left', wraplength=840)
OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['conversion_mode']",
    OrderedDict([('TGLF → CGYRO', 'tglf_to_cgyro'), ('CGYRO → TGLF', 'cgyro_to_tglf'),
                 ('out.tglf.localdump → CGYRO', 'dump_to_cgyro')]), '转换方向', updateGUI=True)
mode = physics['conversion_mode']
required = ('input.cgyro',) if mode == 'cgyro_to_tglf' else ('input.tglf', 'input.gacode')
for key in required:
    label = 'out.tglf.localdump' if key == 'input.tglf' and mode == 'dump_to_cgyro' else key
    OMFITx.FilePicker("scratch['convert_" + key + "']", '载入 / 更换 ' + label, default='',
        postcommand=lambda location=None, key=key: load_input(key, location), updateGUI=True)
    OMFITx.Label(loaded_file(root, 'Transfer_file', key), align='left', wraplength=840)
if 'input.gacode' in required:
    OMFITx.Label('使用与该局部输入对应的 input.gacode；剖面页已经导入的文件可直接使用。', align='left', wraplength=840)
missing = [key for key in required if key not in root['Transfer_file']]
OMFITx.Button('转换并生成 input.' + ('tglf' if mode == 'cgyro_to_tglf' else 'cgyro'), convert_inputs,
             updateGUI=True, state='disabled' if missing else 'normal', help='；'.join('缺少 ' + key for key in missing))
