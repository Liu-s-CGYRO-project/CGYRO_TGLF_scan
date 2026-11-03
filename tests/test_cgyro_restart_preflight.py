"""Optional performance logs must not gate real checkpoint continuation."""
import ast
import copy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import test_checkpoint_resources as fixtures
import OMFITlib_cgyro_restart_preflight as preflight
import OMFITlib_cgyro_run_state as run_state

REPO = Path(__file__).resolve().parents[1]
DEBUG_TIMING = 'out.cgyro.timing.debug'


class RestartPreflightTests(unittest.TestCase):
    def setUp(self):
        self.files = fixtures.ResourceContinuationTests('runTest')
        self.files.setUp()
        self.addCleanup(self.files.doCleanups)
        self.directory = self.files.original
        self.cache = {}
        self.args = (self.files.current, object(), 'cluster', '/work', '', self.cache)

    def prepare(self):
        # Exercise the names retained for already-loaded submission scripts,
        # then the same physical input/checkpoint checks used by new scripts.
        self.files.plan['points'] = ['p000001']
        with patch.object(run_state, 'native_remote_execute', side_effect=AssertionError('remote query')):
            preflight.filter_restart_points(self.files.plan, *self.args)
            preflight.check_debug_history(str(self.directory), 'p000001', *self.args)
            result = self.files.prepare()
        self.assertEqual(self.cache, {})
        self.files.unchanged()
        return result

    def test_missing_debug_log_stages_verified_checkpoint_without_synthetic_history(self):
        current, metadata, names = self.prepare()
        self.assertEqual(current['MAX_TIME'], 1.)
        self.assertEqual(metadata['continuation']['checkpoint']['time'], .3)
        self.assertIn('out.cgyro.timing', names)
        self.assertNotIn(DEBUG_TIMING, names)
        self.assertFalse((self.files.base / 'stage' / DEBUG_TIMING).exists())

    def test_empty_debug_log_does_not_reject_or_invent_timer_rows(self):
        (self.directory / DEBUG_TIMING).write_bytes(b'')
        self.files.before[DEBUG_TIMING] = b''
        _, metadata, names = self.prepare()
        self.assertEqual(metadata['continuation']['checkpoint']['time'], .3)
        self.assertIn(DEBUG_TIMING, names)
        self.assertEqual((self.files.base / 'stage' / DEBUG_TIMING).read_bytes(), b'')

    def test_existing_debug_log_is_preserved_byte_for_byte(self):
        content = b'# timer columns\n1.0 2.0 3.0\n'
        (self.directory / DEBUG_TIMING).write_bytes(content)
        self.files.before[DEBUG_TIMING] = content
        _, _, names = self.prepare()
        self.assertIn(DEBUG_TIMING, names)
        self.assertEqual((self.files.base / 'stage' / DEBUG_TIMING).read_bytes(), content)

    def test_checkpoint_zip_without_debug_log_stages_without_modifying_archive(self):
        path = self.files.base / 'point.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for name, value in self.files.before.items():
                archive.writestr(name, value)
        original = path.read_bytes()
        self.files.plan['sources']['p000001'] = dict(mode='checkpoint_zip', zip=str(path),
            sha256={name: hashlib.sha256(value).hexdigest() for name, value in self.files.before.items()})
        _, metadata, names = self.prepare()
        self.assertEqual(metadata['continuation']['checkpoint']['time'], .3)
        self.assertNotIn(DEBUG_TIMING, names)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.files.base / 'stage' / DEBUG_TIMING).exists())

    def test_legacy_compatibility_calls_do_not_read_archives_or_alter_selection(self):
        plan = dict(points=['one', 'two'], sources={
            'one': dict(mode='checkpoint', directory='/not-opened'),
            'two': dict(mode='checkpoint_zip', zip='/not-opened.zip'),
            'unselected': dict(mode='checkpoint_zip', zip='/unselected.zip')},
            scope={'planned': ['one', 'two', 'unselected']})
        original = copy.deepcopy(plan)
        with patch.object(run_state, 'native_remote_execute', side_effect=AssertionError('remote query')), \
                patch('builtins.open', side_effect=AssertionError('file read')), \
                patch.object(zipfile, 'ZipFile', side_effect=AssertionError('archive read')):
            self.assertIs(preflight.filter_restart_points(plan, *self.args), plan)
            preflight.check_debug_history('/not-opened', 'one', *self.args)
        self.assertEqual(plan, original)
        self.assertEqual(self.cache, {})

    def test_missing_standard_timing_still_rejects_selected_checkpoint(self):
        (self.directory / 'out.cgyro.timing').unlink()
        self.files.before.pop('out.cgyro.timing')
        with self.assertRaisesRegex(ValueError, 'out.cgyro.timing'):
            self.prepare()
        self.files.unchanged()

    def test_submission_and_collection_do_not_require_retired_debug_log(self):
        script_dir = REPO / 'CGYRO_TGLF_scan/CGYRO_scan/SCRIPTS'
        tree = ast.parse((script_dir / 'subscan_lin.py').read_text(encoding='utf-8'))
        self.assertFalse(any(isinstance(node, ast.ImportFrom) and
                             node.module == 'OMFITlib_cgyro_restart_preflight' for node in ast.walk(tree)))
        self.assertFalse(any(isinstance(node, ast.Name) and node.id in
                             ('check_debug_history', 'filter_restart_points') for node in ast.walk(tree)))
        downsync = ast.parse((script_dir / 'downsync.py').read_text(encoding='utf-8'))
        extras = next(ast.literal_eval(node.value) for node in ast.walk(downsync)
                      if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and
                          target.id == 'restart_extra_files' for target in node.targets))
        self.assertNotIn(DEBUG_TIMING, extras)


if __name__ == '__main__':
    unittest.main()
