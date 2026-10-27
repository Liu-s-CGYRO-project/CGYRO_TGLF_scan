"""Partial input catalogs, offline help, and selected-field scan execution."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from omfit_mapping import OMFITMapping, treeify
from test_project import UI

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
from OMFITlib_tglf_parameters import parameter_catalog, parameter_values
from OMFITlib_tglf_parameter_help import parameter_help
from OMFITlib_tglf_workbench import initialize, parameter_overrides, parameter_value, plan
from OMFITlib_tglf_workbench_ui import TGLFWorkbench


class UnreadResults(dict):
    def __getitem__(self, key):
        raise AssertionError('Parameter UI must not resolve results')

    def items(self):
        raise AssertionError('Parameter UI must not enumerate results')

    def values(self):
        raise AssertionError('Parameter UI must not enumerate results')

    def __iter__(self):
        raise AssertionError('Parameter UI must not enumerate results')


class TGLFParametersTest(unittest.TestCase):
    def setUp(self):
        self.source = dict(NS=2, RLTS_1=4., ZS_1=-1., ZS_2=1.)
        self.root = dict(SETTINGS={'WORKBENCH': {}}, TGLF_scan={
            'TGLF': {'FILES': {'input.tglf': self.source}, 'SETTINGS': {'REMOTE_SETUP': {}}, 'SCRIPTS': {}}})
        self.settings, _ = initialize(self.root)
        self.settings.update(dict(source='current', mode='1d', parameter1='BETAE',
                                  value_mode1='list', values1=[0., .01]))

    def workbench(self):
        ui = UI(self.root)
        view = SimpleNamespace(root=self.root, actions=SimpleNamespace(factory=dict), ui=ui,
                               prefix="root['SETTINGS']['WORKBENCH']", label=Mock(), cgyro_checkbox=Mock())
        return TGLFWorkbench(view), ui

    def execute(self, prepared):
        captured = []
        def batch(**kwargs):
            captured.extend(copy.deepcopy(kwargs['inputTGLF']))
            for key in kwargs['runIDs']:
                kwargs['results'][key] = {'gbflux': {'data': np.array(
                    [('elec', 1., 2., 3.)], dtype=[('species', 'U12'), ('Gam/Gam_GB', float),
                                                  ('Q/Q_GB', float), ('Pi/Pi_GB', float)])}}
        self.root['TGLF_scan']['TGLF']['SCRIPTS']['runTGLFbatch'] = SimpleNamespace(run=batch)
        script = REPO / 'CGYRO_TGLF_scan/TGLF_scan/SCRIPTS/run_workbench.py'
        namespace = dict(root=self.root['TGLF_scan'], project_root=self.root, plan=prepared,
                         defaultVars=lambda **kwargs: None, OMFITtree=dict, print=lambda *a: None)
        exec(compile(script.read_text(encoding='utf-8'), str(script), 'exec'), namespace)
        return captured

    def test_omitted_fields_available_and_current_values_win(self):
        self.source.update(dict(BETAE=.025, SAT_RULE=3, FUTURE_FIELD=2.5, USE_BPER=np.bool_(True)))
        before = copy.deepcopy(self.source)
        values = parameter_values(self.source)
        for name in ('XNUE', 'VEXB_SHEAR', 'RLNS_2', 'TAUS_2', 'Q_LOC', 'SHAPE_S_COS6', 'FT_MODEL_SA'):
            self.assertIn(name, values)
        self.assertEqual(values['BETAE'], .025)
        self.assertEqual(values['FUTURE_FIELD'], 2.5)
        self.assertIs(values['USE_BPER'], True)
        self.assertEqual(self.source, before)

    def test_catalog_excludes_managed_non_scalars_and_inactive_species(self):
        self.source.update(dict(RLTS_3=9., rho=.4, __metadata=4, array=np.array([1., 2.]),
                                UNITS='CGYRO', USE_TRANSPORT_MODEL=True))
        values = parameter_values(self.source)
        for name in ('NS', 'USE_TRANSPORT_MODEL', 'rho', '__metadata', 'array', 'RLTS_3', 'UNITS'):
            self.assertNotIn(name, values)
        self.source['NS'] = 3
        self.assertEqual(parameter_values(self.source)['RLTS_3'], 9.)

    def test_newer_explicit_species_not_silently_dropped(self):
        self.source.update(dict(NS=8, RLTS_8=7.5))
        values = parameter_values(self.source)
        self.assertEqual(values['RLTS_8'], 7.5)
        self.assertNotIn('RLNS_8', values)  # Native catalog only verifies species 1..7.

    def test_one_dimensional_scan_materializes_only_the_selected_default(self):
        before = copy.deepcopy(self.source)
        prepared = plan(self.root, self.settings)
        self.assertEqual(prepared['sources'][0]['parameters'], {'BETAE': 0.})
        inputs = self.execute(prepared)
        self.assertEqual([row['BETAE'] for row in inputs], [0., .01])
        for row in inputs:
            self.assertNotIn('NKY', row)
            self.assertNotIn('Q_LOC', row)
        self.assertEqual(self.source, before)
        record = self.root['TGLF_scan']['RUN_DB'][self.settings['result_run']]
        self.assertEqual(record['status'], 'complete')
        self.assertEqual(len(record['points']), 2)

    def test_two_dimensional_integer_and_boolean_scan(self):
        self.settings.update(dict(mode='2d', parameter1='B_MODEL_SA', values1=[0, 1],
                                  parameter2='USE_BPAR', value_mode2='list', values2=[False, True]))
        inputs = self.execute(plan(self.root, self.settings))
        self.assertEqual([(row['B_MODEL_SA'], row['USE_BPAR']) for row in inputs],
                         [(0, False), (0, True), (1, False), (1, True)])
        self.assertTrue(all(type(row['B_MODEL_SA']) is int and type(row['USE_BPAR']) is bool for row in inputs))

    def test_uq_seeds_omitted_field_but_not_all_defaults(self):
        self.settings.update(dict(mode='uq', uq_count=1, samples=2, uq={'0': {'name': 'XNUE', 'mean': .1, 'std': .02}}))
        prepared = plan(self.root, self.settings)
        self.assertEqual(prepared['sources'][0]['parameters'], {'XNUE': 0.})
        fake_cp = SimpleNamespace(Normal=Mock(), J=lambda *a: SimpleNamespace(sample=lambda *a: [[.08, .12]]))
        with patch.dict(sys.modules, {'chaospy': fake_cp}):
            inputs = self.execute(prepared)
        self.assertEqual([row['XNUE'] for row in inputs], [.08, .12])
        self.assertTrue(all('NKY' not in row for row in inputs))

    def test_relative_scan_keeps_each_radius_baseline(self):
        self.root['TGLF_scan']['input.tglf'] = {.3: dict(self.source, RLTS_1=4.), .5: dict(self.source, RLTS_1=6.)}
        self.settings.update(dict(source='radial', radius_mode='all', parameter1='RLTS_1',
                                  value_mode1='factor', scan_start1=.5, scan_end1=1.5, scan_count1=3))
        prepared = plan(self.root, self.settings)
        self.assertEqual([source['axes'][0]['values'] for source in prepared['sources']], [[2., 4., 6.], [3., 6., 9.]])
        self.assertTrue(all(not source['parameters'] for source in prepared['sources']))

    def test_scan_values_override_manual_value_without_overwriting_input(self):
        self.settings['parameters']['BETAE'] = dict(enabled=True, value=.02)
        inputs = self.execute(plan(self.root, self.settings))
        self.assertEqual([row['BETAE'] for row in inputs], [0., .01])
        self.assertNotIn('BETAE', self.source)

    def test_single_run_does_not_apply_displayed_defaults(self):
        self.settings['mode'] = 'single'
        workbench, _ = self.workbench()
        self.settings['parameter_group'] = 'all'
        workbench.parameters()
        self.assertFalse(parameter_overrides(self.settings, self.source))
        inputs = self.execute(plan(self.root, self.settings))
        self.assertEqual(inputs, [dict(self.source, USE_TRANSPORT_MODEL=True)])

    def test_invalid_integer_nonfinite_and_inactive_species_rejected(self):
        for name, value, reference in [('B_MODEL_SA', 1.5, 1), ('FT_MODEL_SA', .5, 1),
                                       ('BETAE', float('nan'), 0.), ('USE_BPAR', 2, False)]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                parameter_value(name, value, reference)
        for name in ('RLTS_3', 'NS', 'USE_TRANSPORT_MODEL', 'MADE_UP'):
            self.settings['parameter1'] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                plan(self.root, self.settings)

    def test_default_zero_factor_scan_requires_explicit_values(self):
        self.settings['value_mode1'] = 'factor'
        with self.assertRaisesRegex(ValueError, '原值为 0'):
            plan(self.root, self.settings)

    def test_saved_settings_reopen_and_native_mapping(self):
        self.settings['parameters']['XNUE'] = dict(enabled=True, value=.08)
        reopened = treeify(json.loads(json.dumps(self.root)), OMFITMapping)
        settings, _ = initialize(reopened, OMFITMapping)
        prepared = plan(reopened, settings)
        self.assertEqual(prepared['sources'][0]['parameters'], {'XNUE': .08, 'BETAE': 0.})
        self.assertEqual(prepared['axes'][0]['values'], [0., .01])

    def test_help_contains_meaning_normalization_conditions_and_source(self):
        for name in parameter_catalog(dict(NS=7)):
            with self.subTest(name=name):
                text = parameter_help(name)
                self.assertIn('含义：', text)
                self.assertIn('单位 / 归一化：', text)
                self.assertIn('适用条件：', text)
                self.assertIn('https://gacode.io/tglf/', text)
                self.assertNotIn('本目录未核对', text)
        self.assertIn('−a·d(ln T_s)/dr', parameter_help('RLTS_2'))
        self.assertIn('高 ky', parameter_help('NKY'))
        self.assertIn('已标为弃用', parameter_help('VPAR_SHEAR_MODEL'))

    def test_help_distinguishes_current_default_and_unknown(self):
        self.assertIn('当前输入值：3', parameter_help('SAT_RULE', {'SAT_RULE': 3}))
        self.assertIn('官方解析器默认参考值：0', parameter_help('SAT_RULE', {}))
        self.assertIn('归一化约定', parameter_help('UNITS', {'UNITS': 'CGYRO'}))
        self.assertIn('当前输入值：0.0', parameter_help('BETAE', {'BETAE': 0.}))
        self.assertIn('未核对', parameter_help('FUTURE_FIELD', {'FUTURE_FIELD': 5.}))

    def test_scan_dropdowns_and_parameter_page_do_not_read_outputs(self):
        self.root['TGLF_scan']['RUN_DB'] = UnreadResults(old=UnreadResults())
        workbench, ui = self.workbench()
        before = copy.deepcopy(self.source)
        workbench.scan_settings()
        axis = next(event for event in ui.events if event[0] == 'ComboBox' and event[1][0].endswith("['parameter1']"))
        self.assertIn('BETAE', axis[1][1])
        self.assertIn('RLTS_2', axis[1][1])
        self.assertIn('电子 beta', axis[2]['help'])
        self.settings['parameter_group'] = 'field'
        ui.events.clear()
        workbench.parameters()
        fields = [event for event in ui.events if event[0] in ('Entry', 'ComboBox') and "['parameters']" in event[1][0]]
        self.assertTrue(any("['XNUE']" in event[1][0] for event in fields))
        self.assertFalse(any("['Q_LOC']" in event[1][0] for event in fields))
        self.assertTrue(all(event[2]['updateGUI'] is False for event in fields))
        self.assertTrue(all('适用条件：' in event[2]['help'] for event in fields))
        self.assertEqual(self.source, before)

    def test_common_enum_choices_and_callback_apply_only_edited_parameter(self):
        workbench, ui = self.workbench()
        for name in ('SAT_RULE', 'KYGRID_MODEL'):
            workbench.parameter_field(name, self.source, name)
        sat, grid = [event for event in ui.events if event[0] == 'ComboBox']
        self.assertEqual(sat[1][1], [0, 1, 2, 3])
        self.assertEqual(grid[1][1], [0, 1, 2, 3, 4, 5])
        self.settings['parameters']['SAT_RULE']['value'] = 3
        sat[2]['postcommand']()
        self.assertEqual(parameter_overrides(self.settings, self.source), {'SAT_RULE': 3})
        self.assertNotIn('SAT_RULE', self.source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
