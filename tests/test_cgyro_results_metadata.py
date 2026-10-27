"""Control refreshes must not open result files or join restart ancestry."""
from contextlib import nullcontext
import copy
import unittest
from unittest.mock import patch
import numpy as np

# Reuse only the isolated native file stand-ins; no GUI, solver or file is opened.
import test_cgyro_storage
import OMFITlib_cgyro_results as browser


class UI:
    def __init__(self):
        self.labels, self.buttons, self.combos = [], {}, []

    def Label(self, text, **kwargs):
        self.labels.append(text)

    def Button(self, text, callback, **kwargs):
        self.buttons[text] = callback

    def ComboBox(self, *args, **kwargs):
        self.combos.append(args)

    def Entry(self, *args, **kwargs):
        pass

    def same_row(self):
        return nullcontext()


def fixture(empty=False):
    info = dict(run_token='current', runid='Jet', case_id='nr=1__rho=0.33__ion=BASE',
                source_nr=1, nr=1, rho=.33, ion_case='BASE', mass='BASE',
                scan_axes=[dict(name='N_THETA', values=[16], linked=[])],
                dimensions=1, scan_dimensions=1, collection_status='empty' if empty else 'partial',
                unpublished_points=['p000001'] if empty else [])
    task = dict(task_id='p000001', result_path=['N_THETA', '16', 'lin', '0.1'],
                values=dict(N_THETA=16, KY=.1))
    tasks = {} if empty else {'p000001': task}
    archive = {} if empty else {'Jet': {'nr=1_rho=0.33': {
        'N_THETA': {'16': {'lin': {'0.1': {'__RESULT_REF__': 'a' * 64}}}},
        '__SCANS__': {'N_THETA': dict(info=copy.deepcopy(info), tasks=tasks)}}}}
    archive['__STORAGE__'] = dict(case_layout='radius-scans')
    saved = dict(info, point_table={'p000001': copy.deepcopy(task)}, points=['p000001'], input_sha256={'p000001': {'input.cgyro': 'a' * 64}})
    archive['__RUNS__'] = {'current': {'manifest': saved, 'cases': {} if empty else {'p000001': {'__RESULT_REF__': 'a' * 64}}}}
    return dict(SETTINGS=dict(WORKBENCH={}), CGYRO_scan=dict(RUN_DB=archive, RUN_MANIFEST=info))


