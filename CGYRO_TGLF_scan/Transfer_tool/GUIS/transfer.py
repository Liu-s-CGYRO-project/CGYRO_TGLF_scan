# -*-Python-*-
"""Profile and radius controls for Transfer_tool's command-box workflow."""
from collections import OrderedDict
from builtins import dict, next
from OMFITlib_transfer_workflow import generation_issues, initialize_generation, loaded_file, PROFILE_KEYS

defaultVars(compoundGUI=False)
OMFITx.TitleGUI('Transfer_tool · 剖面生成')
physics = root['SETTINGS']['PHYSICS']
initialize_generation(root, OMFITtree)


def load_profile(location=None):
    filename = scratch.get('profile_filename', '')
    if not filename:
        return
    kind = physics['start_from']
    readers = {'statefile': OMFITnc, 'pfile': OMFITpFile,
               'input.profiles': OMFITgacode, 'input.gacode': OMFITinputgacode}
    value = readers[kind](filename)
    value.keys()
    root['INPUTS'][kind] = value
    if kind == 'input.gacode':
        root['Transfer_file']['input.gacode'] = value.duplicate()
    scratch['profile_filename'] = ''


def load_equilibrium(location=None):
    filename = scratch.get('equilibrium_filename', '')
    if filename:
        value = OMFITgeqdsk(filename)
        value.keys()
        root['INPUTS']['gEQDSK'] = value
        scratch['equilibrium_filename'] = ''


OMFITx.Label('载入剖面 → 设置半径 → 运行 Transfer_tool', align='left')
OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['start_from']",
               OrderedDict([('input.gacode', 'input.gacode'), ('状态文件（statefile）', 'statefile'),
                            ('剖面文件（p-file）', 'pfile'), ('input.profiles', 'input.profiles')]),
               lbl='剖面来源', default='input.gacode', updateGUI=True)
OMFITx.FilePicker("scratch['profile_filename']", '载入 / 更换剖面', default='',
                  updateGUI=True, postcommand=load_profile)
kind = physics['start_from']
key = next((key for key in PROFILE_KEYS[kind] if key in root['INPUTS']), kind)
OMFITx.Label(loaded_file(root, 'INPUTS', key), align='left', wraplength=840)
if kind in ('statefile', 'pfile'):
    OMFITx.FilePicker("scratch['equilibrium_filename']", '平衡文件（p-file 必需）', default='',
                      updateGUI=True, postcommand=load_equilibrium)
    OMFITx.Label(loaded_file(root, 'INPUTS', 'gEQDSK'), align='left', wraplength=840)
OMFITx.Separator('计算半径')
prefix = "root['SETTINGS']['PHYSICS']['generation']"
OMFITx.ComboBox(prefix + "['coordinate']", OrderedDict([('rho', 'rho'), ('r/a', 'r/a')]), '径向坐标')
with OMFITx.same_row():
    OMFITx.Entry(prefix + "['minimum']", '起始半径', updateGUI=True)
    OMFITx.Entry(prefix + "['maximum']", '结束半径', updateGUI=True)
    OMFITx.Entry(prefix + "['points']", '半径点数', updateGUI=True)
OMFITx.Label('离子数量、质量和电荷从当前剖面自动读取。input.tgyro / input.tglf 沿用已载入文件；缺少时使用内置种子。',
             align='left', wraplength=840)
if not compoundGUI:
    def run_transfer(location=None):
        root['SCRIPTS']['main.py'].run(profile_source=physics['start_from'],
                                      radial_settings=dict(physics['generation']))
    issues = generation_issues(root, physics['start_from'], physics['generation'])
    OMFITx.Button('运行 Transfer_tool', run_transfer, updateGUI=True,
                 state='disabled' if issues else 'normal', help='；'.join(issues))
    if issues:
        OMFITx.Label('需要补充：' + '；'.join(issues), align='left', wraplength=840)
