# -*-Python-*-
"""Profile and radius controls for Transfer_tool's command-box workflow."""
from collections import OrderedDict
from builtins import dict, next
from OMFITlib_transfer_workflow import generation_issues, initialize_generation, loaded_file, PROFILE_KEYS
from OMFITlib_gui_layout import finish_gui_layout
from OMFITlib_transfer_particles import (PRESETS, DESCRIPTIONS, detect_main_ions,
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


OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['start_from']",
               OrderedDict([('input.gacode', 'input.gacode'), ('状态文件（statefile）', 'statefile'),
                            ('剖面文件（p-file）', 'pfile'), ('input.profiles', 'input.profiles')]),
               lbl='剖面来源', default='input.gacode', updateGUI=True)
kind = physics['start_from']
key = next((key for key in PROFILE_KEYS[kind] if key in root['INPUTS']), kind)
OMFITx.FilePicker("scratch['profile_filename']", '剖面文件', default='',
                  updateGUI=True, postcommand=load_profile, help=loaded_file(root, 'INPUTS', key))
anchor = OMFITx.Label('当前剖面：' + key + ('（已载入）' if key in root['INPUTS'] else '（未载入）'), align='left')
if kind in ('statefile', 'pfile'):
    OMFITx.FilePicker("scratch['equilibrium_filename']", '平衡文件（p-file 必需）', default='',
                      updateGUI=True, postcommand=load_equilibrium, help=loaded_file(root, 'INPUTS', 'gEQDSK'))
    OMFITx.Label('平衡文件：' + ('已载入' if 'gEQDSK' in root['INPUTS'] else '未载入'), align='left')
prefix = "root['SETTINGS']['PHYSICS']['generation']"
OMFITx.Separator('计算半径')
OMFITx.ComboBox(prefix + "['coordinate']", OrderedDict([('rho', 'rho'), ('r/a', 'r/a')]), '径向坐标', updateGUI=True)
with OMFITx.same_row():
    OMFITx.Entry(prefix + "['minimum']", '起始半径', updateGUI=True)
    OMFITx.Entry(prefix + "['maximum']", '结束半径', updateGUI=True)
    OMFITx.Entry(prefix + "['points']", '半径点数', updateGUI=True)
OMFITx.Separator('粒子处理')
source_profile = root['INPUTS'].get('input.gacode', None) if kind == 'input.gacode' else None
if kind != 'input.gacode':
    physics['generation']['thermal_reference_ion'] = 0
main_ions = []
particle_issue = ''
try:
    if source_profile is not None:
        main_ions = detect_main_ions(source_profile, physics['generation'])
        OMFITx.Label('主离子：' + ' · '.join('{}{} {:.2%}'.format(
            ion['name'], '（快）' if ion['kind'] == 'fast' else '', ion['mean_fraction']) for ion in main_ions),
            align='left', wraplength=840)
    else:
        OMFITx.Label('主离子：待识别', align='left')
except (KeyError, TypeError, ValueError, OverflowError) as exc:
    particle_issue = str(exc)
    OMFITx.Label('主离子识别：' + particle_issue, align='left', wraplength=840)
details = [
    '主离子：所选半径区间内平均 ni/ne > 30%，全部保留。',
    '所有方案均保持主离子密度比例，并校正密度和密度梯度准中性。',
    DESCRIPTIONS.get(physics['generation']['particle_mode'], '请选择粒子方案。'),
    '原始剖面保留；处理结果及记录保存到 OUTPUTS/Particle_processing。',
]
if main_ions:
    details.append('当前识别：\n' + '\n'.join(main_ion_label(ion) for ion in main_ions))
if source_profile is None and kind != 'input.gacode':
    details.append('其他剖面来源在生成 input.gacode 后自动识别；指定热化参考时可使用已生成的 input.gacode。')
last_report = root['OUTPUTS'].get('Particle_processing', {})
if last_report.get('after', None):
    details.append('上次剖面组成：\n' + '\n'.join(species_label(ion) for ion in last_report['after']))
    if last_report.get('equivalent_stage', None) == 'local_inputs':
        details.append('各半径等效杂质的 Z、密度、MASS 和来源记录在 OUTPUTS/Particle_processing/local_inputs。')
    details.append('上次残差：密度 {:.2g}，梯度 {:.2g}；总压力最大相对变化 {:.2%}。'.format(
        last_report.get('density_residual', 0.0), last_report.get('gradient_residual', 0.0),
        last_report.get('max_relative_pressure_change', 0.0)))
if last_report.get('thermal_reference', None):
    details.append('上次热化参考：' + species_label(last_report['thermal_reference']))
OMFITx.ComboBox(prefix + "['particle_mode']", PRESETS, '处理方案', updateGUI=True, help='\n\n'.join(details))
if not particle_issue:
    if physics['generation']['particle_mode'] == 'thermalize':
        OMFITx.ComboBox(prefix + "['thermal_reference_ion']",
                       thermal_reference_choices(source_profile, main_ions),
                       '温度 / 流速来源', updateGUI=True,
                       help='用于对应任一主离子、独立保留的快离子；自动取剖面中首个不属于主离子种类的热离子，也可明确指定。')
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
    finish_gui_layout(anchor, OMFITx)
