"""Numerical and installation boundaries for the old pygacode precision fix."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import repair_pygacode_hiprec as repair


# A small legacy-protocol fixture; integration against the SHA-pinned upstream
# reader is a separate validation, not replaced by this stand-in.
LEGACY = '''import os
import numpy as np
BYTE='float32'
class cgyrodata:
   def __init__(self,sim_directory):
      self.dir = sim_directory
   def extract(self,f):
      if os.path.isfile(self.dir+'bin'+f):
         return 'time','bin',np.fromfile(self.dir+'bin'+f,dtype=BYTE)
      if os.path.isfile(self.dir+'out'+f):
         return 'time','out',np.fromfile(self.dir+'out'+f,dtype='float',sep=' ')
      return 'time','null',[]
'''.encode()


class HiprecRepairTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / 'data.py'
        self.source.write_bytes(LEGACY)
        target = patch.object(repair, 'LEGACY_SHA256', hashlib.sha256(LEGACY).hexdigest())
        target.start()
        self.addCleanup(target.stop)
        self.namespace = {}
        exec(compile(repair.patched_source(LEGACY), '<fixture>', 'exec'), self.namespace)

    def case(self, name, flag, dtype):
        directory = self.root / name
        directory.mkdir()
        if flag is not None:
            (directory / 'input.cgyro.gen').write_text(flag)
        # Include noninteger values that would be corrupted by byte reinterpretation.
        flux = (np.arange(2 * 3 * 3 * 1 * 4, dtype=np.float64) * 0.03125 - 0.75).reshape((2, 3, 3, 1, 4), order='F')
        field = np.linspace(-2.5, 3.75, 2 * 8 * 4).reshape((2, 8, 4), order='F')
        flux.astype(dtype).ravel(order='F').tofile(directory / 'bin.cgyro.ky_flux')
        field.astype(dtype).ravel(order='F').tofile(directory / 'bin.cgyro.phib')
        return directory, flux.astype(dtype), field.astype(dtype)

    def reader(self, directory):
        return self.namespace['cgyrodata'](str(directory) + os.sep)

    def assert_case(self, reader, flux, field):
        actual = reader.extract('.cgyro.ky_flux')[2]
        self.assertEqual(actual.size // (2 * 3 * 1 * 4), 3)
        self.assertEqual(actual.dtype, flux.dtype)
        np.testing.assert_array_equal(actual.reshape(flux.shape, order='F'), flux)
        actual_field = reader.extract('.cgyro.phib')[2].reshape(field.shape, order='F')
        np.testing.assert_array_equal(actual_field[0] + 1j * actual_field[1], field[0] + 1j * field[1])

    def test_single_and_double_readers_can_be_interleaved(self):
        first = self.case('double', '1 HIPREC_FLAG\n', 'float64')
        second = self.case('single', '0 HIPREC_FLAG\n', 'float32')
        reader1, reader2 = self.reader(first[0]), self.reader(second[0])
        self.assert_case(reader1, *first[1:])
        self.assert_case(reader2, *second[1:])
        self.assert_case(reader1, *first[1:])
        self.assertEqual(self.namespace['BYTE'], 'float32')

    def test_old_generated_input_without_flag_remains_single_precision(self):
        directory, flux, field = self.case('old', '0 NONLINEAR_FLAG\n', 'float32')
        self.assert_case(self.reader(directory), flux, field)

    def test_legacy_directory_without_generated_input_remains_single_precision(self):
        directory, flux, field = self.case('no_gen', None, 'float32')
        self.assert_case(self.reader(directory), flux, field)

    def test_ascii_and_missing_outputs_keep_original_protocol(self):
        directory, _, _ = self.case('text', '1 HIPREC_FLAG\n', 'float64')
        (directory / 'out.cgyro.freq').write_text('0.125 0.375\n')
        reader = self.reader(directory)
        self.assertEqual(reader.extract('.cgyro.freq')[:2], ('time', 'out'))
        np.testing.assert_array_equal(reader.extract('.cgyro.freq')[2], [0.125, 0.375])
        self.assertEqual(reader.extract('.missing'), ('time', 'null', []))

    def test_generated_output_flag_takes_precedence_over_editable_input(self):
        directory, flux, field = self.case('edited_input', '1 HIPREC_FLAG # saved solver input\n', 'float64')
        (directory / 'input.cgyro').write_text('HIPREC_FLAG=0\n')
        (directory / 'out.cgyro.prec').write_text('0.001\n')
        self.assert_case(self.reader(directory), flux, field)

    def test_invalid_or_duplicate_flag_fails_before_any_binary_read(self):
        for index, value in enumerate(('2 HIPREC_FLAG\n', '0.5 HIPREC_FLAG\n', 'nan HIPREC_FLAG\n',
                                       'inf HIPREC_FLAG\n', 'x HIPREC_FLAG\n', 'HIPREC_FLAG = 1\n',
                                       '1 HIPREC_FLAG\n0 HIPREC_FLAG\n')):
            with self.subTest(value=value):
                directory, _, _ = self.case(str(index), value, 'float64')
                with patch.object(np, 'fromfile', side_effect=AssertionError('Binary read too early')):
                    with self.assertRaises(ValueError):
                        self.reader(directory)

    def test_reader_initialization_does_not_open_unselected_case(self):
        directory, _, _ = self.case('selected', '1 HIPREC_FLAG\n', 'float64')
        other, _, _ = self.case('unselected', 'bad HIPREC_FLAG\n', 'float64')
        original_open = open
        calls = []
        def bounded_open(path, *args, **kwargs):
            calls.append(Path(path))
            self.assertNotIn(other, Path(path).parents)
            return original_open(path, *args, **kwargs)
        with patch('builtins.open', side_effect=bounded_open):
            reader = self.reader(directory)
            reader.extract('.cgyro.phib')
            reader.extract('.cgyro.ky_flux')
        self.assertEqual(calls.count(directory / 'input.cgyro.gen'), 1)
        self.assertLessEqual(set(calls), {directory / name for name in
                                        ('input.cgyro.gen', 'bin.cgyro.phib', 'bin.cgyro.ky_flux')})

    def test_dry_run_is_non_mutating(self):
        result = repair.repair(self.source)
        self.assertEqual(result['status'], 'ready')
        self.assertIn('self.BYTE', result['diff'])
        self.assertEqual(list(self.root.iterdir()), [self.source])
        self.assertEqual(self.source.read_bytes(), LEGACY)

    def test_apply_saves_exact_original_and_is_idempotent(self):
        report = repair.repair(self.source, apply=True)
        self.assertEqual(report['status'], 'patched')
        self.assertEqual(Path(report['backup']).read_bytes(), LEGACY)
        expected = repair.patched_source(LEGACY)
        self.assertEqual(self.source.read_bytes(), expected)
        self.assertEqual(report['after_sha256'], hashlib.sha256(expected).hexdigest())
        self.assertEqual(repair.repair(self.source, apply=True)['status'], 'already_patched')

    def test_unknown_reader_is_not_modified(self):
        self.source.write_bytes(LEGACY + b'# local changes\n')
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            repair.repair(self.source, apply=True)
        self.assertEqual(self.source.read_bytes(), LEGACY + b'# local changes\n')

    def test_modified_backport_is_not_accepted_as_already_patched(self):
        self.source.write_bytes(repair.patched_source(LEGACY) + b'# local changes\n')
        with self.assertRaisesRegex(ValueError, 'Modified'):
            repair.repair(self.source, apply=True)

    def test_failed_replace_preserves_original_and_backup(self):
        with patch.object(repair.os, 'replace', side_effect=OSError('read only')):
            with self.assertRaises(OSError):
                repair.repair(self.source, apply=True)
        self.assertEqual(self.source.read_bytes(), LEGACY)
        self.assertEqual(len(list(self.root.iterdir())), 2)
        self.assertFalse(list(self.root.glob('.hiprec-*')))

    def test_conflicting_backup_does_not_replace_reader(self):
        self.source.with_name('data.py.before-hiprec-' + repair.LEGACY_SHA256[:12]).write_bytes(b'not the original')
        with self.assertRaisesRegex(ValueError, 'backup differs'):
            repair.repair(self.source, apply=True)
        self.assertEqual(self.source.read_bytes(), LEGACY)

    def test_concurrent_source_change_is_preserved(self):
        original_chmod = repair.os.chmod
        def concurrent_change(path, mode):
            original_chmod(path, mode)
            self.source.write_bytes(b'another update')
        with patch.object(repair.os, 'chmod', side_effect=concurrent_change):
            with self.assertRaisesRegex(ValueError, 'changed during preparation'):
                repair.repair(self.source, apply=True)
        self.assertEqual(self.source.read_bytes(), b'another update')

    def test_distribution_lookup_does_not_import_pygacode(self):
        package = SimpleNamespace(files=[Path('pygacode/cgyro/data.py')], locate_file=lambda path: self.root / path)
        with patch.object(repair.importlib.metadata, 'distribution', return_value=package):
            self.assertEqual(repair.installed_source(), self.root / 'pygacode/cgyro/data.py')


if __name__ == '__main__':
    unittest.main()
