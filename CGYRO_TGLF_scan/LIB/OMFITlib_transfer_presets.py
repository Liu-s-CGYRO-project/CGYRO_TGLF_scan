"""Saved Transfer scheme identifiers and captions shared with the solver workbenches."""
from builtins import all, dict, enumerate, int, list, range
from collections import OrderedDict


JET_FUEL_MODE = 'jet96482_fast_fuel'
JET_FUEL_LABEL = '快氢同位素并入主离子＋等效热杂质'
JET_FUEL_RULE = 'jet96482_local_card_v1'

SCHEMES = OrderedDict([
    ('all', ('保留所有粒子', dict(particle_mode='all'))),
    ('thermalize', ('慢化快离子（热化处理）', dict(particle_mode='thermalize'))),
    ('equivalent_pressure', ('等效杂质 · 保留原总压力',
                             dict(particle_mode='equivalent', equivalent_temperature='pressure'))),
    ('equivalent_main_ion', ('等效杂质 · 温度随热主离子',
                             dict(particle_mode='equivalent', equivalent_temperature='main_ion'))),
    ('separate_fast', ('主离子 / 等效杂质 / 等效快粒子', dict(particle_mode='separate_fast'))),
    (JET_FUEL_MODE, (JET_FUEL_LABEL, dict(particle_mode=JET_FUEL_MODE))),
    ('main_only', ('仅保留主离子和 Zeff', dict(particle_mode='main_only'))),
])


def tglf_thermal_ions(report, local):
    """TGLF numbers the electron first. Use the final groups for each radius."""
    if 'thermal_ions' in local:
        return list(local['thermal_ions'])
    equivalent = local.get('equivalent', {})
    if equivalent.get('rule', '') == JET_FUEL_RULE:
        return [2, 3]
    if 'groups' in equivalent:
        groups = equivalent['groups']
        return [groups[key]['solver_index'] for key in ('main', 'impurity')
                if groups.get(key, {}).get('solver_index', None) is not None]
    if 'sources' in equivalent:
        main_count = int(report['main_count'])
        indices = list(range(2, 2 + main_count))
        if equivalent.get('parameters', None) and all(ion['kind'] == 'therm' for ion in equivalent['sources']):
            indices.append(2 + main_count)
        return indices
    return [i for i, ion in enumerate(report.get('after', []), 2) if ion.get('kind', '') == 'therm']
