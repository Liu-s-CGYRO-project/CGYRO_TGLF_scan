"""Fail on any science-array read outside the user's current operation.

The older path-only OMFITcgyro double is intentionally not a dict. Here we
model the native dict inheritance and loading membership operator as well;
otherwise harmless-looking marker tests escape all metadata-only regressions.
"""
import importlib
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import test_cgyro_storage as fixture
import test_cgyro_task_cleanup as task_fixture

storage, db = fixture.storage, fixture.db_api
payload = importlib.import_module('OMFITlib_cgyro_payload')


class OMFITcgyro(dict, fixture.OMFITcgyro):
    def __init__(self, owner, data=None, reads=None, allowed=False):
        dict.__init__(self)
        self.__dict__.update(vars(owner))
        self.data, self.reads, self.allowed = data or {}, reads, allowed

    def read(self):
        if self.reads is not None:
            self.reads.add(self.filename)
        if not self.allowed:
            raise AssertionError('Unselected result read: ' + self.filename)
        return self.data

    def __getitem__(self, key):
        return self.read()[key]

    def __contains__(self, key):
        return key in self.read()

    def __iter__(self):
        return iter(self.read())

    def __len__(self):
        return len(self.read())

    def get(self, key, default=None):
        return self.read().get(key, default)

    def keys(self):
        return self.read().keys()

    def items(self):
        return self.read().items()

    def values(self):
        return self.read().values()

    def __deepcopy__(self, memo):
        raise AssertionError('Unexpected result copy: ' + self.filename)


def guard_pool(module):
    pool = storage.result_pool(module)
    reads = set()
    for key in list(pool):
        if storage.is_result(pool[key]):
            pool[key] = OMFITcgyro(pool[key], reads=reads)
    return reads


