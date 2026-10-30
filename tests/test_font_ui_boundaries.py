"""Font settings stay cheap; actual use retains verification in a worker."""
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import tkinter as tk
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import OMFITlib_font_cache as cache
import OMFITlib_font_download_ui as download
import OMFITlib_font_ui as settings


class FontCacheBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.scope = ExitStack()
        self.addCleanup(self.scope.close)
        folder = self.scope.enter_context(tempfile.TemporaryDirectory())
        self.data = b'local test font'
        self.scope.enter_context(patch.object(cache, '_directory', Path(folder)))
        self.scope.enter_context(patch.object(cache, '_checked', {}))
        self.scope.enter_context(patch.object(cache, 'FONT_FILES', {
            'font.ttf': {'bytes': len(self.data), 'sha256': hashlib.sha256(self.data).hexdigest()}}))
        self.scope.enter_context(patch.object(cache, 'FONT_BUNDLES', {
            'gui': {'fonts': ['font.ttf']}, 'plot': {'fonts': ['font.ttf']}}))
        self.path = cache._font_path('font.ttf')
        self.path.write_bytes(self.data)

    def test_fast_lookup_does_not_validate_unverified_files(self):
        with patch.object(cache, '_hash_file', side_effect=AssertionError('UI hashed font')):
            self.assertIsNone(cache.cached_fonts('gui', verify=False))
            self.assertEqual(cache.font_cache_status('gui'), 'on disk; checked when used')
            self.assertEqual(cache._checked, {})

    def test_verified_stat_cache_is_reused_and_changed_file_is_rechecked(self):
        with patch.object(cache, '_hash_file', wraps=cache._hash_file) as digest:
            self.assertIsNotNone(cache.cached_fonts('gui'))
            self.assertIsNotNone(cache.cached_fonts('gui', verify=False))
            self.assertEqual(cache.font_cache_status('gui'), 'verified')
            self.assertEqual(digest.call_count, 1)
            previous = self.path.stat()
            self.path.write_bytes(b'x' * len(self.data))
            os.utime(self.path, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1000000000))
            self.assertIsNone(cache.cached_fonts('gui', verify=False))
            self.assertEqual(digest.call_count, 1)
            self.assertIsNone(cache.cached_fonts('gui'))
            self.assertEqual(digest.call_count, 2)

    def tk_root(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest('Tk display required: ' + str(error))
        root.withdraw()
        root._project_cjk_size = 11
        self.addCleanup(root.destroy)
        return root

    def test_unbind_removes_only_selected_callback_on_legacy_tk(self):
        from OMFITlib_gui_fonts import unbind_callback
        root = self.tk_root()
        root.deiconify()
        root.update()
        calls = []
        first = root.bind('<<BoundaryTest>>', lambda event: calls.append('first'), add='+')
        second = root.bind('<<BoundaryTest>>', lambda event: calls.append('second'), add='+')
        root.bind('<<BoundaryTest>>', lambda event: calls.append('third'), add='+')
        with patch.object(root, 'unbind', side_effect=AssertionError('legacy unbind clears all handlers')):
            unbind_callback(root, '<<BoundaryTest>>', second)
        root.event_generate('<<BoundaryTest>>')
        self.assertEqual(calls, ['first', 'third'])
        self.assertIn(first, root.bind('<<BoundaryTest>>'))
        self.assertNotIn(second, root.tk.call('info', 'commands'))

    def test_open_settings_neither_hashes_nor_walks_other_windows(self):
        root = self.tk_root()
        with patch.object(cache, '_hash_file', side_effect=AssertionError('UI hashed font')), \
                patch.object(settings, 'refresh_window_fonts', side_effect=AssertionError('global font refresh')):
            dialog = settings.open_font_manager(root)
            self.assertTrue(dialog.winfo_exists())
            self.assertEqual(cache._checked, {})
            dialog.destroy()

    def test_uncached_verification_runs_in_dialog_worker(self):
        root = self.tk_root()
        threads = []
        def verify(kind, **kwargs):
            threads.append(threading.get_ident())
            return cache.cached_fonts(kind)
        with patch.object(download, 'ensure_cached_fonts', side_effect=verify), \
                patch.object(cache, '_hash_file', wraps=cache._hash_file) as digest:
            result = download.ensure_fonts('gui', parent=root)
            self.assertEqual(result['font.ttf'], str(self.path))
            self.assertEqual(digest.call_count, 1)
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0], threading.get_ident())

    def test_standalone_and_project_font_libraries_remain_identical(self):
        for name in ('font_cache', 'font_download_ui', 'font_ui', 'gui_fonts', 'tk_callbacks'):
            filename = 'OMFITlib_' + name + '.py'
            self.assertEqual((REPO / 'CGYRO_TGLF_scan/LIB' / filename).read_bytes(),
                             (REPO / 'OMFITtemplates/LIB' / filename).read_bytes(), filename)


if __name__ == '__main__':
    unittest.main()
