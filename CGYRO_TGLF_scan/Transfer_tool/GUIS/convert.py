# -*-Python-*-
"""Two conversion directions; infer TGLF input format from its fields."""
from collections import OrderedDict
from OMFITlib_transfer_workflow import tglf_input_format
from OMFITlib_gui_layout import finish_gui_layout
from omfit_classes.utils_base import evalExpr

OMFITx.TitleGUI('局部输入互转')
anchor = OMFITx.Label('', align='left')
anchor.master.pack_forget()
physics = root['SETTINGS']['PHYSICS']
if 'conversion_mode' not in physics:
    old = str(evalExpr(physics.get('Transfer to tglf', False))).lower()
    physics['conversion_mode'] = 'cgyro_to_tglf' if old in ('true', '.true.', '1', '1.0') else 'tglf_to_cgyro'
if physics['conversion_mode'] == 'dump_to_cgyro':
    physics['conversion_mode'] = 'tglf_to_cgyro'
sources = physics.setdefault('conversion_sources', OMFITtree())


def source_path(key):
    saved = sources.get(key, {}).get('path', '')
    if key == 'input.gacode' and not saved:
        saved = physics.get('file_sources', {}).get('input.gacode', {}).get('path', '')
    return str(saved or '')


def load_input(key, location=None):
    field = 'convert_' + key
    filename = scratch.get(field, '')
    if not filename:
        return
    if isinstance(filename, (tuple, list)):
        path, server, tunnel = filename
    else:
        path, server, tunnel = str(filename), 'localhost', ''
    reader = OMFITinputgacode if key == 'input.gacode' else OMFITgacode
    value = reader(path, server=server or 'localhost', tunnel=tunnel or '')
    value.keys()
    if key == 'input.tglf':
        tglf_input_format(value, for_conversion=True)
    elif key == 'input.cgyro' and 'N_SPECIES' not in value:
        raise ValueError('所选文件不是 CGYRO 局部输入，缺少 N_SPECIES。')
    root['Transfer_file'][key] = value
    sources[key] = dict(path=str(path), server=str(server or 'localhost'), tunnel=str(tunnel or ''))
    scratch[field] = str(path)


def convert_inputs(location=None):
    mode = physics['conversion_mode']
    physics['Transfer to tglf'] = mode == 'cgyro_to_tglf'
    physics['Transfer to cgyro'] = mode != 'cgyro_to_tglf'
    root['SCRIPTS']['convert_file'].run()


OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['conversion_mode']",
    OrderedDict([('TGLF → CGYRO', 'tglf_to_cgyro'), ('CGYRO → TGLF', 'cgyro_to_tglf')]),
    '转换方向', state='readonly', updateGUI=True)
mode = physics['conversion_mode']
required = ('input.cgyro',) if mode == 'cgyro_to_tglf' else ('input.tglf', 'input.gacode')
problems = []
for key in required:
    label = 'TGLF 局部文件' if key == 'input.tglf' else ('对应剖面 input.gacode' if key == 'input.gacode' else key)
    scratch['convert_' + key] = source_path(key)
    OMFITx.FilePicker("scratch['convert_" + key + "']", label, default='', transferRemoteFile=None,
        postcommand=lambda location=None, key=key: load_input(key, location), updateGUI=True)
    value = root['Transfer_file'].get(key, None)
    if value is None:
        problems.append('缺少 ' + key)
        OMFITx.Label('尚未载入', align='left')
    elif key == 'input.tglf':
        try:
            detected = tglf_input_format(value, for_conversion=True)
            caption = 'out.tglf.localdump（含展开几何）' if detected == 'localdump' else 'input.tglf'
            OMFITx.Label('已识别：' + caption, align='left')
        except ValueError as exc:
            problems.append(str(exc))
            OMFITx.Label(str(exc), align='left', wraplength=600)
    else:
        OMFITx.Label(key + ' 已载入', align='left')
if mode == 'tglf_to_cgyro':
    OMFITx.Label('支持 input.tglf / out.tglf.localdump，自动识别。对应剖面用于计算二阶梯度。',
                 align='left', wraplength=600)
OMFITx.Button('生成 input.' + ('tglf' if mode == 'cgyro_to_tglf' else 'cgyro'), convert_inputs,
    updateGUI=True, state='disabled' if problems else 'normal', help='；'.join(problems))
OMFITx.Label('完成后可在“生成文件”查看、编辑；计算页面直接选择生成的文件。', align='left', wraplength=600)
finish_gui_layout(anchor, OMFITx)
