# -*-Python-*-
"""Run the original command box 1 workflow from a single GUI action."""
from datetime import datetime
import copy
from OMFITlib_transfer_workflow import generation_issues, initialize_generation, prepare_tgyro, selected_profile
from OMFITlib_transfer_particles import prepare_particles, species_label

defaultVars(profile_source=None, radial_settings=None)
issues = generation_issues(root, profile_source, radial_settings)
if issues:
    raise ValueError('；'.join(issues))
kind, key = selected_profile(root, profile_source)
outputs = root['OUTPUTS']
output_names = ('Profiles_gen', 'TGYRO', 'Particle_processing')
previous = {name: copy.deepcopy(outputs[name]) for name in output_names if name in outputs}
old_seeds = {name: root['INPUTS'][name] for name in ('input.tgyro', 'input.tglf') if name in root['INPUTS']}
setup = root['SETTINGS']['SETUP']
old_resources = {name: setup.get(name, None) for name in ('p_tgyro', 'num_nodes', 'num_cores')}
old_profile = root['INPUTS'].get('input.gacode', None)
old_transfer_profile = root['Transfer_file'].get('input.gacode', None)
outputs['Profiles_gen'] = OMFITtree()
outputs.pop('TGYRO', None)
try:
    if kind != 'input.gacode':
        print('Transfer_tool：生成 input.gacode …')
        root['SCRIPTS']['profiles_gen.py'].run(profile_source=kind)
        root['INPUTS']['input.gacode'] = outputs['Profiles_gen']['input.gacode'].duplicate()
    source_profile = root['INPUTS']['input.gacode']
    options = radial_settings if radial_settings is not None else initialize_generation(root, OMFITtree)
    profile, report = prepare_particles(source_profile, options)
    root['INPUTS']['input.gacode'] = profile
    outputs['Profiles_gen']['input.gacode'] = profile.duplicate()
    outputs['Particle_processing'] = report
    print('粒子处理后：' + '；'.join(species_label(ion) for ion in report['after']))
    if report.get('thermal_reference', None):
        print('独立热化的温度 / 流速来源：' + species_label(report['thermal_reference']))
    print('准中性：密度残差 {:.3g}，密度梯度残差 {:.3g}。'.format(report['density_residual'], report['gradient_residual']))
    prepare_tgyro(root, profile, radial_settings)
    root['Transfer_file']['input.gacode'] = profile.duplicate()
    print('Transfer_tool：运行 TGYRO …')
    root['SCRIPTS']['tgyro_tglf.py'].run()
    print('Transfer_tool：生成各半径的 input.cgyro / input.tglf …')
    root['SCRIPTS']['profiles_gen4input.py'].run()
    # Keep the imported (or newly generated raw) profile reusable for another preset.
    root['INPUTS']['input.gacode'] = source_profile
except BaseException:
    for name in ('input.tgyro', 'input.tglf'):
        if name in old_seeds:
            root['INPUTS'][name] = old_seeds[name]
        else:
            root['INPUTS'].pop(name, None)
    setup.update(old_resources)
    for name in output_names:
        if name in previous:
            outputs[name] = previous[name]
        else:
            outputs.pop(name, None)
    for branch, value in ((root['INPUTS'], old_profile), (root['Transfer_file'], old_transfer_profile)):
        if value is None:
            branch.pop('input.gacode', None)
        else:
            branch['input.gacode'] = value
    raise
if previous:
    history = outputs.setdefault('History', OMFITtree())
    history[datetime.now().strftime('%Y%m%d_%H%M%S_%f')] = previous
print('Transfer_tool 完成。请在“生成结果与传递”选择要使用的半径输入。')
