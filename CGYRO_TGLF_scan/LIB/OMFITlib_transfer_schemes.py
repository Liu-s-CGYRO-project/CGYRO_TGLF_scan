"""Small frozen Transfer input sets; solver results remain exclusively in RUN_DB.

Generation is an explicit action. Selectors read only the saved radius/option
metadata; they never regenerate inputs or inspect CGYRO output files.
"""
from builtins import ValueError, dict, hasattr, int, list, sorted, str
from collections import OrderedDict
import copy
from OMFITlib_project_inputs import input_digest, validate_input
from OMFITlib_transfer_workflow import generation_issues, selected_profile


SCHEMES = OrderedDict([
    ('all', ('保留所有粒子', dict(particle_mode='all'))),
    ('thermalize', ('慢化快离子（热化处理）', dict(particle_mode='thermalize'))),
    ('equivalent_pressure', ('等效杂质 · 保留原总压力',
                             dict(particle_mode='equivalent', equivalent_temperature='pressure'))),
    ('equivalent_main_ion', ('等效杂质 · 温度随热主离子',
                             dict(particle_mode='equivalent', equivalent_temperature='main_ion'))),
    ('separate_fast', ('主离子 / 等效杂质 / 等效快粒子', dict(particle_mode='separate_fast'))),
    ('main_only', ('仅保留主离子和 Zeff', dict(particle_mode='main_only'))),
])


def scheme_runid(base, scheme):
    """Use the existing result-name namespace, without changing result identity."""
    return str(base) + '__transfer_' + scheme if scheme else str(base)


def _duplicate(value):
    return value.duplicate() if hasattr(value, 'duplicate') else copy.deepcopy(value)


def _freeze(outputs, options, label, factory):
    generated = outputs.get('Profiles_gen', {})
    report = outputs.get('Particle_processing', {})
    inputs, local = factory(), {}
    for key in generated.keys():
        if not str(key).startswith('input.cgyro_'):
            continue
        source = generated[key]
        validate_input(source, 'cgyro')
        metadata = report.get('local_inputs', {}).get(key, {})
        if metadata.get('rho', None) is None:
            raise ValueError(label + ' / ' + key + ' 缺少半径记录。')
        inputs[key] = _duplicate(source)
        # The generation report also contains full profile arrays. Retain only
        # the local provenance required by isotope preparation and inspection.
        local[key] = {name: copy.deepcopy(metadata[name])
                      for name in ('rho', 'main_count', 'rhostar', 'equivalent',
                                   'prescribed_zeff', 'final_neutrality') if name in metadata}
    if not inputs:
        raise ValueError(label + ' 没有生成 CGYRO 输入。')
    frozen = factory()
    # File-bearing containers must be OMFITtree in a real session so project
    # save/update follows the file references instead of pickling the readers.
    frozen.update(dict(label=label, options=dict(options), inputs=inputs,
                       particle_record=dict(options=copy.deepcopy(report.get('options', options)),
                                            main_count=report.get('main_count', None), local_inputs=local)))
    return frozen


def generate_schemes(node, flags, options, generate, factory=dict):
    """Generate each preset from the same source, then atomically install cards.

    Separate small working branches keep the normal Transfer result and seeds
    untouched. Failure/interrupt preserves the previous complete scheme set.
    No project snapshots, CGYRO results, or pending jobs are copied.
    """
    chosen = [(key, label, dict(options, **overrides))
              for key, (label, overrides) in SCHEMES.items() if flags.get(key, False)]
    if not chosen:
        raise ValueError('至少勾选一个转换方案。')
    source = node['SETTINGS']['PHYSICS']['start_from']
    for key, label, settings in chosen:
        issues = generation_issues(node, source, settings)
        if issues:
            raise ValueError(label + '：' + '；'.join(issues))
    _, source_key = selected_profile(node, source)
    digest = input_digest(node['INPUTS'][source_key])
    original = {name: node[name] for name in ('OUTPUTS', 'INPUTS', 'Transfer_file')}
    setup = node['SETTINGS']['SETUP']
    setup_values = copy.deepcopy(dict(setup))
    prepared = factory()
    try:
        for key, label, settings in chosen:
            node['OUTPUTS'], node['INPUTS'], node['Transfer_file'] = factory(), factory(), factory()
            for name in original['INPUTS'].keys():
                node['INPUTS'][name] = _duplicate(original['INPUTS'][name])
            setup.clear()
            setup.update(copy.deepcopy(setup_values))
            generate(source, settings, label)
            frozen = _freeze(node['OUTPUTS'], settings, label, factory)
            frozen.update(dict(source_kind=source, source_digest=digest))
            prepared[key] = frozen
    finally:
        for name, value in original.items():
            node[name] = value
        setup.clear()
        setup.update(setup_values)
    node['OUTPUTS']['CGYRO_schemes'] = prepared
    return list(prepared)


def scheme_sources(root):
    """Project source rows compatible with the ordinary CGYRO planner."""
    groups = root.get('Transfer_tool', {}).get('OUTPUTS', {}).get('CGYRO_schemes', {})
    rows = []
    for scheme, group in groups.items():
        report = group['particle_record']
        for key in sorted(group['inputs'], key=lambda name: int(str(name).rsplit('_', 1)[1])):
            nr = int(str(key).rsplit('_', 1)[1])
            rows.append(dict(key=scheme + ':' + key, nr=nr,
                             rho=report['local_inputs'][key]['rho'], scheme=scheme,
                             scheme_label=group['label'], batch_key=scheme + ':' + str(nr),
                             particle_record=report, particle_key=key,
                             path=('Transfer_tool', 'OUTPUTS', 'CGYRO_schemes', scheme, 'inputs', key)))
    return rows
