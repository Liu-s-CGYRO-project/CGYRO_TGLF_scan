"""Build failures must not rewrite the reviewed source manifest."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_project as builder


class BuildManifestTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.output = self.root / 'release.zip'
        self.manifest = self.root / 'PROJECT_CONTENTS.json'
        self.original = b'{"version":"1.0.0","files":{"prior":"reviewed"}}'
        self.manifest.write_bytes(self.original)
        (self.root / 'OMFITsave.txt').write_text("['Demo'] <-:-:-> OMFITmodule <-:-:->  <-:-:-> {}\n", encoding='utf-8')
        (self.root / 'MainSettingsNamelist.txt').write_text('{}', encoding='utf-8')
        (self.root / 'OMFIT_COMPATIBILITY.md').write_text('Fixture', encoding='utf-8')
        for name in ('validate_gui_fonts', 'validate_plot_fonts', 'validate_library_imports',
                     'validate_workbench', 'validate_project_api'):
            item = patch.object(builder, name, return_value={})
            item.start()
            self.addCleanup(item.stop)
        item = patch.object(builder, 'ROOT', self.root)
        item.start()
        self.addCleanup(item.stop)

    def test_existing_output_leaves_source_manifest_unchanged(self):
        self.output.write_bytes(b'existing')
        with self.assertRaises(builder.TemplateError):
            builder.build(self.output)
        self.assertEqual(self.manifest.read_bytes(), self.original)
        self.assertEqual(self.output.read_bytes(), b'existing')

    def test_oversize_failure_leaves_source_manifest_unchanged(self):
        with patch.object(builder, 'MAX_PROJECT_PACKAGE_BYTES', 1):
            with self.assertRaises(builder.TemplateError):
                builder.build(self.output)
        self.assertEqual(self.manifest.read_bytes(), self.original)
        self.assertFalse(self.output.exists())

    def test_crc_failure_leaves_source_manifest_unchanged(self):
        with patch.object(zipfile.ZipFile, 'testzip', return_value='bad-file'):
            with self.assertRaises(builder.TemplateError):
                builder.build(self.output)
        self.assertEqual(self.manifest.read_bytes(), self.original)
        self.assertFalse(self.output.exists())

    def test_success_publishes_before_refreshing_source_manifest(self):
        refresh = builder._refresh_manifest
        observed = []
        def write(path, data):
            if path == self.manifest:
                observed.append(self.output.is_file())
            return refresh(path, data)
        with patch.object(builder, '_refresh_manifest', write):
            builder.build(self.output)
        self.assertEqual(observed, [True])
        with zipfile.ZipFile(self.output) as package:
            self.assertEqual(package.read('PROJECT_CONTENTS.json'), self.manifest.read_bytes())
        self.assertIn('OMFITsave.txt', json.loads(self.manifest.read_bytes())['files'])

    def test_manifest_refresh_failure_reports_already_published_package(self):
        with patch.object(builder.os, 'replace', side_effect=PermissionError('manifest locked')):
            with self.assertRaisesRegex(builder.TemplateError, str(self.output).replace('\\', '\\\\')):
                builder.build(self.output)
        self.assertTrue(self.output.is_file())
        self.assertEqual(self.manifest.read_bytes(), self.original)
        with zipfile.ZipFile(self.output) as package:
            self.assertIsNone(package.testzip())
        self.assertEqual(list(self.root.glob('.project-manifest-*')), [])

    def test_source_edit_between_hashing_and_zip_write_cannot_mismatch_manifest(self):
        source = self.root / 'OMFIT_COMPATIBILITY.md'
        captured = source.read_bytes()
        original = Path.read_bytes
        reads = []
        def edit_after_capture(path):
            data = original(path)
            if path == source:
                reads.append(data)
                path.write_bytes(b'edited while build was running')
            return data
        with patch.object(Path, 'read_bytes', edit_after_capture):
            builder.build(self.output)
        self.assertEqual(reads, [captured])
        with zipfile.ZipFile(self.output) as package:
            manifest = json.loads(package.read('PROJECT_CONTENTS.json'))
            self.assertEqual(package.read(source.name), captured)
            for name, digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256(package.read(name)).hexdigest(), digest, name)


if __name__ == '__main__':
    unittest.main()
