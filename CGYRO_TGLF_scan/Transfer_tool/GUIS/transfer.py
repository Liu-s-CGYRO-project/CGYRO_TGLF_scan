# -*-Python-*-
"""Profile and radius controls for Transfer_tool's command-box workflow."""
from collections import OrderedDict
from builtins import dict, next
from OMFITlib_transfer_workflow import generation_issues, initialize_generation, loaded_file, PROFILE_KEYS
from OMFITlib_transfer_particles import PRESETS, DESCRIPTIONS, ion_choices, species_label

# compoundGUI is reserved by OMFIT and must not be reset through defaultVars.
defaultVars(show_run_button=True)
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
    physics['generation']['main_ion'] = 0
    physics['generation']['equivalent_ion'] = 0
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


OMFITx.Label('载入剖面 → 选择粒子方案与半径 → 运行 Transfer_tool', align='left')
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
prefix = "root['SETTINGS']['PHYSICS']['generation']"
OMFITx.Separator('粒子处理')
OMFITx.ComboBox(prefix + "['particle_mode']", PRESETS, '处理方案', updateGUI=True)
source_profile = root['INPUTS'].get('input.gacode', None) if kind == 'input.gacode' else None
if kind != 'input.gacode':
    physics['generation']['main_ion'] = 0
    physics['generation']['equivalent_ion'] = 0
try:
    OMFITx.ComboBox(prefix + "['main_ion']", ion_choices(source_profile), '主离子', updateGUI=True)
    if physics['generation']['particle_mode'] == 'equivalent':
        OMFITx.ComboBox(prefix + "['equivalent_ion']", ion_choices(source_profile, impurity=True),
                       '等效杂质', updateGUI=True)
except (KeyError, TypeError, ValueError) as exc:
    OMFITx.Label('剖面粒子信息：' + str(exc), align='left', wraplength=840)
OMFITx.Label(DESCRIPTIONS.get(physics['generation']['particle_mode'], '请选择粒子方案。'), align='left', wraplength=840)
OMFITx.Label('所有方案均校正密度和密度梯度准中性：电子保持不变，由主离子补齐；每个半径的局部输入再次校正。',
             align='left', wraplength=840)
OMFITx.Label('原始剖面保留。处理后的剖面、粒子组成和校正记录保存在生成结果中。', align='left', wraplength=840)
if source_profile is None and kind != 'input.gacode':
    OMFITx.Label('其他剖面来源在生成 input.gacode 后自动识别粒子；需要指定粒子时，可改用已生成的 input.gacode。',
                 align='left', wraplength=840)
last_report = root['OUTPUTS'].get('Particle_processing', {})
if last_report.get('after', None):
    OMFITx.Label('上次生成：' + '；'.join(species_label(ion) for ion in last_report['after']), align='left', wraplength=840)
    OMFITx.Label('上次校正残差：密度 {:.2g}，密度梯度 {:.2g}；总压力最大相对变化 {:.2%}。'.format(
        last_report.get('density_residual', 0.0), last_report.get('gradient_residual', 0.0),
        last_report.get('max_relative_pressure_change', 0.0)), align='left', wraplength=840)
OMFITx.Separator('计算半径')
OMFITx.ComboBox(prefix + "['coordinate']", OrderedDict([('rho', 'rho'), ('r/a', 'r/a')]), '径向坐标')
with OMFITx.same_row():
    OMFITx.Entry(prefix + "['minimum']", '起始半径', updateGUI=True)
    OMFITx.Entry(prefix + "['maximum']", '结束半径', updateGUI=True)
    OMFITx.Entry(prefix + "['points']", '半径点数', updateGUI=True)
OMFITx.Label('离子数量、质量和电荷从当前剖面自动读取。input.tgyro / input.tglf 沿用已载入文件；缺少时使用内置种子。',
             align='left', wraplength=840)
if show_run_button:
    def run_transfer(location=None):
        root['SCRIPTS']['main.py'].run(profile_source=physics['start_from'],
                                      radial_settings=dict(physics['generation']))
    issues = generation_issues(root, physics['start_from'], physics['generation'])
    OMFITx.Button('运行 Transfer_tool', run_transfer, updateGUI=True,
                 state='disabled' if issues else 'normal', help='；'.join(issues))
    if issues:
        OMFITx.Label('需要补充：' + '；'.join(issues), align='left', wraplength=840)
