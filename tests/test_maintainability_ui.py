"""Shared selection/runtime contracts; no GUI, network or real solver execution.

Reuse the repository's explicit native-reader stand-ins and solver fixtures.
Each test exercises production functions rather than copying their algorithms.
"""
import copy
import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
for library in (REPO / 'CGYRO_TGLF_scan').rglob('LIB'):
    sys.path.insert(0, str(library))
import test_cgyro_storage  # Existing fake native file boundaries.
import test_compare as comparison
import test_project as project
import test_tglf_multi as multi_fixture
import OMFITlib_project_runtime as runtime
import OMFITlib_tglf_multi_data as multi_data
import OMFITlib_compare_cgyro_selection as selection
import OMFITlib_compare_status as status
import OMFITlib_compare_options as options
import OMFITlib_compare_tglf as tglf
import OMFITlib_compare_dispatch as dispatch
import OMFITlib_plot_sources as plot_sources
from omfit_mapping import OMFITMapping as StrictTree, treeify


class SharedSelectionTests(unittest.TestCase):
    def test_independent_radius_never_falls_back_to_another_radius(self):
        context = dict(force_read_all_nr_items=True, selected_paras={'N_THETA': [16, 32]},
                       selected_paras_by_nr={'other': {'N_ENERGY': [8]}})
        self.assertEqual(list(status._iter_selected_parameter_items_for_nr(context, 'current')), [])
        self.assertEqual(list(selection.iter_selected_parameter_items(context, 'current')), [])

    def test_status_and_spectrum_keep_zero_empty_and_duplicate_semantics(self):
        for values, expected in ((0, [0.0]), (None, []), ([], []), ('0, 1, 0', [0.0, 1.0]),
                                 ([0, None, '', 2], [0.0, 2.0])):
            with self.subTest(values=values):
                context = dict(selected_paras={'A': values})
                result = [('A', expected)] if expected else []
                self.assertEqual(list(status._iter_selected_parameter_items_for_nr(context, 'r')), result)
                self.assertEqual(list(selection.iter_selected_parameter_items(context, 'r')), result)

    def test_statistical_defaults_drive_initialization_and_contexts(self):
        root = comparison.fixture()
        physics = root['SETTINGS']['PHYSICS']
        physics['compare_mode'] = 'CGYRO_vs_CGYRO'
        settings = physics['CGYRO_vs_CGYRO']
        for key in options.STAT_DEFAULTS:
            settings.pop(key, None)
        comparison.state.initialize_settings(root)
        for key, value in options.STAT_DEFAULTS.items():
            self.assertEqual(settings[key], value)
            self.assertEqual(selection.build_context(root)[key], value)