class ReadBoundaryTests(unittest.TestCase):
    setUp, tearDown = fixture.StorageCases.setUp, fixture.StorageCases.tearDown
    result = fixture.StorageCases.result

    def test_marker_checks_never_enter_native_mapping_or_lazy_reader(self):
        owner = OMFITcgyro(self.result('native'))
        wrapper = fixture.OMFITlazyLoad(owner, failure=AssertionError('Lazy file opened'))
        wrapper.tp = 'OMFITcgyro'
        for node in (owner, wrapper):
            with self.subTest(kind=type(node).__name__):
                self.assertFalse(payload.is_packed(node))
                self.assertIsNone(fixture.files.file_reference_id(node))
                self.assertFalse(fixture.files.SubmissionFiles({}, dict).bundle(node))
                self.assertIs(storage.result_view({}, node), node)

    def test_preview_and_delete_keep_other_native_results_unopened(self):
        case = task_fixture.TaskCleanupTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        module = case.module
        before = case.public_rows()
        reads = guard_pool(module)
        with patch.object(payload, 'materialize_owner', side_effect=AssertionError('Result expanded')):
            report = task_fixture.cleanup.preview_tasks(module, ['old'])
            task_fixture.cleanup.remove_tasks(module, ['old'], report, report['confirmation'])
        self.assertEqual(case.public_rows(), [row for row in before if row[3] != 'old'])
        self.assertEqual(len(storage.result_pool(module)), 4)
        self.assertFalse(reads)

    def test_indexed_queue_bookkeeping_and_reachability_read_no_arrays(self):
        module = {}
        refs = [storage.store_result(module, self.result(str(i), str(i).encode())) for i in range(7)]
        module['RUN_DB']['kept'] = dict(enumerate(refs))
        module['RUN_MANIFEST'] = dict(run_token='current', status='submitted', case_tag='case')
        reads = guard_pool(module)
        with patch.object(payload, 'materialize_owner', side_effect=AssertionError('Result expanded')), \
                patch.object(storage, 'archive_inventory', side_effect=AssertionError('Historical bytes read')):
            fixture.queue_api.save_current(module)
            self.assertEqual(storage.prune_storage(module), 0)
            self.assertEqual(storage.compact_storage(module)['physical_results'], 7)
        self.assertEqual(len(storage.result_pool(module)), 7)
        self.assertFalse(reads)

    def test_new_submission_does_not_compact_unrelated_legacy_payloads(self):
        old = OMFITcgyro(self.result('legacy'))
        module = dict(RUN_DB={'old': {'unindexed': old}},
                      RUN_MANIFEST=dict(run_token='current', status='submitted', case_tag='case'))
        bundle, _ = fixture.StorageCases.bundle(self, 'new-input', zip_only=True)
        db.set_run_cases(module, module['RUN_MANIFEST'], {'p000001': bundle})
        with patch.object(storage, 'archive_inventory', side_effect=AssertionError('Historical bytes read')):
            fixture.queue_api.save_current(module)
        self.assertIs(module['RUN_DB']['old']['unindexed'], old)
        self.assertIsNotNone(fixture.files.file_reference_id(db.run_cases(module)['p000001']['zip']))
        self.assertNotEqual(storage.storage_state(module).get('checkpoint_policy', 0), storage.CHECKPOINT_POLICY_VERSION)

    def test_scoped_compaction_rolls_back_only_current_run_after_state_commit_failure(self):
        first = {'result': self.result('current')}
        unrelated = {'result': OMFITcgyro(self.result('other'))}
        state = dict(version=db.STORAGE_SCHEMA_VERSION, checkpoint_policy=0)
        aborted = KeyboardInterrupt('state write interrupted')
        class FailingDB(dict):
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                if key == db.STATE and value is not state:
                    raise aborted
        records = {'current': first, 'other': unrelated}
        run_db = FailingDB({db.RUNS: records, db.STATE: state})
        module = {'RUN_DB': run_db}
        with self.assertRaises(KeyboardInterrupt) as caught:
            storage.compact_storage(module, run_token='current')
        self.assertIs(caught.exception, aborted)
        self.assertIs(records['current'], first)
        self.assertIs(records['other'], unrelated)
        self.assertIs(run_db[db.STATE], state)
        self.assertFalse(storage.result_pool(module))

    def test_status_curve_reads_only_log_tail_for_the_selected_scan(self):
        status = importlib.import_module('OMFITlib_compare_status')
        module = {}
        case = fixture.StorageCases.indexed_scan(self, module, 'selected', 'T', values=(16, 32), ky_count=2)
        module['RUN_DB']['Jet'] = {'case': case}
        for owner in storage.result_pool(module).values():
            (Path(owner.filename) / 'out.cgyro.info').write_text('LINEAR CONVERGED\n')
        reads = guard_pool(module)
        curves = status._collect_cgyro_output_status_curves({'CGYRO_scan': module}, {}, 'Jet', 'case', 'N_THETA', [16])
        self.assertEqual(len(curves), 1)
        self.assertEqual(list(curves[0]['status']), [0, 0])
        self.assertFalse(reads)

    def test_checkpoint_preview_reads_small_files_and_does_not_certify_binary(self):
        module = {}
        owner = self.result('preview')
        directory = Path(owner.filename)
        (directory / 'out.cgyro.time').write_text('0\n1\n2\n')
        (directory / 'out.cgyro.tag').write_text('2\n1.0D0\n')
        (directory / 'out.cgyro.info').write_text('Linear terminated at max time\n')
        (directory / 'bin.cgyro.restart').write_bytes(b'invalid checkpoint')
        reference = storage.store_result(module, owner)
        with patch.object(payload, 'ensure_capacity', return_value={}):
            payload.pack_results(module, storage.directory_inventory)
        result = storage.resolve_result(module, reference)
        original_digest = payload.file_digest
        def small_file_digest(path):
            self.assertLess(Path(path).stat().st_size, 100)
            self.assertNotEqual(Path(path).read_bytes(), b'invalid checkpoint')
            return original_digest(path)
        with patch.object(payload, 'materialize_owner', side_effect=AssertionError('Expanded directory')), \
                patch.object(payload, 'file_digest', side_effect=small_file_digest), \
                patch.object(fixture.continuation, 'checkpoint_tag', side_effect=AssertionError('Binary read')):
            status = fixture.continuation.point_status(result, verify_checkpoint=False)
        self.assertEqual(status['convergence'], 'max_time')
        self.assertEqual(status['checkpoint']['time'], 1.)
        self.assertEqual(status['checkpoint']['last_time'], 2.)
        self.assertIn('预览', status['reason'])
        # Ordinary continuation still performs the full structural validation;
        # previewing an invalid binary cannot turn it into a usable checkpoint.
        self.assertIsNone(fixture.continuation.point_status(owner)['checkpoint'])

    def test_checkpoint_preview_rejects_invalid_time_hints(self):
        owner = self.result('bad-preview')
        directory = Path(owner.filename)
        (directory / 'out.cgyro.time').write_text('0\n1\n')
        for tag in ('', '0 0', '1 -1', '1 nan', '1 inf', '1 2', 'garbled'):
            with self.subTest(tag=tag):
                (directory / 'out.cgyro.tag').write_text(tag)
                self.assertIsNone(fixture.continuation.point_status(owner, verify_checkpoint=False)['checkpoint'])

    def test_continuation_validates_only_selected_checkpoint_and_still_rejects_damage(self):
        first, second = self.result('selected'), self.result('unselected')
        case = dict(__INFO__={}, __TASKS__={
            'p000001': dict(result_path=['first']), 'p000002': dict(result_path=['second'])},
            first=first, second=second)
        api = fixture.continuation
        with patch.object(api, 'stopped_context', return_value=None), \
                patch.object(api, 'archived_case', return_value=('Jet', 'case', case)), \
                patch.object(api, 'checkpoint_tag', side_effect=ValueError('Damaged checkpoint')) as check:
            with self.assertRaisesRegex(ValueError, 'Damaged checkpoint'):
                api.continuation_plan({}, 'run', ['p000001'], 10)
        check.assert_called_once_with(first.filename)

    def test_point_picker_and_selection_do_not_read_arrays_or_validate_all_binaries(self):
        import tkinter as tk
        from tkinter import ttk
        from types import SimpleNamespace
        import OMFITlib_cgyro_results as browser
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)
        rows, results = {}, {}
        reads = set()
        for number in (1, 2):
            point = 'p{:06d}'.format(number)
            owner = self.result(point)
            directory = Path(owner.filename)
            (directory / 'out.cgyro.time').write_text('0\n1\n')
            (directory / 'out.cgyro.tag').write_text('2 1\n')
            rows[point] = dict(task_id=point, values=dict(KY=.1 * number))
            results[point] = OMFITcgyro(owner, reads=reads)
        # No retained ZIP needs to be touched just to list this unstarted row.
        unstarted = 'p000003'
        view = {'__TASKS__': rows}
        context = dict(view=view, unfinished={unstarted}, sources={unstarted: (
            dict(input_sha256={unstarted: {'input.cgyro': 'a' * 64}}), {})})
        entry = dict(tasks=rows, resume_tasks=dict(rows, p000003=dict(values=dict(KY=.3))),
                     stopped_run=True, resume_context=context, scan_axes=[], runid='Jet')
        plot = Mock()
        root = dict(CGYRO_scan={}, PLOTS={'CGYRO_results': SimpleNamespace(plot=plot)})
        browser_ui = browser.ResultBrowser(root, None, continue_callback=Mock())
        browser_ui.anchor = ttk.Frame(window)
        with patch.object(browser, 'selected_record', return_value=({}, 'run', entry, {})), \
                patch.object(browser, '_result_node', side_effect=lambda root, entry, row: results[row['task_id']]), \
                patch.object(browser, 'configure_window_fonts'), patch.object(browser, 'style_widget'), \
                patch.object(fixture.continuation, 'checkpoint_tag', side_effect=AssertionError('Binary read')), \
                patch.object(fixture.continuation, 'resume_source', side_effect=AssertionError('Input ZIP read')):
            browser_ui._show_points()
            def widgets(parent):
                for child in parent.winfo_children():
                    yield child
                    yield from widgets(child)
            children = list(widgets(window))
            table = next(child for child in children if isinstance(child, ttk.Treeview))
            self.assertEqual(table.selection(), (unstarted,))
            self.assertIn('待校验', table.set('p000001', 'checkpoint'))
            self.assertIn('待校验', table.set(unstarted, 'checkpoint'))
            table.selection_set('p000002')
            next(child for child in children if isinstance(child, ttk.Button) and
                 child.cget('text') == '绘制 omega & gamma vs time').invoke()
        plot.assert_called_once_with(time_traces=True, run_token='run', point_ids=['p000002'], stopped_points=True)
        self.assertFalse(reads)


class PlotReadBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Import after the isolated native modules so ordinary regression
        # discovery does not require the developer's installed OMFIT stack.
        import test_compare as comparison
        from types import SimpleNamespace
        import numpy as np
        self.comparison = comparison
        self.root = comparison.fixture('CGYRO_vs_CGYRO')
        self.settings = self.root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']
        self.settings.update(selected_paras={'A': [1.]})
        self.reads, self.points = set(), {}
        for radius, case in self.root['CGYRO_scan']['RUN_DB']['run'].items():
            for value, branch in case['A'].items():
                for ky, data in list(branch['lin'].items()):
                    data['t'] = np.arange(data['n_time'])
                    data['balloon'] = dict(theta_b_over_pi=np.array([-1., 0., 1.]),
                                           balloon_phi=np.array([1., 2., 1.], dtype=complex))
                    identity = (radius, value, ky)
                    owner = SimpleNamespace(filename='/fixture/' + '/'.join(map(str, identity)))
                    result = OMFITcgyro(owner, data, self.reads)
                    self.points[identity] = result
                    branch['lin'][ky] = result

    def collect(self, allowed, **settings):
        for identity in allowed:
            self.points[identity].allowed = True
        self.settings.update(settings)
        ctx = self.comparison.modules['cgyro_selection'].build_context(self.root)
        items = self.comparison.modules['cgyro'].collect_plot_items(self.root, ctx)
        self.assertTrue(items, ctx['_diagnostics'])
        self.assertEqual(self.reads, {self.points[key].filename for key in allowed})
        return items

    def test_time_traces_read_only_nearest_selected_ky(self):
        self.collect([('nr=2', 1., '0.2')], plot_mode='Plot time traces', time_ky_values='.21 .21')

    def test_signed_time_selection_preserves_negative_coordinate(self):
        node = self.root['CGYRO_scan']['RUN_DB']['run']['nr=2']['A'][1.]['lin']
        point = self.points.pop(('nr=2', 1., '0.4'))
        node['-0.4'] = node.pop('0.4')
        point.data['kyrhos'] = -.4
        self.points[('nr=2', 1., '-0.4')] = point
        # A hidden abs-ky display setting must not alter raw time traces.
        self.collect([('nr=2', 1., '-0.4')], plot_mode='Plot time traces',
                     time_ky_values='-.41', abs_ky=True)

    def test_single_ky_parameter_plot_does_not_read_other_ky_or_radius(self):
        self.collect([('nr=2', 1., '0.2')], plot_mode='Plot single ky', single_ky_values='.21')

    def test_single_ky_ratio_does_not_read_other_ky(self):
        self.collect([('nr=2', 1., '0.2')], plot_mode='Plot γ/γ_ref', gamma_ref_mode='single ky',
                     gamma_ref_ky_values='.21')

    def test_explicit_eigen_ky_skips_frequency_and_fields_of_other_points(self):
        self.collect([('nr=2', 1., '0.2')], plot_mode='Plot eigen ball', eigen_ky_mode='single ky',
                     eigen_ky_values='.21')

    def test_spectrum_and_max_gamma_read_only_selected_parameter_and_radius(self):
        allowed = [('nr=2', 1., ky) for ky in ('.1', '.2', '.4', '.8')]
        allowed = [(nr, value, str(float(ky))) for nr, value, ky in allowed]
        for mode in ('Plot 2D', 'Plot eigen ball'):
            with self.subTest(mode=mode):
                self.reads.clear()
                self.collect(allowed, plot_mode=mode)

    def test_main_ion_scaled_selection_uses_small_input_before_arrays(self):
        inputs = {}
        for result in self.points.values():
            result.data['input.cgyro.gen']['MASS_1'] = 4.
            inputs[Path(result.filename) / 'input.cgyro.gen'] = result.data['input.cgyro.gen']
        with patch.object(payload.native_readers, 'OMFITgacode',
                          side_effect=lambda name: inputs[Path(name)], create=True):
            self.collect([('nr=2', 1., '0.2')], plot_mode='Plot single ky', single_ky_values='.41',
                         normalize_main_ion=True)

    def test_comparison_controls_do_not_load_results_in_any_mode(self):
        modules = self.comparison.modules
        for mode in modules['state'].MODES:
            self.root['SETTINGS']['PHYSICS']['compare_mode'] = mode
            modules['ui'].ComparisonUI(self.root, self.comparison.FakeUI(self.root)).render()
        self.assertFalse(self.reads)


if __name__ == '__main__':
    unittest.main()
