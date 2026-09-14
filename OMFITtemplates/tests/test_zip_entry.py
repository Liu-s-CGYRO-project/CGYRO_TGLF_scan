"""Native OMFIT entry discovery and lossless repair of old generated ZIPs."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
from OMFITlib_template_archive import Project, TemplateError
from OMFITlib_template_service import Cancelled, apply_update, plan_update, publish, repair_project
from test_templates import fixture


def native_entry(archive):
    # OMFIT omfit_base.cherry_pick_OMFITsave uses this first-member rule,
    # unlike the manager's order-independent input parser.
    directory = archive.namelist()[0].rpartition('/')[0]
    return (directory + '/' if directory else '') + 'OMFITsave.txt'


class ZipEntryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / 'broken.zip'
        fixture(self.source)
        self.output = self.base / 'fixed.zip'

    def assertNativeEntry(self, filename):
        with zipfile.ZipFile(filename) as archive:
            self.assertTrue(archive.read(native_entry(archive)))
            self.assertEqual(archive.infolist()[0].filename, native_entry(archive))
            # OMFITproject.info uses commonprefix across all raw entry names.
            prefix = os.path.commonprefix(archive.namelist())
            self.assertTrue(archive.read(prefix + 'OMFITsave.txt'))
            self.assertTrue(archive.read(prefix + 'MainSettingsNamelist.txt'))

    def test_update_both_data_policies_load_from_root_not_case_directory(self):
        # Ensure a retained case is lexically first, matching the user's error.
        with zipfile.ZipFile(self.source, 'a') as archive:
            archive.writestr('CGYRO/Cases/lincgyro/BETAE_UNIT~0.00010~ky~0.10000/out.cgyro.freq', b'USER RESULT')
        release = publish(self.source, self.base / 'library',
            dict(id='demo', name='Demo', author='test', version='1'), ['Demo'], include_examples=True)
        for policy in ('keep', 'examples'):
            with self.subTest(policy=policy):
                output = self.base / (policy + '.zip')
                apply_update(plan_update(self.source, release, data_policy=policy), output)
                self.assertNativeEntry(output)
                with zipfile.ZipFile(output) as archive:
                    self.assertEqual(archive.read('CGYRO/Cases/lincgyro/BETAE_UNIT~0.00010~ky~0.10000/out.cgyro.freq'), b'USER RESULT')

    def test_repair_preserves_all_contents_directories_metadata_and_source(self):
        with zipfile.ZipFile(self.source, 'a') as archive:
            archive.comment = b'original project comment'
            info = zipfile.ZipInfo('Demo/data/run.sh', date_time=(2026, 9, 14, 10, 20, 30))
            info.external_attr = 0o100755 << 16
            info.comment = b'result-associated script'
            archive.writestr(info, b'#!/bin/sh\n# saved task, never execute\n')
        before = self.source.read_bytes()
        with zipfile.ZipFile(self.source) as archive:
            self.assertNotIn(native_entry(archive), archive.namelist())
        progress = []
        repair_project(self.source, self.output, progress=lambda *args: progress.append(args))
        self.assertNativeEntry(self.output)
        self.assertEqual(self.source.read_bytes(), before)
        with zipfile.ZipFile(self.source) as original, zipfile.ZipFile(self.output) as repaired:
            self.assertEqual(set(original.namelist()), set(repaired.namelist()))
            self.assertEqual(original.comment, repaired.comment)
            for info in original.infolist():
                self.assertEqual(original.read(info), repaired.read(info.filename))
                copied = repaired.getinfo(info.filename)
                for attr in ('date_time', 'external_attr', 'internal_attr', 'create_system', 'comment', 'compress_type'):
                    self.assertEqual(getattr(info, attr), getattr(copied, attr), (info.filename, attr))
        self.assertEqual(progress[-1][1], progress[-1][2])
        self.assertTrue(any('校验' in item[0] for item in progress))

    def test_repair_single_wrapper_and_native_dot_directory_entries(self):
        fixture(self.source, prefix='工程/')
        with zipfile.ZipFile(self.source, 'a') as archive:
            archive.writestr('工程/', b'')
            archive.writestr('./工程/empty/', b'')
        repair_project(self.source, self.output)
        self.assertNativeEntry(self.output)
        with zipfile.ZipFile(self.output) as archive:
            self.assertEqual(archive.namelist()[0], 'OMFITsave.txt')
            self.assertIn('empty/', archive.namelist())
        with Project(self.source) as source, Project(self.output) as result:
            for name in source.files:
                self.assertEqual(source.read(name), result.read(name))

    def test_repair_zip64_sizes_and_directory_count(self):
        with patch('zipfile.ZIP64_LIMIT', 1024), patch('zipfile.ZIP_FILECOUNT_LIMIT', 3):
            fixture(self.source)
            repair_project(self.source, self.output)
            self.assertNativeEntry(self.output)
            with zipfile.ZipFile(self.source) as source, zipfile.ZipFile(self.output) as result:
                self.assertEqual(source.read('Demo/data/v1.npy'), result.read('Demo/data/v1.npy'))

    def test_repair_refuses_source_and_existing_outputs(self):
        before = self.source.read_bytes()
        self.output.write_bytes(b'EXISTING')
        for output in (self.source, self.output, self.base / 'invalid.txt'):
            with self.subTest(output=output), self.assertRaises(TemplateError):
                repair_project(self.source, output)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.output.read_bytes(), b'EXISTING')
        self.assertFalse(list(self.base.glob('*.partial')))

    def test_cancel_copy_and_verification_leave_no_output(self):
        before = self.source.read_bytes()
        for stage in ('修复', '校验'):
            with self.subTest(stage=stage):
                cancel = threading.Event()
                def progress(label, done, total):
                    if stage in label:
                        cancel.set()
                with self.assertRaises(Cancelled):
                    repair_project(self.source, self.output, progress=progress, cancel=cancel)
                self.assertFalse(self.output.exists())
                self.assertFalse(list(self.base.glob('*.partial')))
        self.assertEqual(self.source.read_bytes(), before)

    def test_corrupt_result_crc_aborts_repair(self):
        with zipfile.ZipFile(self.source, 'a') as archive:
            archive.writestr('Demo/data/corrupt.dat', b'ORIGINAL', compress_type=zipfile.ZIP_STORED)
            info = archive.getinfo('Demo/data/corrupt.dat')
        with self.source.open('r+b') as stream:
            stream.seek(info.header_offset + 30 + len(info.filename.encode()) + len(info.extra))
            stream.write(b'X')
        before = self.source.read_bytes()
        with self.assertRaises(zipfile.BadZipFile):
            repair_project(self.source, self.output)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.base.glob('*.partial')))

    def test_source_change_during_repair_aborts_publication(self):
        before = self.source.stat()
        def progress(*args):
            os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000000))
        with self.assertRaisesRegex(TemplateError, '源文件发生变化'):
            repair_project(self.source, self.output, progress=progress)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.base.glob('*.partial')))

    def test_read_back_hash_failure_aborts_publication(self):
        with patch.object(Project, 'digest', return_value='incorrect'):
            with self.assertRaisesRegex(TemplateError, '内容校验失败'):
                repair_project(self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.base.glob('*.partial')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
