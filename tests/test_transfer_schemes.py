"""Conversion batches and cross-run selection keep inputs/results isolated."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from omfit_mapping import OMFITMapping
import test_project as project_tests
import test_compare as compare_tests
import OMFITlib_transfer_schemes as schemes
from OMFITlib_tglf_workbench import initialize as initialize_tglf
from OMFITlib_tglf_workbench_ui import TGLFWorkbench
from OMFITlib_compare_state import activate_source, selected_cgyro_runs, selection_check
from OMFITlib_compare_cases import CaseSelection
from OMFITlib_project_ui import ProjectUI


class Untouched:
    def __deepcopy__(self, memo):
        raise AssertionError('Copied unrelated results')
    def keys(self):
        raise AssertionError('Read unrelated results')
    def items(self):
        raise AssertionError('Read unrelated results')
    def get(self, *args):
        raise AssertionError('Read unrelated results')


class SchemeTests(unittest.TestCase):
    def setUp(self):
        host = project_tests.ProjectTest(methodName='runTest')
        host.setUp()
        host.send()
        host.configure()
        self.host, self.root, self.actions = host, host.root, host.actions
        self.node = host.transfer
        self.node['INPUTS']['input.gacode'] = {'raw_profile': 7}
        self.node['SETTINGS']['PHYSICS']['start_from'] = 'input.gacode'
        self.options = dict(minimum=.2, maximum=.8, points=2, coordinate='rho', particle_mode='all')

    def generate(self, source, options, label):
        self.assertEqual(self.node['INPUTS']['input.gacode'], {'raw_profile': 7})
        self.node['INPUTS']['input.gacode']['raw_profile'] = 9
        self.node['SETTINGS']['SETUP']['num_nodes'] = 999
        q = 2. if options['particle_mode'] == 'all' else 3.
        self.node['OUTPUTS'].update(dict(Profiles_gen={'input.cgyro_1': project_tests.cgyro(),
                    'input.tglf_1': dict(NS=6 if q == 2. else 3, ZS_1=-1, BETAE=q/100)},
            Particle_processing=dict(options=options, main_count=1, plot_profile=Untouched(),
                local_inputs={'input.cgyro_1': dict(rho=.33, main_count=1, rhostar=.002, locpargen_qn=True),
                              'input.tglf_1': dict(rho=.33, main_count=1, locpargen_qn=True)})))
        self.node['OUTPUTS']['Profiles_gen']['input.cgyro_1']['Q'] = q

    def prepare(self, factory=dict):
        with patch.object(schemes, 'generation_issues', return_value=[]):
            schemes.generate_schemes(self.node, dict(all=True, separate_fast=True),
                                     self.options, self.generate, factory)
        self.actions.settings['cgyro_source_mode'] = 'schemes'
        return self.node['OUTPUTS']['CGYRO_schemes']

    def test_generation_keeps_only_cards_and_small_provenance_and_restores_working_state(self):
        previous = self.node['OUTPUTS']
        previous['normal_results'] = Untouched()
        setup = copy.deepcopy(self.node['SETTINGS']['SETUP'])
        original = self.node['INPUTS']
        frozen = self.prepare(OMFITMapping)
        self.assertEqual(list(frozen), ['all', 'separate_fast'])
        self.assertIsInstance(frozen['all'], OMFITMapping)
        self.assertIsInstance(frozen['all']['inputs'], OMFITMapping)
        self.assertIsInstance(frozen['all']['tglf_inputs'], OMFITMapping)
        self.assertEqual(frozen['all']['tglf_inputs']['input.tglf_1']['NS'], 6)
        self.assertNotIn('KY', frozen['all']['tglf_inputs']['input.tglf_1'])
        self.assertIs(self.node['OUTPUTS'], previous)
        self.assertIs(self.node['INPUTS'], original)
        self.assertEqual(original['input.gacode'], {'raw_profile': 7})
        self.assertEqual(self.node['SETTINGS']['SETUP'], setup)
        self.assertNotIn('plot_profile', frozen['all']['particle_record'])
        self.assertEqual(frozen['all']['source_digest'], frozen['separate_fast']['source_digest'])
        for group in frozen.values():
            for record in group['particle_record']['local_inputs'].values():
                self.assertTrue(record['locpargen_qn'])
        self.assertEqual(frozen['separate_fast']['inputs']['input.cgyro_1']['Q'], 3.)

    def test_failure_or_interrupt_leaves_previous_set_and_results(self):
        previous = self.prepare()
        outputs = self.node['OUTPUTS']
        for error in (RuntimeError('failed generation'), KeyboardInterrupt()):
            def fail(source, options, label):
                self.generate(source, options, label)
                if options['particle_mode'] == 'separate_fast':
                    raise error
            with patch.object(schemes, 'generation_issues', return_value=[]):
                with self.assertRaises(type(error)):
                    schemes.generate_schemes(self.node, dict(all=True, separate_fast=True), self.options, fail)
            self.assertIs(self.node['OUTPUTS'], outputs)
            self.assertIs(outputs['CGYRO_schemes'], previous)
            self.assertEqual(self.node['INPUTS']['input.gacode'], {'raw_profile': 7})

    def test_empty_selection_does_not_generate(self):
        with self.assertRaisesRegex(ValueError, '勾选'):
            schemes.generate_schemes(self.node, {}, self.options, lambda *a: self.fail('generated'))

    def test_missing_or_mismatched_tglf_radius_preserves_both_previous_input_sets(self):
        previous = self.prepare()
        for missing in (True, False):
            def incomplete(*args):
                self.generate(*args)
                outputs = self.node['OUTPUTS']
                if missing:
                    del outputs['Profiles_gen']['input.tglf_1']
                else:
                    outputs['Particle_processing']['local_inputs']['input.tglf_1']['rho'] = .5
            with patch.object(schemes, 'generation_issues', return_value=[]), self.assertRaises(ValueError):
                schemes.generate_schemes(self.node, dict(all=True), self.options, incomplete)
            self.assertIs(self.node['OUTPUTS']['CGYRO_schemes'], previous)

    def test_tglf_scheme_picker_and_action_use_frozen_cards_without_live_generation_settings(self):
        self.prepare()
        self.host.configure('tglf')
        self.node['SETTINGS']['PHYSICS']['generation'] = {'particle_mode': 'new-draft'}
        ui = project_tests.UI(self.root)
        view = ProjectUI(self.actions, ui)
        for scheme in ('all', 'separate_fast'):
            self.actions.select_tglf_transfer(scheme)
            workbench = TGLFWorkbench(view)
            workbench.input()
            choices = next(args[1] for name, args, _ in ui.events if name == 'ComboBox' and args[2] == '处理方案')
            self.assertEqual(set(choices.values()), {'all', 'separate_fast'})
            self.assertEqual([row['scheme'] for row in workbench.selected], [scheme])
            self.actions.run_tglf_plan()
            sent = self.root['TGLF_scan']['SCRIPTS']['run_workbench'].run.call_args.kwargs['plan']['sources']
            self.assertEqual([row['path'] for row in sent],
                [('Transfer_tool', 'OUTPUTS', 'CGYRO_schemes', scheme, 'tglf_inputs', 'input.tglf_1')])
        self.actions.settings['generated_tglf_source'] = json.dumps(sent[0]['path'])
        self.actions.use_generated_tglf()
        self.assertEqual(self.host.tg['FILES']['input.tglf']['BETAE'], .03)
        self.actions.settings['message'] = '已完成 4 个输入组合，结果已保存到 RUN_DB。'
        ui.events.clear()
        view.show_message(local=workbench.settings)
        self.assertFalse(ui.events)

    def test_legacy_cgyro_only_groups_still_list_cgyro_and_offer_no_tglf_card(self):
        groups = self.prepare()
        for group in groups.values():
            del group['tglf_inputs']
        self.assertEqual(len(schemes.scheme_sources(self.root)), 2)
        _, rows = initialize_tglf(self.root)
        self.assertFalse(any(row['group'] == 'transfer' for row in rows))

    def test_all_preflights_finish_before_generation(self):
        with patch.object(schemes, 'generation_issues', side_effect=[[], ['bad preset']]):
            with self.assertRaisesRegex(ValueError, 'bad preset'):
                schemes.generate_schemes(self.node, dict(all=True, separate_fast=True), self.options,
                                         lambda *args: self.fail('generated before validation'))

    def test_empty_generated_inputs_do_not_replace_previous_set(self):
        previous = self.prepare()
        with patch.object(schemes, 'generation_issues', return_value=[]):
            with self.assertRaisesRegex(ValueError, '没有生成'):
                schemes.generate_schemes(self.node, dict(all=True), self.options, lambda *args: None)
        self.assertIs(self.node['OUTPUTS']['CGYRO_schemes'], previous)

    def test_frozen_scheme_plan_separates_same_radius_and_ignores_live_conversion_settings(self):
        self.prepare()
        self.node['SETTINGS']['PHYSICS']['generation'] = {'particle_mode': 'new-draft'}
        work = self.actions.run_cgyro(prepare=True)
        self.assertEqual([row['runid'] for row in work], ['test__transfer_all', 'test__transfer_separate_fast'])
        self.assertEqual([row['batch_key'] for row in work], ['all:1', 'separate_fast:1'])
        self.assertEqual(len({row['case_id'] for row in work}), 1)
        batch = self.host.cg['BATCH_INPUTS']
        self.assertEqual(batch['all:1']['BASE']['Q'], 2.)
        self.assertEqual(batch['separate_fast:1']['BASE']['Q'], 3.)
        self.host.assert_no_scripts_run()

    def test_submission_uses_frozen_input_and_runid_then_restores_editor(self):
        self.prepare()
        self.host.cg['RUN_DB']['unrelated'] = Untouched()
        calls = []
        def submit(**kwargs):
            calls.append((self.host.cg['SETTINGS']['EXPERIMENT']['runid'],
                          self.host.cg['INPUTS']['input.cgyro']['Q']))
            self.host.cg['RUN_MANIFEST'] = dict(status='published')
        self.host.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = submit
        self.actions.run_cgyro()
        self.assertEqual(calls, [('test__transfer_all', 2.), ('test__transfer_separate_fast', 3.)])
        self.assertEqual(self.host.cg['SETTINGS']['EXPERIMENT']['runid'], 'test')

    def test_submission_failure_restores_result_name(self):
        self.prepare()
        self.host.cg['SCRIPTS']['runCGYRO.py'].run.side_effect = RuntimeError('submit failed')
        with self.assertRaisesRegex(RuntimeError, 'submit failed'):
            self.actions.run_cgyro()
        self.assertEqual(self.host.cg['SETTINGS']['EXPERIMENT']['runid'], 'test')

    def test_source_listing_reads_metadata_only_and_survives_json_metadata_roundtrip(self):
        frozen = self.prepare()
        for group in frozen.values():
            group['particle_record'] = json.loads(json.dumps(group['particle_record']))
            group['inputs']['input.cgyro_1'] = Untouched()
        rows = schemes.scheme_sources(self.root)
        self.assertEqual([row['rho'] for row in rows], [.33, .33])

    def test_scheme_checkboxes_do_not_request_refresh(self):
        ui = project_tests.UI(self.root)
        view = ProjectUI(self.actions, ui)
        view.transfer_schemes()
        choices = [kw for kind, args, kw in ui.events if kind == 'CheckBox']
        self.assertEqual(len(choices), len(schemes.SCHEMES))
        self.assertTrue(all(not kw.get('updateGUI', False) for kw in choices))


class CrossRunTests(unittest.TestCase):
    def setUp(self):
        self.root = compare_tests.fixture('CGYRO_vs_CGYRO')
        self.state = self.root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']
        db = self.root['CGYRO_scan']['RUN_DB']
        db['second'] = copy.deepcopy(db['run'])
        for point in db['second']['nr=2']['A'][2.]['lin'].values():
            point['freq']['gamma'][0][:] = 42.
        activate_source(self.state, 'run')
        self.state['selected_paras'] = {'A': [1.]}
        self.state['runid'] = 'second'
        activate_source(self.state, 'second')
        self.state.update(nr_CGYRO=['nr=2'], selected_paras={'A': [2.]},
                          compare_multiple_runs=True, compare_run_flags={'run': True, 'second': True})
        compare_tests.modules['cgyro'].FigureNotebook = compare_tests.Notebook

    def tearDown(self):
        compare_tests.plt.close('all')

    def test_saved_source_selections_are_independent_after_roundtrip(self):
        state = json.loads(json.dumps(self.state))
        chosen = selected_cgyro_runs(state)
        self.assertEqual([row['runid'] for row in chosen], ['run', 'second'])
        self.assertEqual([row['selected_paras']['A'] for row in chosen], [[1.], [2.]])
        self.assertEqual(state['runid'], 'second')

    def test_unconfigured_run_does_not_inherit_current_selection(self):
        self.state['compare_run_flags']['unconfigured'] = True
        self.root['CGYRO_scan']['RUN_DB']['unconfigured'] = {}
        errors = selection_check(self.root, 'CGYRO_vs_CGYRO')['errors']
        self.assertTrue(any('unconfigured' in error and '参数' in error for error in errors))

    def test_per_case_selection_mode_stays_with_its_run(self):
        self.state['force_read_all_nr_items'] = True
        self.state['selected_paras_by_nr'] = {'nr=2': {'A': [2.]}}
        self.state['runid'] = 'run'
        activate_source(self.state, 'run')
        choices = selected_cgyro_runs(self.state)
        self.assertFalse(choices[0].get('force_read_all_nr_items', False))
        self.assertTrue(choices[1]['force_read_all_nr_items'])
        self.assertEqual(choices[1]['selected_paras_by_nr'], {'nr=2': {'A': [2.]}})
        self.assertEqual(selection_check(self.root, 'CGYRO_vs_CGYRO')['errors'], [])

    def test_checked_only_plot_with_same_point_paths_has_distinct_data_and_labels(self):
        self.root['CGYRO_scan']['RUN_DB']['untouched'] = Untouched()
        figures = compare_tests.modules['cgyro'].run_plot(self.root)
        self.assertEqual(len(figures), 1)
        lines = figures[0].axes[2].get_lines()
        self.assertEqual(len(lines), 2)
        self.assertIn('run ·', lines[0].get_label())
        self.assertIn('second ·', lines[1].get_label())
        self.assertFalse((lines[0].get_ydata() == lines[1].get_ydata()).all())
        self.assertTrue((lines[1].get_ydata() == 42.).all())

    def test_unchecked_current_run_is_not_read(self):
        self.state['compare_run_flags']['second'] = False
        self.root['CGYRO_scan']['RUN_DB']['second'] = Untouched()
        figures = compare_tests.modules['cgyro'].run_plot(self.root)
        self.assertEqual(len(figures), 1)
        self.assertEqual(len(figures[0].axes[0].get_lines()), 1)

    def test_3d_uses_separate_surfaces_instead_of_merging_schemes(self):
        self.state['plot_mode'] = 'Plot 3D'
        figures = compare_tests.modules['cgyro'].run_plot(self.root)
        self.assertEqual(len(figures), 2)
        self.assertIn('run', figures[0].get_label())
        self.assertIn('second', figures[1].get_label())

    def test_exports_keep_source_names_and_statistical_window(self):
        with tempfile.TemporaryDirectory() as folder:
            self.state.update(linear_export_now=True, linear_export_dir=folder, ave_window=.5)
            exports = compare_tests.modules['cgyro'].run_plot(self.root)
            metadata = [json.loads((Path(path) / 'metadata.json').read_text()) for path in exports]
        self.assertEqual([row['runid'] for row in metadata], ['run', 'second'])
        self.assertEqual([row['averaging_fraction'] for row in metadata], [.5, .5])

    def test_run_checkboxes_only_list_names_and_do_not_refresh_or_parse_results(self):
        self.root['CGYRO_scan']['RUN_DB']['untouched'] = Untouched()
        ui = compare_tests.FakeUI(self.root)
        selector = CaseSelection(self.root, ui)
        with selector._catalog_scope():
            selector.render_mode_cgyro_vs_cgyro(self.state)
        checkboxes = [kw for tab, kind, args, kw in ui.events
                      if kind == 'CheckBox' and 'compare_run_flags' in args[0]]
        self.assertEqual(len(checkboxes), 3)
        self.assertTrue(all(not kw.get('updateGUI', False) for kw in checkboxes))


if __name__ == '__main__':
    unittest.main()
