"""History retention must not load, copy or discard result-bearing records."""
import copy
import json
import unittest
from unittest.mock import patch
import test_cgyro_storage  # Isolated native reader stand-ins.
from test_project import fixture, CgyroInput
from OMFITlib_project import ProjectActions
import OMFITlib_project_history as history
import OMFITlib_workbench_runtime_ui as runtime_ui


class Unreadable:
    def __bool__(self):
        raise AssertionError('payload was opened')

    def __deepcopy__(self, memo):
        raise AssertionError('payload was copied')


class ProjectHistoryTests(unittest.TestCase):
    def setUp(self):
        self.root = fixture()
        self.actions = ProjectActions(self.root)
        self.records = self.root['PROJECT_STATE'].setdefault('activity', {})

    def test_logs_are_bounded_but_failures_have_separate_budget(self):
        for i in range(history.LOG_LIMIT + 30):
            self.actions._record(str(i), status='returned')
        for i in range(history.ERROR_LOG_LIMIT + 10):
            self.actions.report_error('error ' + str(i), RuntimeError(str(i)))
        self.assertEqual(history.history_counts(self.records), dict(log=120, input_backup=0, retained=0))
        self.assertEqual([r['title'] for r in self.records.values() if r['status'] == 'returned'][0], '30')
        self.assertEqual([r['title'] for r in self.records.values() if r['status'] == 'failed'][0], 'error 10')

    def test_pending_unknown_payload_and_result_backups_are_never_pruned_or_read(self):
        payload = Unreadable()
        for field in ('previous_tglf_files', 'tglf_data', 'tgyro_result', 'incoming', 'unrecognized_payload', 'previous_inputs'):
            self.records[field] = dict(status='archived', **{field: payload})
        self.records['pending'] = dict(status='running')
        self.records['choice'] = dict(status='awaiting_choice', previous_inputs=payload)
        history.trim_logs(self.records, 0, 0)
        self.assertEqual(len(self.records), 8)
        counts = history.history_counts(self.records)
        self.assertEqual(counts, dict(log=0, input_backup=1, retained=7))
        self.assertEqual(history.clear_history(self.records, 'log'), 0)
        self.assertEqual(history.clear_history(self.records, 'input_backup'), 1)
        self.assertEqual(len(self.records), 7)
        self.assertIs(self.records['previous_tglf_files']['previous_tglf_files'], payload)

    def test_same_input_handoff_does_not_duplicate_or_create_history(self):
        path = ('CGYRO_scan', 'INPUTS', 'input.cgyro')
        current = CgyroInput(N_THETA=32, HIPREC_FLAG=1)
        self.root['CGYRO_scan']['INPUTS']['input.cgyro'] = current
        self.root['CGYRO_scan']['RUN_DB'] = Unreadable()
        with patch.object(CgyroInput, 'duplicate', side_effect=AssertionError('unchanged input copied')):
            self.actions.replace('same', [(path, CgyroInput(current))])
        self.assertEqual(self.records, {})
        self.assertIs(self.root['CGYRO_scan']['INPUTS']['input.cgyro'], current)

    def test_changed_input_is_independent_and_only_changed_destinations_archived(self):
        inputs = self.root['CGYRO_scan']['INPUTS']
        inputs.update(one=CgyroInput(N_THETA=32), two=CgyroInput(N_THETA=48))
        original = inputs['one']
        one, two = [('CGYRO_scan', 'INPUTS', key) for key in ('one', 'two')]
        self.actions.replace('change', [(one, CgyroInput(N_THETA=64)), (two, CgyroInput(N_THETA=48))])
        record = list(self.records.values())[-1]
        self.assertEqual(len(record['previous_inputs']), 1)
        self.assertEqual(len(record['destinations']), 1)
        original['N_THETA'] = 24
        self.assertEqual(list(record['previous_inputs'].values())[0]['N_THETA'], 32)
        reopened = json.loads(json.dumps(self.records))
        history.trim_logs(reopened, 0, 0)
        self.assertEqual(reopened, self.records)

    def profile_source(self):
        source = CgyroInput(rho=[0., .5, 1.])
        self.root['Transfer_tool']['Transfer_file']['input.gacode'] = source
        self.actions.settings['transfer_source'] = json.dumps(['Transfer_tool', 'Transfer_file', 'input.gacode'])
        profiles = self.root['TGLF_scan']['TGYRO']['PROFILES_GEN']
        for group in ('INPUTS', 'OUTPUTS'):
            for name in ('input.gacode', 'input.gacode_base'):
                profiles[group][name] = CgyroInput(copy.deepcopy(source))
        return source, profiles

    def test_identical_profile_handoff_preserves_all_result_and_cache_references(self):
        source, profiles = self.profile_source()
        scan = self.root['TGLF_scan']
        keys = ('input.tglf', 'scanResults', 'scanResults_spectra', 'scanResults2D',
                'scanResults2D_spectra', 'scanResults3D', 'scanResults3D_spectra', '_workbench_index')
        saved = {key: Unreadable() for key in keys}
        scan.update(saved)
        before = copy.deepcopy(profiles['SETTINGS'])
        with patch.object(CgyroInput, 'duplicate', side_effect=AssertionError('same profile copied')):
            self.actions.handoff('profiles')
            self.actions.handoff('profiles')
        self.assertEqual(self.records, {})
        self.assertEqual(profiles['SETTINGS'], before)
        for key in keys:
            self.assertIs(scan[key], saved[key])

    def test_changed_profile_backup_failure_keeps_inputs_and_active_results(self):
        source, profiles = self.profile_source()
        previous = copy.deepcopy(profiles['INPUTS'])
        source['rho'] = [0., .6, 1.]
        payload = Unreadable()
        self.root['TGLF_scan']['scanResults'] = payload
        with self.assertRaisesRegex(AssertionError, 'payload was copied'):
            self.actions.handoff('profiles')
        self.assertEqual(profiles['INPUTS'], previous)
        self.assertIs(self.root['TGLF_scan']['scanResults'], payload)
        self.assertEqual(self.records, {})

    def test_changed_profile_preserves_spectra_and_multidimensional_results(self):
        source, profiles = self.profile_source()
        source['rho'] = [0., .6, 1.]
        scan = self.root['TGLF_scan']
        saved = {key: {'point': [1, 2]} for key in ('scanResults', 'scanResults_spectra',
                    'scanResults2D', 'scanResults2D_spectra', 'scanResults3D', 'scanResults3D_spectra')}
        scan.update(copy.deepcopy(saved))
        self.actions.handoff('profiles')
        self.assertEqual(len(self.records), 1)
        record = next(iter(self.records.values()))
        self.assertEqual({key: record['tglf_data'][key] for key in saved}, saved)
        self.assertEqual(len(record['previous_inputs']), 4)
        self.assertTrue(all(key not in scan for key in saved))
        self.assertEqual(profiles['INPUTS']['input.gacode']['rho'], [0., .6, 1.])

    def test_log_retention_uses_creation_time_after_tree_is_sorted(self):
        records = {
            '20261030T010000_00000000': dict(status='returned', created='2026-10-30T01:00:00.900000+00:00', title='newer'),
            '20261030T010000_ffffffff': dict(status='returned', created='2026-10-30T01:00:00.100000+00:00', title='older'),
        }
        history.trim_logs(records, normal_limit=1)
        self.assertEqual([row['title'] for row in records.values()], ['newer'])

    def test_failed_copy_leaves_all_current_inputs_intact(self):
        inputs = self.root['CGYRO_scan']['INPUTS']
        inputs.update(one=CgyroInput(N_THETA=32), two=CgyroInput(N_THETA=48))
        before = copy.deepcopy(inputs)
        class BadInput(CgyroInput):
            def duplicate(self):
                raise OSError('copy failed')
        with self.assertRaises(OSError):
            self.actions.replace('change', [(('CGYRO_scan', 'INPUTS', 'one'), CgyroInput(N_THETA=64)),
                                            (('CGYRO_scan', 'INPUTS', 'two'), BadInput(N_THETA=64))])
        self.assertEqual(inputs, before)
        self.assertEqual(self.records, {})

    def test_history_render_does_not_inspect_payload_or_refresh_whole_tree(self):
        self.records['backup'] = dict(title='backup', created='today', status='archived', previous_inputs=Unreadable())
        buttons = []
        class UI:
            def Button(self, *args, **kwargs):
                buttons.append(kwargs)
            def Separator(self, *args):
                pass
        host = type('Host', (), dict(root=self.root, ui=UI(), label=lambda *args: None,
                                    clear_input_history=lambda *args: None))()
        runtime_ui.RuntimePage.runtime_history(host)
        self.assertEqual(len(buttons), 2)
        self.assertTrue(all(b['updateGUI'] and not b['refresh_tree'] for b in buttons))
        self.assertTrue(all(b['refresh_scope'] == 'section' for b in buttons))


if __name__ == '__main__':
    unittest.main()
