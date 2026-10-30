"""Wait retries preserve exact job identity and require verified terminal states."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_cgyro_storage as fixtures
import OMFITlib_cgyro_retry as retry_api
import OMFITlib_tk_callbacks as callbacks

queue = fixtures.queue_api


class QueueWaitTests(unittest.TestCase):
    def setUp(self):
        self.manifest = dict(run_token='token', job_id='123', server='cluster', workDir='/run', status='cancel_requested')
        self.root = {'RUN_MANIFEST': self.manifest}
        self.ui = SimpleNamespace()
        self.wait = patch.object(callbacks.RetryWait, 'wait').start()
        self.addCleanup(patch.stopall)

    def test_terminal_required_after_polling(self):
        with patch.object(queue, 'refresh_run_state', side_effect=[{'terminal': False}, {'terminal': True}]) as query:
            queue.wait_for_stop(self.root, self.ui)
        self.assertEqual(query.call_count, 2)
        self.assertEqual(self.wait.call_count, 1)
        self.assertNotIn('wait_completed', self.manifest)

    def test_empty_or_pending_status_never_infers_completion(self):
        with patch.object(queue, 'refresh_run_state', return_value={'terminal': False}), patch.object(queue, 'STOP_POLL_ATTEMPTS', 3):
            with self.assertRaisesRegex(RuntimeError, 'still settling'):
                queue.wait_for_stop(self.root, self.ui)
        self.assertEqual(self.wait.call_count, 2)
        self.assertEqual(self.manifest['status'], 'cancel_requested')

    def test_consecutive_errors_include_all_three_causes(self):
        with patch.object(queue, 'refresh_run_state', side_effect=[OSError('first'), OSError('second'), OSError('third')]):
            with self.assertRaisesRegex(RuntimeError, 'first\nsecond\nthird'):
                queue.wait_for_stop(self.root, self.ui)

    def test_cancel_leaves_job_recoverable(self):
        self.wait.side_effect = KeyboardInterrupt('stop waiting')
        with patch.object(queue, 'refresh_run_state', return_value={'terminal': False}):
            with self.assertRaises(KeyboardInterrupt):
                queue.wait_for_stop(self.root, self.ui)
        self.assertEqual(self.manifest['job_id'], '123')
        self.assertEqual(self.manifest['status'], 'cancel_requested')

    def test_reentrant_job_change_prevents_next_query(self):
        self.wait.side_effect = lambda *args: self.manifest.update(job_id='456')
        with patch.object(queue, 'refresh_run_state', return_value={'terminal': False}) as query:
            with self.assertRaisesRegex(RuntimeError, 'job changed'):
                queue.wait_for_stop(self.root, self.ui)
        self.assertEqual(query.call_count, 1)

    def test_replaced_manifest_prevents_receipt_recovery_from_new_job(self):
        self.manifest.update(scheduler='slurm', submit_output='')
        self.wait.side_effect = lambda *args: self.root.update(RUN_MANIFEST=dict(self.manifest, job_id='456'))
        with patch.object(retry_api, 'save_current'), patch.object(retry_api, 'native_remote_execute', return_value=1) as query:
            with self.assertRaisesRegex(RuntimeError, 'job changed'):
                retry_api.recover_submission(self.root, self.ui)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(self.root['RUN_MANIFEST']['job_id'], '456')

    def test_network_retry_uses_wait_and_never_submits(self):
        self.manifest.update(scheduler='slurm', submit_output='')
        def receipt(*args, **kwargs):
            kwargs['std_out'].append('Submitted batch job 123')
            return 0
        with patch.object(retry_api, 'save_current'), patch.object(retry_api, 'native_remote_execute') as query:
            query.side_effect = lambda *args, **kwargs: 1 if query.call_count == 1 else receipt(*args, **kwargs)
            self.assertTrue(retry_api.recover_submission(self.root, self.ui))
        self.assertEqual(query.call_count, 2)
        self.assertEqual(self.wait.call_count, 1)
        self.assertEqual(self.manifest['job_id'], '123')

    def test_cancel_during_partial_collection_keeps_verified_points(self):
        def download():
            self.manifest.update(load_errors={'bad': 'truncated'}, loaded_points=['good'], partial_points=[])
            raise RuntimeError('unreadable neighbor')
        self.root['SCRIPTS'] = {'downsync.py': SimpleNamespace(run=download)}
        self.wait.side_effect = KeyboardInterrupt('stop waiting')
        with patch.object(retry_api, 'require_retained_run'), patch.object(retry_api, 'save_current'), \
                patch.object(retry_api, 'collected_points', return_value={'good'}), \
                patch.object(retry_api, 'submit_retry', side_effect=AssertionError('solver retry')):
            with self.assertRaises(KeyboardInterrupt):
                retry_api.collect_current(self.root, self.ui, dict, None, None)
        self.assertEqual(self.manifest['loaded_points'], ['good'])
        self.assertEqual(self.manifest['job_id'], '123')

    def test_network_retry_restores_previous_collection_before_waiting(self):
        self.manifest.update(collection_status='complete', loaded_points=['old'])
        def download():
            self.manifest['loaded_points'] = []
            raise RuntimeError('network failed')
        self.root['SCRIPTS'] = {'downsync.py': SimpleNamespace(run=download)}
        def stop_waiting(*args):
            self.assertEqual(self.manifest['loaded_points'], ['old'])
            raise KeyboardInterrupt('stop waiting')
        self.wait.side_effect = stop_waiting
        with patch.object(retry_api, 'require_retained_run'), patch.object(retry_api, 'save_current'), \
                patch.object(retry_api, 'collection_done', return_value=True), \
                patch.object(retry_api, 'run_cases', return_value={}), patch.object(retry_api, 'set_run_cases'):
            with self.assertRaises(KeyboardInterrupt):
                retry_api.collect_current(self.root, self.ui, dict, None, None)
        self.assertEqual(self.manifest['loaded_points'], ['old'])


if __name__ == '__main__':
    unittest.main()
