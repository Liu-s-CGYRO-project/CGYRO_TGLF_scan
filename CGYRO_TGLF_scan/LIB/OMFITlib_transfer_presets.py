"""Saved Transfer scheme identifiers and captions shared with the solver workbenches."""
from builtins import dict
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
