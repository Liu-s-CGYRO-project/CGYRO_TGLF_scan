"""Offline maintenance entry points and installer publication failure boundaries."""
import ast
import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import compact_cgyro_project as legacy_zip
import compact_commandbox as commandbox
import build_bootstrap
import build_deployer
import build_maintenance_commandbox
from OMFITlib_template_archive import TemplateError
from release_policy import MAX_MANAGER_BOOTSTRAP_BYTES


class MaintenanceToolsTests(unittest.TestCase):
    def test_legacy_zip_rejects_before_reading_or_writing_any_path(self):
        with patch('builtins.open', side_effect=AssertionError('Unexpected I/O')):
            with self.assertRaisesRegex(RuntimeError, 'retired'):
                legacy_zip.compact('source', 'output', 'code', 'report')

    def test_compatibility_entry_requires_complete_current_interfaces(self):
        for project in (None, {}, {'LIB': None}, {'LIB': {}, 'SCRIPTS': None}):
            with self.subTest(project=project):
                with self.assertRaisesRegex(RuntimeError, 'omfit-maintain-'):
                    commandbox.compact({'CGYRO_TGLF_scan': project})
        with self.assertRaises(RuntimeError):
            commandbox.compact(None)

    def ready(self, action):
        return {'CGYRO_TGLF_scan': {
            'LIB': {name: object() for name in ('OMFITlib_cgyro_reference', 'OMFITlib_cgyro_retention')},
            'SCRIPTS': {'compact_cgyro_storage': SimpleNamespace(run=action)},
        }}

    def test_compatibility_entry_delegates_exactly_once_without_network(self):
        calls = []
        def action():
            calls.append('native task')
            return {'retired_runs': []}
        self.assertEqual(commandbox.compact(self.ready(action), proxy='unused'), {'retired_runs': []})
        self.assertEqual(calls, ['native task'])

    def test_native_abort_is_not_swallowed(self):
        def action():
            raise KeyboardInterrupt('Abort')
        with self.assertRaises(KeyboardInterrupt):
            commandbox.compact(self.ready(action))

    def fixture(self, directory):
        package = directory / 'OMFIT_template_manager_9.8.7.omfit.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('OMFITtemplates/LIB/OMFITlib_template_versions.py', "MANAGER_VERSION = '9.8.7'\n")
        return package

    def generate(self, package, output):
        with patch.object(sys, 'argv', ['build_bootstrap', '--manager', str(package), '--output', str(output)]):
            with redirect_stdout(io.StringIO()):
                build_bootstrap.main()

    def project_fixture(self, directory, with_result=False):
        package = directory / 'CGYRO_TGLF_scan_code_only_9.8.7.zip'
        rows = "['CGYRO_TGLF_scan'] <-:-:-> OMFITmodule <-:-:->  <-:-:-> {}\n"
        rows += "['OMFITtemplates'] <-:-:-> OMFITmodule <-:-:->  <-:-:-> {}\n"
        if with_result:
            rows += "['CGYRO_TGLF_scan']['RUN_DB'] <-:-:-> OMFITascii <-:-:-> ./CGYRO_TGLF_scan/result.txt <-:-:-> {}\n"
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('OMFITsave.txt', rows)
            archive.writestr('PROJECT_CONTENTS.json', json.dumps({'version': '9.8.7'}))
            if with_result:
                archive.writestr('CGYRO_TGLF_scan/result.txt', b'calculation result')
        return package

    def template_fixture(self, directory):
        package = directory / 'tdxy-liu__cgyro-tglf__9.8.7.omfittpl.zip'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(dict(
                version='9.8.7', author='tdxy-liu', id='cgyro-tglf', examples=False)))
        return package

    def deploy(self, project, template, output):
        with patch.object(sys, 'argv', ['build_deployer', '--project', str(project),
                                       '--template', str(template), '--output', str(output)]):
            with redirect_stdout(io.StringIO()):
                build_deployer.main()

    def embedded(self, output, variable):
        tree = ast.parse(output.read_bytes())
        return next(ast.literal_eval(node.value) for node in tree.body
                    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == variable
                                                            for t in node.targets))

    def test_bootstrap_output_embeds_verified_identity_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            package, output = self.fixture(folder), folder / 'bootstrap.py'
            self.generate(package, output)
            source = output.read_bytes()
            self.assertNotIn(b'\r\n', source)
            tree = ast.parse(source)
            metadata = next(ast.literal_eval(node.value) for node in tree.body
                            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'MANAGER'
                                                                    for t in node.targets))
            self.assertEqual(metadata['bytes'], package.stat().st_size)
            self.assertEqual(metadata['version'], '9.8.7')
            with self.assertRaises(TemplateError):
                self.generate(package, output)
            self.assertEqual(output.read_bytes(), source)

    def test_interrupted_script_write_leaves_no_installer_or_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            package, output = self.fixture(folder), folder / 'bootstrap.py'
            original = Path.write_bytes
            def interrupted(path, data):
                original(path, data[:30])
                raise KeyboardInterrupt('disk write interrupted')
            with patch.object(Path, 'write_bytes', interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    self.generate(package, output)
            self.assertFalse(output.exists())
            self.assertEqual(list(folder.iterdir()), [package])

    def test_bootstrap_validates_captured_bytes_not_reopened_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            package, output = self.fixture(folder), folder / 'bootstrap.py'
            original = Path.read_bytes
            with patch.object(Path, 'read_bytes', lambda path: b'unverified snapshot' if path == package else original(path)):
                with self.assertRaises(zipfile.BadZipFile):
                    self.generate(package, output)
            self.assertFalse(output.exists())

    def test_deployer_validates_each_snapshot_and_embeds_matching_digest_with_lf(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            project, template = self.project_fixture(folder), self.template_fixture(folder)
            original = Path.read_bytes
            for index, changed in enumerate((project, template)):
                output = folder / ('invalid-' + str(index) + '.py')
                with self.subTest(input=changed.name):
                    with patch.object(Path, 'read_bytes', lambda path: b'unverified snapshot' if path == changed else original(path)):
                        with self.assertRaises(zipfile.BadZipFile):
                            self.deploy(project, template, output)
                    self.assertFalse(output.exists())
            captured = {path: original(path) for path in (project, template)}
            def replaced_after_read(path):
                data = original(path)
                if path in captured:
                    path.write_bytes(b'replaced input path')
                return data
            output = folder / 'deploy.py'
            with patch.object(Path, 'read_bytes', replaced_after_read):
                self.deploy(project, template, output)
            release = self.embedded(output, 'RELEASE')
            for kind, path in (('project', project), ('template', template)):
                self.assertEqual(release[kind]['sha256'], hashlib.sha256(captured[path]).hexdigest())
                self.assertEqual(release[kind]['bytes'], len(captured[path]))
            self.assertNotIn(b'\r\n', output.read_bytes())
            self.assertTrue(output.read_bytes().startswith(b'#!/usr/bin/env python3\n'))

    def test_maintenance_rejects_unverified_snapshot_even_if_path_is_clean(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            project = self.project_fixture(folder, with_result=True)
            result_snapshot = project.read_bytes()
            self.project_fixture(folder)
            original = Path.read_bytes
            for index, snapshot in enumerate((b'unverified snapshot', result_snapshot)):
                output = folder / ('invalid-' + str(index) + '.py')
                with self.subTest(snapshot=index):
                    with patch.object(Path, 'read_bytes', lambda path: snapshot if path == project else original(path)):
                        with self.assertRaises((ValueError, zipfile.BadZipFile)):
                            build_maintenance_commandbox.build(project, output)
                    self.assertFalse(output.exists())

    def test_maintenance_embeds_exact_verified_snapshot_with_lf(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            project, output = self.project_fixture(folder), folder / 'maintenance.py'
            captured = project.read_bytes()
            original = Path.read_bytes
            def replaced_after_read(path):
                data = original(path)
                if path == project:
                    path.write_bytes(b'replaced input path')
                return data
            with patch.object(Path, 'read_bytes', replaced_after_read):
                build_maintenance_commandbox.build(project, output)
            self.assertEqual(base64.b85decode(self.embedded(output, 'PAYLOAD')), captured)
            self.assertEqual(self.embedded(output, 'PACKAGE')['sha256'], hashlib.sha256(captured).hexdigest())
            self.assertNotIn(b'\r\n', output.read_bytes())

    def test_deployer_and_maintenance_interruptions_never_publish_partial_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            project, template = self.project_fixture(folder), self.template_fixture(folder)
            original = Path.write_bytes
            def interrupted(path, data):
                if path.suffix == '.partial':
                    original(path, data[:30])
                    raise KeyboardInterrupt('installer write interrupted')
                return original(path, data)
            for kind in ('deployer', 'maintenance'):
                output = folder / (kind + '.py')
                with self.subTest(kind=kind), patch.object(Path, 'write_bytes', interrupted):
                    with self.assertRaises(KeyboardInterrupt):
                        if kind == 'deployer':
                            self.deploy(project, template, output)
                        else:
                            build_maintenance_commandbox.build(project, output)
                self.assertFalse(output.exists())
                self.assertEqual(list(folder.glob('.*.partial')), [])

    def test_size_boundary_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            package, output = self.fixture(folder), folder / 'bootstrap.py'
            package.write_bytes(b'0' * MAX_MANAGER_BOOTSTRAP_BYTES)
            with self.assertRaisesRegex(ValueError, 'below 1 MB'):
                self.generate(package, output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
