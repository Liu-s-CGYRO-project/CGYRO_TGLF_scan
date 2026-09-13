"""Multi-profile workflow regression with real files, plots and simulated solver boundaries."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

import numpy as np
import matplotlib.pyplot as plt
from test_compare import FakeUI, Notebook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'))
import OMFITlib_tglf_multi_data as data
import OMFITlib_tglf_multi_run as execution
from OMFITlib_tglf_multi_ui import MultiInputUI
from OMFITlib_tglf_multi_plot import plot_cases


def profile():
    return {'rho': np.array([0., .2, .6, 1.]), 'rmin': np.array([0., .1, .5, 1.]),
            'ne': np.ones(4), 'Te': np.ones(4), 'q': np.ones(4),
            'IONS': {1: ['D', 1., 2., 'thermal'], 2: ['C', 6., 12., 'fast']},
            'ni_1': np.ones(4), 'Ti_1': np.ones(4), 'ni_2': np.ones(4), 'Ti_2': np.ones(4)}


def result():
    return {'eigenvalue_spectrum': {'ky': np.array([.1, .3, .6]),
                                   'gamma': np.array([[.2, .3, .4], [.1, .2, .3]]),
                                   'freq': np.array([[.1, .2, .3], [-.1, -.2, -.3]])},
            'gbflux': {'data': [('elec', 1., 2., 3., 4.), ('ion1', .5, .6, .7, .8)]}}


class TestMultiInput(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = {'SETTINGS': {}, 'TGLF_scan': {name: {'SETTINGS': {'REMOTE_SETUP': {}}} for name in ('TGYRO', 'TGLF')},
                     'SCRIPTS': {name: Mock() for name in ('import_tglf_multi', 'run_tglf_multi')},
                     'PLOTS': {'TGLF_multi': Mock()}}
        self.settings, self.cases = data.initialize(self.root)
        self.path = self.base / 'case A' / 'input.gacode'
        self.path.parent.mkdir()
        self.path.write_text('synthetic profiles fixture')
        self.case_id = data.import_files(self.root, [self.path], lambda *a, **k: profile())[0][0]
        self.case = self.cases[self.case_id]
        self.calls = []
        self.fail_tglf = False

        def fake_execute(module, **kwargs):
            self.calls.append(kwargs)
            local = Path(kwargs['workdir'])
            if '/prepare' in local.as_posix():
                for _, name in kwargs['inputs']:
                    if name.endswith('/input.tglf'):
                        target = local / Path(name).parent / 'out.tglf.localdump'
                        target.parent.mkdir()
                        target.write_text('fixture localdump')
            elif self.fail_tglf:
                raise RuntimeError('synthetic solver failure')
            return 0

        def read_dump(*args, **kwargs):
            return dict(NS=3, RMIN_LOC=.3, Q_LOC=2., RLTS_1=4., USE_TRANSPORT_MODEL=True,
                        SAT_RULE=0, NKY=12, NMODES=2, USE_BPER=False, USE_BPAR=False)

        self.runner = execution.OMFITRunner(self.root, Mock(executable=fake_execute), read_dump,
                                            lambda name, fromString: fromString, lambda path: result(),
                                            lambda *a: str(self.base / 'work'), {}, dict)
        self.addCleanup(plt.close, 'all')

    def run_cases(self, action='all'):
        return execution.run_selected(self.root, self.runner, action)

    def latest(self):
        return self.case['runs'][self.case['selected_run']]

    def test_gui_run_requires_generation_and_invalidates_changed_plan(self):
        def run_button_state():
            ui = FakeUI(self.root)
            MultiInputUI(self.root, ui).render()
            return next(kwargs['state'] for _, kind, args, kwargs in ui.events
                        if kind == 'Button' and args[0] == '运行已生成输入 / 重试失败项')
        self.assertEqual(run_button_state(), 'disabled')
        self.run_cases('prepare')
        self.assertEqual(run_button_state(), 'normal')
        self.settings['radii'] = '.6'
        self.assertEqual(run_button_state(), 'disabled')

    def test_gui_no_selected_case_disables_run_and_plot(self):
        self.case['enabled'] = False
        ui = FakeUI(self.root)
        MultiInputUI(self.root, ui).render()
        for label in ('生成输入', '生成并运行', '对比所选记录的频率与增长率'):
            options = next(kwargs for _, kind, args, kwargs in ui.events if kind == 'Button' and args[0] == label)
            self.assertEqual(options['state'], 'disabled')

    def test_import_same_basename_in_two_directories_and_isolated_snapshot(self):
        original = profile()
        other = self.base / 'case B' / 'input.gacode'
        other.parent.mkdir()
        other.write_text('second synthetic input')
        added, errors = data.import_files(self.root, [self.path, self.path, other], lambda *a, **k: original)
        original['ne'][:] = 99
        self.assertEqual(len(added), 2)
        self.assertEqual([self.cases[key]['label'] for key in added], ['case A', 'case B'])
        self.assertFalse(errors)
        np.testing.assert_allclose(self.cases[added[0]]['input.gacode']['ne'], 1)
        self.assertEqual(self.path.read_text(), 'synthetic profiles fixture')

    def test_import_partial_failures_leave_valid_cases(self):
        added, errors = data.import_files(self.root, [self.path, self.base / 'missing'], lambda *a, **k: profile())
        self.assertEqual((len(added), len(errors)), (1, 1))

    def test_invalid_profile_fails_at_import(self):
        bad = profile()
        bad['rho'][2] = np.nan
        added, errors = data.import_files(self.root, [self.path], lambda *a, **k: bad)
        self.assertFalse(added)
        self.assertIn('rho', errors[0])

    def test_radius_validation_and_coordinate_are_explicit(self):
        for value in ('0', '1', 'nan', '.5, .5', '.3 no', ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                data.parse_radii(value)
        self.assertEqual(data.parse_radii('.7, .3 .5'), [.3, .5, .7])
        plan = data.case_plan(self.settings, self.case)
        text, grid = data.tgyro_input(profile(), plan)
        self.assertEqual(grid, [.25, .5])
        self.assertIn('TGYRO_USE_RHO=1', text)
        self.settings['coordinate'] = 'r/a'
        text, _ = data.tgyro_input(profile(), data.case_plan(self.settings, self.case))
        self.assertIn('TGYRO_USE_RHO=0', text)

    def test_auxiliary_radius_is_inside_truncated_profile(self):
        self.assertEqual(data.dump_grid([.5], [.4, .9]), [.45, .5])
        self.assertEqual(data.dump_grid([.4], [.4, .9]), [.4, .65])

    def test_overrides_do_not_execute_code_or_accept_nonfinite(self):
        for text in ('x=1', 'SAT_RULE=__import__("os")', 'NKY=nan', 'NS=3', 'A=1; A=2', 'NKY=[]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                data.parse_overrides(text)
        self.assertEqual(data.parse_overrides('NKY=24; USE_BPER=.true.\nKY=1d-1'),
                         {'NKY': 24, 'USE_BPER': True, 'KY': .1})

    def test_case_override_wins_and_copies_do_not_copy_results(self):
        self.settings['extra'] = 'NKY=18'
        self.case['extra'] = 'NKY=24; SAT_RULE=2'
        self.run_cases()
        copy_id = data.duplicate_case(self.root, self.case_id)
        self.assertFalse(self.cases[copy_id]['runs'])
        self.cases[copy_id]['extra'] = 'NKY=16'
        self.assertEqual(self.latest()['plan']['parameters']['NKY'], 24)

    def test_prepare_does_not_run_tglf_or_overwrite_active_data(self):
        self.root['TGLF_scan']['input.tglf'] = {'sentinel': 1}
        self.root['TGLF_scan']['TGLF']['FILES'] = {'previous': 2}
        self.run_cases('prepare')
        run = self.latest()
        self.assertEqual(run['status'], 'ready')
        self.assertEqual(len(run['points']), 1)
        self.assertEqual(len(self.calls), 1)
        self.assertIn('tgyro -t . -n 2', self.calls[0]['script'][0])
        self.assertEqual(self.root['TGLF_scan']['input.tglf'], {'sentinel': 1})
        self.assertEqual(self.root['TGLF_scan']['TGLF']['FILES'], {'previous': 2})
        self.assertTrue(all(call['clean'] is False for call in self.calls))

    def test_generation_preserves_dump_before_model_overrides(self):
        self.case['extra'] = 'SAT_RULE=2'
        self.run_cases('prepare')
        point = self.latest()['points']['r000']
        self.assertEqual(point['localdump']['SAT_RULE'], 0)
        self.assertEqual(point['input.tglf']['SAT_RULE'], 2)
        self.assertEqual(point['input.tglf']['RLTS_1'], 4.)

    def test_every_rerun_gets_new_directories_and_records(self):
        self.run_cases()
        first = self.latest()['id']
        self.run_cases()
        self.assertNotEqual(first, self.latest()['id'])
        self.assertEqual(len(self.case['runs']), 2)
        paths = [call['workdir'] for call in self.calls]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(self.case['runs'][first]['status'], 'complete')

    def test_failure_retry_retains_logs_and_completed_points(self):
        self.settings['radii'] = '.3, .6'
        self.run_cases('prepare')
        self.fail_tglf = True
        self.run_cases('run')
        self.assertEqual(self.latest()['status'], 'partial')
        self.fail_tglf = False
        self.run_cases('run')
        self.assertEqual(self.latest()['status'], 'complete')
        for point in self.latest()['points'].values():
            self.assertEqual(len(point['attempts']), 2)
            self.assertEqual([a['status'] for a in point['attempts'].values()], ['failed', 'complete'])
        before = len(self.calls)
        self.run_cases('run')
        self.assertEqual(len(self.calls), before)

    def test_changed_settings_require_new_generated_inputs(self):
        self.run_cases('prepare')
        self.settings['SAT_RULE'] = 2
        with self.assertRaisesRegex(ValueError, '设置已变化'):
            self.run_cases('run')
        self.assertEqual(len(self.calls), 1)

    def test_changed_profile_requires_regeneration_and_command_edits_are_used(self):
        self.run_cases('prepare')
        self.case['input.gacode']['Te'][1] = 2.
        with self.assertRaisesRegex(ValueError, '剖面已变化'):
            self.run_cases('run')
        self.case['input.gacode']['Te'][1] = 1.
        self.settings['tglf_command'] = '/custom/bin/tglf -e .'
        self.run_cases('run')
        self.assertIn('/custom/bin/tglf -e .', self.calls[-1]['script'][0])

    def test_all_cases_preflight_before_external_execution(self):
        key = data.duplicate_case(self.root, self.case_id)
        self.cases[key]['radii'] = 'nan'
        with self.assertRaises(ValueError):
            self.run_cases()
        self.assertFalse(self.calls)

    def test_one_case_failure_does_not_stop_other_cases(self):
        data.duplicate_case(self.root, self.case_id)
        prepare = self.runner.prepare
        def first_fails(case, run):
            if case is self.case:
                raise ValueError('bad first profile')
            prepare(case, run)
        self.runner.prepare = first_fails
        outcome = self.run_cases()
        self.assertEqual(outcome, {'cases': 2, 'failed': 1})
        self.assertEqual(self.latest()['status'], 'prepare_failed')
        self.assertEqual(list(self.cases.values())[1]['runs'].popitem()[1]['status'], 'complete')

    def test_stop_on_error_is_respected(self):
        self.settings['continue_on_error'] = False
        self.fail_tglf = True
        with self.assertRaisesRegex(RuntimeError, 'synthetic'):
            self.run_cases()
        self.assertEqual(self.latest()['status'], 'partial')

    def test_missing_or_invalid_result_is_not_success(self):
        for broken in ({}, {'eigenvalue_spectrum': {}}):
            with self.assertRaises(ValueError):
                execution.validate_result(broken)
        broken = result()
        broken['eigenvalue_spectrum']['gamma'][0, 0] = np.nan
        with self.assertRaises(ValueError):
            execution.validate_result(broken)

    def test_missing_localdump_and_unknown_model_option_fail_generation(self):
        self.runner.ui = Mock(executable=lambda *a, **k: 0)
        self.run_cases('prepare')
        self.assertEqual(self.latest()['status'], 'prepare_failed')
        self.assertIn('未生成', self.latest()['error'])

    def test_keyboard_interrupt_records_cancelled_attempt(self):
        self.run_cases('prepare')
        def cancel(*args, **kwargs):
            raise KeyboardInterrupt()
        self.runner.ui = Mock(executable=cancel)
        with self.assertRaises(KeyboardInterrupt):
            self.run_cases('run')
        point = self.latest()['points']['r000']
        self.assertEqual(point['status'], 'cancelled')
        self.assertEqual(point['attempts'][point['selected_attempt']]['status'], 'cancelled')

    def test_remote_endpoints_use_unique_children_and_fail_unconfigured(self):
        self.settings['execution'] = 'module'
        class Servers:
            def __getitem__(self, module):
                return {'server': 'test-host', 'tunnel': 'test-tunnel'}
        self.runner.servers = Servers()
        module = self.root['TGLF_scan']['TGLF']
        module['SETTINGS']['REMOTE_SETUP']['workDir'] = '/scratch/user/omfit'
        local, remote, server, tunnel = self.runner.endpoint(module, self.settings, 'TGLF/run_one')
        self.assertEqual(remote, '/scratch/user/omfit/tglf_multi/TGLF/run_one/')
        self.assertEqual((server, tunnel), ('test-host', 'test-tunnel'))
        module['SETTINGS']['REMOTE_SETUP']['workDir'] = '../relative'
        with self.assertRaises(ValueError):
            self.runner.endpoint(module, self.settings, 'TGLF/run_one')

    def test_save_trees_register_page_scripts_and_empty_cases(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'OMFITtemplates/LIB'))
        from OMFITlib_template_archive import parse_tree
        repo = Path(__file__).resolve().parents[1]
        for filename, prefix in ((repo / 'OMFITsave.txt', ('CGYRO_TGLF_scan',)),
                                 (repo / 'CGYRO_TGLF_scan/OMFITsave.txt', ())):
            rows = {row.keys: row for row in parse_tree(filename.read_bytes())}
            for key in (('GUIS', 'TGLF_multi'), ('SCRIPTS', 'run_tglf_multi'), ('LIB', 'OMFITlib_tglf_multi_run')):
                self.assertTrue((filename.parent / rows[prefix + key].ref).is_file())
            self.assertEqual(rows[prefix + ('TGLF_CASES',)].kind, 'OMFITtree')

    def test_gui_can_render_empty_project_and_complete_history(self):
        ui = FakeUI(self.root)
        MultiInputUI(self.root, ui).render()
        labels = [args[0] for _, widget, args, _ in ui.events if widget == 'Button']
        self.assertIn('导入多个 input.gacode', labels)
        self.assertIn('生成并运行', labels)
        self.run_cases()
        MultiInputUI(self.root, ui).render()
        original = self.root['TGLF_CASES']
        self.root['TGLF_CASES'] = {}
        MultiInputUI(self.root, FakeUI(self.root)).render()
        self.root['TGLF_CASES'] = original

    def test_plot_uses_native_grid_and_selected_run(self):
        self.run_cases()
        fig = plot_cases(self.root, Notebook)
        fig.canvas.draw()
        np.testing.assert_array_equal(fig.axes[0].lines[0].get_xdata(), [.1, .3, .6])
        self.case['enabled'] = False
        with self.assertRaises(ValueError):
            plot_cases(self.root, Notebook)


if __name__ == '__main__':
    unittest.main()