class TglfRenderingTests(unittest.TestCase):
    def setUp(self):
        self.root = comparison.fixture('TGLF_vs_TGLF')
        self.addCleanup(comparison.plt.close, 'all')

    def test_legacy_2d_selection_survives_gui_migration_and_matches_reader(self):
        for factory in (dict, StrictTree):
            with self.subTest(factory=factory):
                root = treeify(comparison.fixture('TGLF_vs_TGLF'), factory)
                record = root['SETTINGS']['PHYSICS']['TGLF_vs_TGLF']['TGLF']
                axes = {'A+B': {'para1_values': [1., 3.], 'para2_values': [2., 4.]}}
                record.update(dict(spectra_mode='2D', selected_paras_2d=copy.deepcopy(axes)))
                before = plot_sources.tglf_results(root, record)
                self.assertIs(before.node, root['TGLF_scan']['scanResults2D_spectra'])
                comparison.modules['ui'].ComparisonUI(root, comparison.FakeUI(root)).render()
                self.assertEqual(record['result_source'], 'legacy:2D')
                self.assertEqual(record['spectra_mode'], '2D')
                self.assertEqual(record['selected_paras_2d'], axes)
                self.assertIs(plot_sources.tglf_results(root, record).node, before.node)

    def test_source_resolution_preserves_explicit_choice_and_absent_legacy_fallback(self):
        choices = plot_sources.run_choices(self.root)
        self.assertEqual(plot_sources.selected_tglf_source(self.root,
            {'result_source': 'legacy:1D', 'spectra_mode': '2D'}, choices=choices), 'legacy:1D')
        self.assertEqual(plot_sources.selected_tglf_source(self.root,
            {'result_source': 'missing', 'spectra_mode': '2D'}, choices=choices), 'missing')
        self.assertEqual(plot_sources.selected_tglf_source(self.root,
            {'spectra_mode': '3D'}, choices=choices), next(iter(choices.values())))
        self.assertEqual(plot_sources.selected_tglf_source({}, {'spectra_mode': '2D'}), '')

    def test_dispatch_collects_each_mode_once_and_does_not_read_hidden_flux(self):
        record = self.root['SETTINGS']['PHYSICS']['TGLF_vs_TGLF']
        record['plot']['show_flux_spectra'] = False
        with patch.object(tglf, 'collect_tglf_curves', wraps=tglf.collect_tglf_curves) as collect, \
             patch.object(dispatch, 'collect_comparison_pages', side_effect=AssertionError('second collector')), \
             patch.object(tglf, 'collect_tglf_flux_spectrum_curves', side_effect=AssertionError('hidden flux')), \
             patch.object(tglf, 'render_tglf_spectrum_pages') as render:
            dispatch.run_plot(self.root)
        self.assertEqual(collect.call_count, 2)
        self.assertEqual(len(render.call_args.args[0]), 1)

    def test_empty_selection_creates_no_notebook(self):
        ctx = comparison.core.build_context(self.root)
        ctx['tglf_state']['rho_selected'] = []
        with patch.object(tglf, 'FigureNotebook', create=True, side_effect=AssertionError('empty window')):
            with self.assertRaises(ValueError):
                tglf.plot_tglf_vs_tglf(self.root, ctx)

    def test_prepared_pages_render_without_accessing_saved_tree(self):
        ctx = comparison.core.build_context(self.root)
        ctx['show_flux_spectra'] = False
        pages = tglf.collect_tglf_spectrum_pages(self.root, ctx)
        self.root.clear()
        with patch.object(tglf, 'FigureNotebook', comparison.Notebook, create=True), \
             patch.object(tglf, 'collect_tglf_curves', side_effect=AssertionError('renderer reads results')):
            tglf.render_tglf_spectrum_pages(pages, ctx)

    def test_2d_empty_axis_and_surface_display_scaling_preserve_raw_values(self):
        record = self.root['SETTINGS']['PHYSICS']['TGLF_vs_TGLF']
        record['TGLF'].update(spectra_mode='2D', selected_paras_2d={
            'A+B': {'para1_values': [], 'para2_values': [2.]}})
        record['plot'].update(tglf2d_plot_mode='3D', show_flux_spectra=False)
        ctx = comparison.core.build_context(self.root)
        self.assertEqual(tglf.collect_tglf_spectrum_pages(self.root, ctx), [])
        record['TGLF']['selected_paras_2d']['A+B']['para1_values'] = [1., 3.]
        record['TGLF']['selected_paras_2d']['A+B']['para2_values'] = [2., 4.]
        ctx = comparison.core.build_context(self.root)
        pages = tglf.collect_tglf_spectrum_pages(self.root, ctx)
        original = copy.deepcopy(pages)
        with patch.object(tglf, 'FigureNotebook', comparison.Notebook, create=True):
            tglf.render_tglf_spectrum_pages(pages, ctx)
        for before, after in zip(original, pages):
            for mode in (1, 2):
                for left, right in zip(before['curves'][mode], after['curves'][mode]):
                    comparison.np.testing.assert_array_equal(left['gamma'], right['gamma'])
                    comparison.np.testing.assert_array_equal(left['omega'], right['omega'])


class TglfResumeTests(unittest.TestCase):
    tree_factory = dict
    def setUp(self):
        self.fixture = multi_fixture.TestMultiInput(methodName='runTest')
        self.fixture.tree_factory = self.tree_factory
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_calculation_abort_resumes_only_unfinished_points(self):
        fixture = self.fixture
        fixture.settings['radii'] = '.3, .6'
        fixture.run_cases('prepare')
        original_execute = fixture.runner.ui.executable
        interrupted = [False]
        def execute(module, **kwargs):
            if 'r001' in kwargs['workdir'] and not interrupted[0]:
                interrupted[0] = True
                raise KeyboardInterrupt()
            return original_execute(module, **kwargs)
        fixture.runner.ui.executable = execute
        with self.assertRaises(KeyboardInterrupt):
            fixture.run_cases('run')
        run = fixture.latest()
        self.assertEqual(run['preparation_status'], 'complete')
        self.assertEqual(run['status'], 'cancelled')
        first_attempts = copy.deepcopy(run['points']['r000']['attempts'])
        fixture.run_cases('run')
        self.assertEqual(run['status'], 'complete')
        self.assertEqual(list(first_attempts), list(run['points']['r000']['attempts']))
        self.assertEqual(len(run['points']['r001']['attempts']), 2)

    def test_partial_preparation_abort_cannot_resume(self):
        fixture = self.fixture
        fixture.settings['radii'] = '.3, .6'
        original_prepare = fixture.runner.prepare
        def prepare(case, run):
            original_prepare(case, run)
            del run['points']['r001']
            raise KeyboardInterrupt()
        fixture.runner.prepare = prepare
        with self.assertRaises(KeyboardInterrupt):
            fixture.run_cases('prepare')
        with self.assertRaises(ValueError):
            fixture.run_cases('run')

    def test_legacy_cancelled_requires_complete_inputs_and_changed_plan_is_rejected(self):
        fixture = self.fixture
        fixture.run_cases('prepare')
        run = fixture.latest()
        run.pop('preparation_status')
        run['status'] = 'cancelled'
        self.assertEqual(multi_data.prepared_run_issues(run, run['plan'], run['profile_digest']), [])
        missing = run['points']['r000'].pop('input.tglf')
        self.assertTrue(multi_data.prepared_run_issues(run, run['plan'], run['profile_digest']))
        run['points']['r000']['input.tglf'] = missing
        self.assertTrue(multi_data.prepared_run_issues(run, dict(run['plan'], radii=[.6]), run['profile_digest']))

    def test_non_exception_abort_preserves_completed_preparation(self):
        class NativeAbort(BaseException):
            pass
        fixture = self.fixture
        fixture.run_cases('prepare')
        with patch.object(fixture.runner.ui, 'executable', side_effect=NativeAbort):
            with self.assertRaises(NativeAbort):
                fixture.run_cases('run')
        run = fixture.latest()
        self.assertEqual(run['status'], 'cancelled')
        self.assertEqual(run['preparation_status'], 'complete')
        point = run['points']['r000']
        self.assertEqual(point['attempts'][point['selected_attempt']]['status'], 'cancelled')

    def test_null_input_and_empty_point_map_cannot_be_resumed(self):
        fixture = self.fixture
        fixture.run_cases('prepare')
        run = fixture.latest()
        run['points']['r000']['input.tglf'] = None
        self.assertTrue(multi_data.prepared_run_issues(run, run['plan'], run['profile_digest']))
        run['points'] = {}
        self.assertTrue(multi_data.prepared_run_issues(run, run['plan'], run['profile_digest']))


