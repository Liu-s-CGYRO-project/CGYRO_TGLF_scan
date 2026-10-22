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
                dimensions=1, scan_dimensions=1, collection_status='empty' if empty else 'partial')
    task = dict(task_id='p000001', result_path=['N_THETA', '16', 'lin', '0.1'],
                values=dict(N_THETA=16, KY=.1))
    tasks = {} if empty else {'p000001': task}
    archive = {} if empty else {'Jet': {'nr=1_rho=0.33': {
        'N_THETA': {'16': {'lin': {'0.1': {'__RESULT_REF__': 'physical-result'}}}},
        '__SCANS__': {'N_THETA': dict(info=copy.deepcopy(info), tasks=tasks)}}}}
    archive['__STORAGE__'] = dict(case_layout='radius-scans')
    archive['__RUNS__'] = {'current': {'manifest': copy.deepcopy(info)}}
    return dict(SETTINGS=dict(WORKBENCH={}), CGYRO_scan=dict(RUN_DB=archive, RUN_MANIFEST=info))


class ResultMetadataTests(unittest.TestCase):
    def test_unindexed_partial_and_inherited_results_keep_slice_controls(self):
        for status in ('partial', 'empty'):
            with self.subTest(status=status):
                root, ui = fixture(empty=True), UI()
                manifest = root['CGYRO_scan']['RUN_MANIFEST']
                manifest.update(collection_status=status,
                                continuation={'source_token': 'ancestor'} if status == 'empty' else {})
                info = dict(manifest, dimensions=2,
                            scan_axes=[dict(name='N_ENERGY'), dict(name='N_XI')])
                tasks = {'p000001': dict(values=dict(N_ENERGY=8, N_XI=16, KY=.1))}
                context = dict(info=info, view={'__TASKS__': tasks}, rows=tasks)
                with patch.object(browser, 'stopped_context', return_value=context) as resolve:
                    browser.ResultBrowser(root, ui).render(title=False)
                resolve.assert_called_once_with(root['CGYRO_scan'], 'current')
                self.assertIn('查看数值表', ui.buttons)
                self.assertIn('绘制当前结果', ui.buttons)
                self.assertTrue(any(args[2] == 'ky 切片' for args in ui.combos))
                self.assertTrue(any('1 个已读取计算点' in value for value in ui.labels))

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
        with patch.object(browser, 'stopped_context', side_effect=AssertionError('opened restart ancestry')), \
                patch.object(browser, 'resolve_result', side_effect=AssertionError('opened a result')):
            browser.ResultBrowser(root, ui, continue_callback=lambda *args: None).render(title=False)
        self.assertTrue(any('1 个已读取计算点' in value for value in ui.labels))
        self.assertIn('时间曲线 / 选择点续算…', ui.buttons)
        self.assertEqual(root['CGYRO_scan'], before)

    def test_empty_current_run_keeps_resume_button_without_resolving(self):
        root, ui = fixture(empty=True), UI()
        with patch.object(browser, 'stopped_context', side_effect=AssertionError('opened restart ancestry')):
            browser.ResultBrowser(root, ui, continue_callback=lambda *args: None).render(title=False)
        self.assertIn('选择未完成点继续计算…', ui.buttons)
        self.assertTrue(any('原始输入已保留' in value for value in ui.labels))

    def test_explicit_reader_still_checks_ancestry_and_reports_failure(self):
        root = fixture()
        with patch.object(browser, 'stopped_context', side_effect=ValueError('missing frozen ancestry')) as check:
            _, token, entry, _ = browser.selected_record(root)
        check.assert_called_once_with(root['CGYRO_scan'], 'current')
        self.assertEqual(token, 'current')
        self.assertEqual(entry['resume_error'], 'missing frozen ancestry')

    def test_explicit_reader_receives_frozen_point_identity(self):
        root = fixture()
        context = dict(info={}, view={'__TASKS__': {'frozen': {}}}, rows={'frozen': {}})
        with patch.object(browser, 'stopped_context', return_value=context):
            _, _, entry, _ = browser.selected_record(root)
        self.assertIs(entry['resume_context'], context)
        self.assertIs(entry['resume_tasks'], context['rows'])

    def test_next_render_sees_new_archive_metadata(self):
        root = fixture()
        browser.selected_record(root, resolve_stopped=False)
        scan = root['CGYRO_scan']['RUN_DB']['Jet']['nr=1_rho=0.33']['__SCANS__']['N_THETA']
        scan['tasks']['p000002'] = dict(result_path=['N_THETA', '16', 'lin', '-0.2'],
                                      values=dict(N_THETA=16, KY=-.2))
        ui = UI()
        browser.ResultBrowser(root, ui).render(title=False)
        self.assertTrue(any('2 个已读取计算点' in value for value in ui.labels))
        self.assertFalse(any('cache' in key.lower() for key in root['SETTINGS']['WORKBENCH']))


if __name__ == '__main__':
    unittest.main()
