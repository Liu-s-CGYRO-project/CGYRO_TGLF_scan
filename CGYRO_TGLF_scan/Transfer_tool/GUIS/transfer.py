# -*-Python-*-
"""Transfer inputs and run only workflows present in this module."""
OMFITx.TitleGUI('输入文件准备与转换')
from builtins import bool, float, int, isinstance, str
from collections import OrderedDict
physics = root['SETTINGS']['PHYSICS']
physics.setdefault('start_from', 'statefile')


def load_profile(location=None):
    kind = root['SETTINGS']['PHYSICS']['start_from']
    filename = scratch.get('profile_filename', '')
    if not filename:
        return
    readers = {'statefile': OMFITnc, 'pfile': OMFITpFile,
               'input.profiles': OMFITgacode, 'input.gacode': OMFITinputgacode}
    root['INPUTS'][kind] = readers[kind](filename)
    if kind == 'input.gacode':
        root['Transfer_file']['input.gacode'] = root['INPUTS'][kind].duplicate()


def load_equilibrium(location=None):
    filename = scratch.get('equilibrium_filename', '')
    if filename:
        root['INPUTS']['gEQDSK'] = OMFITgeqdsk(filename)


def load_conversion_inputs(location=None):
    # Each picker replaces only its requested input, preserving the other files.
    for key in ('input.cgyro', 'input.tglf', 'input.gacode'):
        filename = scratch.get('convert_' + key, '')
        if filename:
            reader = OMFITinputgacode if key == 'input.gacode' else OMFITgacode
            root['Transfer_file'][key] = reader(filename)
            scratch['convert_' + key] = ''


def generate_profiles(location=None):
    root['SCRIPTS']['profiles_gen.py'].run()


def convert_inputs(location=None):
    root['SCRIPTS']['convert_file'].run()


def boolean_checkbox(key, label, default=False):
    # OMFIT CheckBox compares repr(value) with 'False'/'True'. Legacy 0/1,
    # NumPy scalars and string flags otherwise appear as an alternate blue box.
    value = physics.get(key, default)
    if getattr(value, 'shape', None) == () and hasattr(value, 'item'):
        value = value.item()
    if value is None:
        value = False
    elif isinstance(value, str):
        flags = {'false': False, '.false.': False, '0': False,
                 'true': True, '.true.': True, '1': True}
        value = flags.get(value.strip().lower(), value)
    if isinstance(value, (bool, int, float)) and value in (False, True):
        physics[key] = bool(value)
    # Redraw also clears the native alternate state after the default button.
    return OMFITx.CheckBox("root['SETTINGS']['PHYSICS'][{!r}]".format(key), label,
                          default=default, updateGUI=True)


OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['start_from']",
               OrderedDict([('状态文件（statefile）', 'statefile'), ('剖面文件（p-file）', 'pfile'),
                            ('input.profiles', 'input.profiles'), ('input.gacode', 'input.gacode')]),
               lbl='剖面来源', default='statefile', updateGUI=True)
if physics['start_from'] not in ('statefile', 'pfile', 'input.profiles', 'input.gacode'):
    physics['start_from'] = 'input.gacode'
OMFITx.FilePicker("scratch['profile_filename']", '剖面输入文件', default='',
                  updateGUI=True, postcommand=load_profile)
if physics['start_from'] in ('statefile', 'pfile'):
    OMFITx.FilePicker("scratch['equilibrium_filename']", '平衡文件（g-file）', default='',
                      updateGUI=True, postcommand=load_equilibrium)
if physics['start_from'] != 'input.gacode':
    OMFITx.Button('生成 input.gacode', generate_profiles, updateGUI=True)

OMFITx.Label('局部参数转换：载入所需输入，选择转换方向，然后执行转换。')
for key in ('input.cgyro', 'input.tglf', 'input.gacode'):
    OMFITx.FilePicker("scratch['convert_" + key + "']", key, default='',
                      updateGUI=True, postcommand=load_conversion_inputs)
boolean_checkbox('Transfer to cgyro', 'TGLF → CGYRO', default=True)
boolean_checkbox('Transfer to tglf', 'CGYRO → TGLF', default=False)
boolean_checkbox('tglf_is_out_tglf_localdump', 'TGLF 输入来自 out.tglf.localdump', default=False)
OMFITx.Button('转换局部输入', convert_inputs, updateGUI=True)
OMFITx.Label('NEO 与离子排序：工程总控 → 输入准备与转换 → 生成与高级工具 → PROFILES_GEN。')