class ResultMetadataTests(unittest.TestCase):
    def test_averages_and_window_follow_each_requested_fraction(self):
        result = dict(n_time=10, t=np.arange(10.), freq=dict(omega=[np.arange(10.)], gamma=[2 * np.arange(10.)]))
        short = browser._frequency_summary(result, .2)
        long = browser._frequency_summary(result, .5)
        self.assertEqual(short[:2], (8.5, 17.))
        self.assertEqual(long[:2], (7., 14.))
        self.assertEqual(browser.frequency_window(result, .2),
                         dict(tail_fraction=.2, samples=2, total_samples=10, start_time=8., end_time=9.))
        self.assertEqual(browser.frequency_window(result, .5)['start_time'], 5.)

    def two_partial_records(self):
        root = fixture()
        db = root['CGYRO_scan']['RUN_DB']
        other = copy.deepcopy(db['Jet']['nr=1_rho=0.33'])
        info = other['__SCANS__']['N_THETA']['info']
        info.update(run_token='other', nr=2, source_nr=2, rho=.5,
                    case_id='nr=2__rho=0.5__ion=BASE')
        db['Jet']['nr=2_rho=0.5'] = other
        db['__RUNS__']['other'] = {'manifest': copy.deepcopy(info)}
        return root

    def test_reader_does_not_resolve_an_unselected_radius(self):
        root = self.two_partial_records()
        root['SETTINGS']['WORKBENCH']['cgyro_result_view'] = dict(run_token='current')
        with patch.object(browser, 'selected_result', side_effect=AssertionError('Opened a payload')):
            _, _, entry, options = browser.selected_record(root)
        self.assertEqual(entry['run_token'], 'current')
        self.assertEqual(len(options), 2)

    def test_explicit_selection_is_kept_and_missing_version_is_not_substituted(self):
        root = self.two_partial_records()
        view = dict(run_token='other'); root['SETTINGS']['WORKBENCH']['cgyro_result_view'] = view
        _, key, entry, _ = browser.selected_record(root)
        self.assertEqual(entry['run_token'], 'other')
        self.assertEqual(view['run_token'], key)
        view['run_token'] = 'deleted-record'
        with self.assertRaisesRegex(ValueError, '重新选择'):
            browser.selected_record(root)
        self.assertEqual(view['run_token'], 'deleted-record')

    def test_unselected_unindexed_continuation_does_not_open_its_source(self):
        root = self.two_partial_records()
        root['CGYRO_scan']['RUN_MANIFEST'].update(run_token='unindexed', continuation={'source_token': 'missing'})
        root['SETTINGS']['WORKBENCH']['cgyro_result_view'] = dict(run_token='other')
        with patch.object(browser, 'selected_result', side_effect=AssertionError('Result files')):
            _, _, entry, options = browser.selected_record(root)
        self.assertEqual(entry['run_token'], 'other')
        self.assertNotIn('unindexed', options.values())

    def test_collected_partial_version_keeps_slice_controls_without_parent(self):
        root, ui = fixture(empty=True), UI()
        record = root['CGYRO_scan']['RUN_DB']['__RUNS__']['current']
        record['manifest'].update(dimensions=2, collection_status='partial',
            scan_axes=[dict(name='N_ENERGY'), dict(name='N_XI')], continuation={'source_token': 'missing'})
        record['manifest']['point_table']['p000001'] = dict(values=dict(N_ENERGY=8, N_XI=16, KY=.1),
            result_path=['N_ENERGY__N_XI', '8', 'N_XI', '16', 'lin', '.1'])
        record['cases'] = {'p000001': {'__RESULT_REF__': 'a' * 64}}
        with patch.object(browser, 'selected_result', side_effect=AssertionError('Result files')):
            browser.ResultBrowser(root, ui).render(title=False)
        self.assertIn('查看数值表', ui.buttons)
        self.assertTrue(any(args[2] == 'ky 切片' for args in ui.combos))

    def test_coordinate_choices_preserve_signed_values_and_tolerance(self):
        values = [1., 1. + 5e-11, 1. + 2e-10, -.1, -.1, .1, -0., 0.,
                  np.nan, np.inf, -np.inf, 'bad', None] * 30
        expected = []
        for raw in values:
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if np.isfinite(value) and not any(np.isclose(value, item, rtol=1e-10, atol=1e-12)
                                             for item in expected):
                expected.append(value)
        rows = [dict(values=dict(KY=value)) for value in values]
        with patch.object(np, 'isclose', side_effect=AssertionError('numpy scalar allocation')):
            self.assertEqual(browser._unique_numeric(rows, 'KY'), sorted(expected))

    def test_render_partial_record_uses_metadata_only(self):
        root, ui = fixture(), UI()
        before = copy.deepcopy(root['CGYRO_scan'])
        with patch.object(browser, 'selected_result', side_effect=AssertionError('opened result files')), \
                patch.object(browser, 'resolve_result', side_effect=AssertionError('opened a result')):
            browser.ResultBrowser(root, ui, continue_callback=lambda *args: None).render(title=False)
        self.assertTrue(any('1 个已有结果计算点' in value for value in ui.labels))
        self.assertIn('时间曲线 / 选择点续算…', ui.buttons)
        self.assertEqual(root['CGYRO_scan'], before)

    def test_empty_current_run_keeps_resume_button_without_resolving(self):
        root, ui = fixture(empty=True), UI()
        with patch.object(browser, 'selected_result', side_effect=AssertionError('opened result files')):
            browser.ResultBrowser(root, ui, continue_callback=lambda *args: None).render(title=False)
        self.assertIn('选择未完成点继续计算…', ui.buttons)
        self.assertTrue(any('原始输入已保留' in value for value in ui.labels))

    def test_explicit_reader_reports_missing_selected_files_without_substitution(self):
        root = fixture()
        _, _, entry, _ = browser.selected_record(root)
        with self.assertRaisesRegex(ValueError, 'Missing physical'):
            browser._result_node(root, entry, entry['tasks']['p000001'])

    def test_explicit_reader_receives_frozen_result_identity(self):
        root = fixture()
        _, _, entry, _ = browser.selected_record(root)
        binding = browser.select_result(root['CGYRO_scan'], entry, 'p000001')
        self.assertEqual(binding['result_id'], 'a' * 64)
        self.assertEqual(binding['identity']['values'], dict(N_THETA=16., KY=.1))
        self.assertEqual(binding['identity']['case_id'], 'nr=1__rho=0.33__ion=BASE')

    def test_next_render_sees_new_archive_metadata(self):
        root = fixture()
        browser.selected_record(root, resolve_stopped=False)
        scan = root['CGYRO_scan']['RUN_DB']['Jet']['nr=1_rho=0.33']['__SCANS__']['N_THETA']
        scan['tasks']['p000002'] = dict(result_path=['N_THETA', '16', 'lin', '-0.2'],
                                      values=dict(N_THETA=16, KY=-.2))
        ui = UI()
        browser.ResultBrowser(root, ui).render(title=False)
        self.assertTrue(any('2 个已有结果计算点' in value for value in ui.labels))
        self.assertFalse(any('cache' in key.lower() for key in root['SETTINGS']['WORKBENCH']))


if __name__ == '__main__':
    unittest.main()