class RuntimeContractTests(unittest.TestCase):
    tree_factory = dict
    def setUp(self):
        self.root = treeify(project.fixture(), self.tree_factory)
        config = runtime.initialize_runtime(self.root)
        config.update(dict(serverPicker='cluster', server='user@cluster', workDir='/work/user/gacode',
                           scheduler='slurm', queue='normal', environment='source /shared/setup'))
        runtime.apply_runtime(self.root)

    def test_all_written_scheduler_fields_are_checked_for_drift(self):
        settings = self.root['CGYRO_scan']['SETTINGS']
        remote = settings['REMOTE_SETUP']
        changes = [(remote, 'queue', 'other'), (remote, 'w', '00:01:00'),
                   (remote['cluster'], 'scheduler', 'pbs'), (remote['cluster'], 'array_parallel', 3),
                   (settings['SETUP'], 'wall_time', '00:01:00'), (settings['SETUP'], 'num_cores', 9)]
        for node, key, value in changes:
            with self.subTest(key=key):
                original = node[key]
                node[key] = value
                self.assertTrue(runtime.shared_issues(self.root))
                node[key] = original
                self.assertEqual(runtime.shared_issues(self.root), [])

    def test_abort_committing_applied_snapshot_restores_all_module_settings(self):
        class InterruptOnce(dict):
            armed = True
            def __setitem__(self, key, value):
                if key == 'gacode_runtime' and self.armed:
                    self.armed = False
                    raise KeyboardInterrupt()
                return super().__setitem__(key, value)
        self.root['PROJECT_STATE'] = InterruptOnce(self.root['PROJECT_STATE'])
        config = runtime.initialize_runtime(self.root)
        config['cores'] = 7
        originals = {name: copy.deepcopy(runtime.node_at(self.root, path)['SETTINGS'])
                     for name, path in runtime.TARGETS.items() if path}
        applied = copy.deepcopy(runtime.applied_runtime(self.root))
        with self.assertRaises(KeyboardInterrupt):
            runtime.apply_runtime(self.root)
        for name, path in runtime.TARGETS.items():
            if path:
                self.assertEqual(runtime.node_at(self.root, path)['SETTINGS'], originals[name])
        self.assertEqual(runtime.applied_runtime(self.root), applied)

    def test_tgyro_expanded_dir_rank_count_is_not_runtime_drift(self):
        settings = self.root['TGLF_scan']['TGYRO']['SETTINGS']
        settings['SETUP']['executable'] = settings['REMOTE_SETUP']['environment'] + '\ntgyro -e . -n 3'
        self.assertEqual(runtime.shared_issues(self.root), [])
        settings['SETUP']['executable'] += '; echo modified'
        self.assertTrue(runtime.shared_issues(self.root))

    def test_malformed_legacy_resource_is_reported_without_raising(self):
        self.root['Transfer_tool']['SETTINGS']['SETUP']['p_tgyro'] = 'not-an-integer'
        self.assertTrue(runtime.shared_issues(self.root))
        self.root['Transfer_tool']['SETTINGS']['SETUP']['p_tgyro'] = 3
        self.root['CGYRO_scan']['SETTINGS']['REMOTE_SETUP'] = None
        self.assertTrue(runtime.shared_issues(self.root))


class StrictTglfResumeTests(TglfResumeTests):
    tree_factory = StrictTree


class StrictRuntimeContractTests(RuntimeContractTests):
    tree_factory = StrictTree


if __name__ == '__main__':
    unittest.main()
