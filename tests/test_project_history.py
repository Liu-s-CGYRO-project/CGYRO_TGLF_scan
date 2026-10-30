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
