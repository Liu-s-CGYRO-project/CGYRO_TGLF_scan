# -*-Python-*-
"""Profile and radius controls for Transfer_tool's command-box workflow."""
from collections import OrderedDict
from builtins import dict, next
from OMFITlib_transfer_workflow import generation_issues, initialize_generation, loaded_file, PROFILE_KEYS
from OMFITlib_transfer_particles import (PRESETS, DESCRIPTIONS, detect_main_ions, ion_choices,
                                        main_ion_label, species_label, thermal_reference_choices)

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
    physics['generation']['equivalent_ion'] = 0
    physics['generation']['thermal_reference_ion'] = 0
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


OMFITx.Label('载入剖面 → 设置半径 → 确认主离子与处理方案 → 运行 Transfer_tool', align='left')
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
OMFITx.Separator('计算半径')
OMFITx.ComboBox(prefix + "['coordinate']", OrderedDict([('rho', 'rho'), ('r/a', 'r/a')]), '径向坐标', updateGUI=True)
with OMFITx.same_row():
    OMFITx.Entry(prefix + "['minimum']", '起始半径', updateGUI=True)
    OMFITx.Entry(prefix + "['maximum']", '结束半径', updateGUI=True)
    OMFITx.Entry(prefix + "['points']", '半径点数', updateGUI=True)
OMFITx.Separator('粒子处理')
OMFITx.Label('主离子自动识别：本轮半径范围内，平均 ni/ne 严格大于 30%；通常为 1–2 种，保留全部符合条件的离子。',
             align='left', wraplength=840)
source_profile = root['INPUTS'].get('input.gacode', None) if kind == 'input.gacode' else None
if kind != 'input.gacode':
    physics['generation']['equivalent_ion'] = 0
    physics['generation']['thermal_reference_ion'] = 0
main_ions = []
particle_issue = ''
try:
    if source_profile is not None:
        main_ions = detect_main_ions(source_profile, physics['generation'])
        for ion in main_ions:
            OMFITx.Label('主离子 ' + main_ion_label(ion), align='left', wraplength=840)
    else:
        OMFITx.Label('载入或生成 input.gacode 后自动识别主离子。', align='left')
except (KeyError, TypeError, ValueError, OverflowError) as exc:
    particle_issue = str(exc)
    OMFITx.Label('主离子识别：' + particle_issue, align='left', wraplength=840)
OMFITx.ComboBox(prefix + "['particle_mode']", PRESETS, '处理方案', updateGUI=True)
if not particle_issue:
    if physics['generation']['particle_mode'] == 'equivalent':
        OMFITx.ComboBox(prefix + "['equivalent_ion']", ion_choices(source_profile, main_ions),
                       '等效杂质', updateGUI=True)
    elif physics['generation']['particle_mode'] == 'thermalize':
        OMFITx.ComboBox(prefix + "['thermal_reference_ion']",
                       thermal_reference_choices(source_profile, main_ions),
                       '温度 / 流速来源', updateGUI=True,
                       help='用于对应任一主离子、独立保留的快离子；自动取剖面中首个不属于主离子种类的热离子，也可明确指定。')
OMFITx.Label(DESCRIPTIONS.get(physics['generation']['particle_mode'], '请选择粒子方案。'), align='left', wraplength=840)
OMFITx.Label('电子密度与梯度不变；各半径保持主离子密度比例，共同满足密度与梯度准中性。局部输入再次校正。',
             align='left', wraplength=840)
OMFITx.Label('原始剖面保留。处理后的剖面、粒子组成和校正记录保存在生成结果中。', align='left', wraplength=840)
if source_profile is None and kind != 'input.gacode':
    OMFITx.Label('其他剖面来源在生成 input.gacode 后自动识别；需要指定等效杂质或热化参考时，可改用已生成的 input.gacode。',
                 align='left', wraplength=840)
last_report = root['OUTPUTS'].get('Particle_processing', {})
if last_report.get('main_ions', None):
    OMFITx.Label('上次识别的主离子：' + '；'.join(main_ion_label(ion) for ion in last_report['main_ions']),
                 align='left', wraplength=840)
if last_report.get('thermal_reference', None):
    OMFITx.Label('上次独立热化的温度 / 流速来源：' + species_label(last_report['thermal_reference']),
                 align='left', wraplength=840)
if last_report.get('after', None):
    OMFITx.Label('上次生成：' + '；'.join(species_label(ion) for ion in last_report['after']), align='left', wraplength=840)
    OMFITx.Label('上次校正残差：密度 {:.2g}，密度梯度 {:.2g}；总压力最大相对变化 {:.2%}。'.format(
        last_report.get('density_residual', 0.0), last_report.get('gradient_residual', 0.0),
        last_report.get('max_relative_pressure_change', 0.0)), align='left', wraplength=840)
OMFITx.Label('离子数量、质量和电荷从当前剖面自动读取。input.tgyro / input.tglf 沿用已载入文件；缺少时使用内置种子。',
             align='left', wraplength=840)
if show_run_button:
    def run_transfer(location=None):
        root['SCRIPTS']['main.py'].run(profile_source=physics['start_from'],
                                      radial_settings=dict(physics['generation']))
    issues = generation_issues(root, physics['start_from'], physics['generation'])
    if particle_issue:
        issues.append(particle_issue)
    OMFITx.Button('运行 Transfer_tool', run_transfer, updateGUI=True,
                 state='disabled' if issues else 'normal', help='；'.join(issues))
    if issues:
        OMFITx.Label('需要补充：' + '；'.join(issues), align='left', wraplength=840)
