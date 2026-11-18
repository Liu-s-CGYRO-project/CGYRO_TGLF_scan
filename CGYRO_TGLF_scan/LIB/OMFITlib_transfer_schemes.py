"""Frozen per-scheme input cards for CGYRO and TGLF.

Generation is an explicit action. Selectors read only the saved radius/option
metadata; they never regenerate inputs or inspect solver output files.
"""
from builtins import ValueError, dict, hasattr, int, list, sorted, str
import copy
from OMFITlib_project_inputs import input_digest, validate_input
from OMFITlib_transfer_presets import SCHEMES
from OMFITlib_transfer_workflow import generation_issues, selected_profile


def scheme_runid(base, scheme):
    """Use the existing result-name namespace, without changing result identity."""
    return str(base) + '__transfer_' + scheme if scheme else str(base)


def _duplicate(value):
    return value.duplicate() if hasattr(value, 'duplicate') else copy.deepcopy(value)


def _freeze(outputs, options, label, factory):
    generated = outputs.get('Profiles_gen', {})
    report = outputs.get('Particle_processing', {})
    cards = {'cgyro': factory(), 'tglf': factory()}
    local = {}
    for key in generated.keys():
        stem, sep, index = str(key).rpartition('_')
        if not sep or not index.isdigit() or stem not in ('input.cgyro', 'input.tglf'):
            continue
        kind = stem.split('.')[1]
        source = generated[key]
        validate_input(source, kind)
        metadata = report.get('local_inputs', {}).get(key, {})
        if metadata.get('rho', None) is None:
            raise ValueError(label + ' / ' + key + ' 缺少半径记录。')
        cards[kind][key] = _duplicate(source)
        local[key] = {name: copy.deepcopy(metadata[name])
                      for name in ('rho', 'main_count', 'rhostar', 'equivalent', 'locpargen_qn', 'thermal_ions',
                                   'prescribed_zeff', 'final_neutrality') if name in metadata}
    if not cards['cgyro'] or not cards['tglf']:
        raise ValueError(label + ' 没有生成完整的 CGYRO 和 TGLF 半径输入。')
    radii = {kind: {name.rsplit('_', 1)[1]: local[name]['rho'] for name in files}
             for kind, files in cards.items()}
    if radii['cgyro'] != radii['tglf']:
        raise ValueError(label + ' 的 CGYRO 和 TGLF 半径输入不配对。')
    frozen = factory()
    # File-bearing containers must be OMFITtree in a real session so project
    # save/update follows the file references instead of pickling the readers.
    frozen.update(dict(label=label, options=dict(options), inputs=cards['cgyro'], tglf_inputs=cards['tglf'],
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
