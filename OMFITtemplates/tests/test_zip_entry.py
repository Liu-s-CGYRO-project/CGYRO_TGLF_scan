"""Native OMFIT entry discovery when generating a new project ZIP."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
from OMFITlib_template_archive import Project
from OMFITlib_template_service import apply_update, plan_update, publish
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

    def test_wrapped_old_project_generates_a_native_root_entry(self):
        fixture(self.source, prefix='工程/')
        release = publish(self.source, self.base / 'library',
            dict(id='demo', name='Demo', author='test', version='1'), ['Demo'])
        with zipfile.ZipFile(self.source) as archive:
            self.assertNotIn(native_entry(archive), archive.namelist())
        apply_update(plan_update(self.source, release), self.output)
        self.assertNativeEntry(self.output)
        with Project(self.source) as source, Project(self.output) as result:
            self.assertEqual(result.prefix, '')
            self.assertEqual(source.read('Demo/data/v1.npy'), result.read('Demo/data/v1.npy'))

    def test_regenerate_unloadable_zip_preserves_data_settings_and_original(self):
        before = self.source.read_bytes()
        release = publish(self.source, self.base / 'library',
            dict(id='demo', name='Demo', author='test', version='1'), ['Demo'])
        apply_update(plan_update(self.source, release), self.output)
        again = self.base / 'again.zip'
        apply_update(plan_update(self.output, release), again)
        self.assertNativeEntry(again)
        with Project(self.source) as source, Project(again) as result:
            for name in ('Demo/data/v1.npy', 'Demo/SettingsNamelist.txt', 'MainSettingsNamelist.txt'):
                self.assertEqual(source.read(name), result.read(name))
        self.assertEqual(self.source.read_bytes(), before)

    def test_generated_zip64_archive_keeps_native_entry_and_results(self):
        with patch('zipfile.ZIP64_LIMIT', 1024), patch('zipfile.ZIP_FILECOUNT_LIMIT', 3):
            fixture(self.source)
            release = publish(self.source, self.base / 'library',
                dict(id='demo', name='Demo', author='test', version='1'), ['Demo'])
            apply_update(plan_update(self.source, release), self.output)
            self.assertNativeEntry(self.output)
            with Project(self.source) as source, Project(self.output) as result:
                self.assertEqual(source.read('Demo/data/v1.npy'), result.read('Demo/data/v1.npy'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
