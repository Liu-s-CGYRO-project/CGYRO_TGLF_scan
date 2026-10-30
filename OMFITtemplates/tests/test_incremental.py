"""File-level updates reuse local bytes and leave the running installation intact."""
from contextlib import contextmanager
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
from OMFITlib_template_archive import TemplateError, json_bytes
from OMFITlib_template_incremental import (FORMAT, activate_installation, active_launch, install_incremental,
    plan_incremental, restore_activation, validate_manifest, verified_asset, verify_installation, RECEIPT, MANIFEST,
    anchor_directory)
from OMFITlib_template_service import Cancelled
from OMFITlib_template_session import OMFITSession


def fixture_payload(version='1.7.0'):
    return {
        'OMFITtemplates/OMFITsave.txt': b"['GUIS'] <-:-:-> OMFITtree <-:-:->  <-:-:-> {}\n"
            b"['GUIS']['main'] <-:-:-> OMFITpythonGUI <-:-:-> ./GUIS/main.py <-:-:-> {}\n",
        'OMFITtemplates/SettingsNamelist.txt': json_bytes({'MODULE': {'ID': 'OMFITtemplates', 'version': version}}),
        'OMFITtemplates/GUIS/main.py': b'print("NEW GUI")\n',
        'OMFITtemplates/launch.py': b'print("START")\n',
        'OMFITtemplates/LIB/OMFITlib_template_versions.py': ('MANAGER_VERSION = ' + repr(version)).encode(),
        'OMFITtemplates/help.rst': b'UNCHANGED DOCUMENTATION\n',
        'start_manager.sh': b'#!/bin/sh\n',
    }


class FixtureClient:
    def __init__(self, payload):
        self.repo, self.base = 'team/demo', '/repos/team/demo'
        self.cancel, self.progress = threading.Event(), None
        self.bodies, self.requests = {}, []
        manifest = dict(format=FORMAT, version='1.7.0', files={})
        assets = {}
        for name, data in payload.items():
            digest = hashlib.sha256(data).hexdigest()
            asset = 'omfit-file-' + digest + '.gz'
            manifest['files'][name] = dict(size=len(data), sha256=digest, asset=asset, mode=0o755 if name.endswith('.sh') else 0o644)
            assets[asset] = self.add(asset, gzip.compress(data, mtime=0))
        self.manifest = manifest
        self.release = dict(latest='1.7.0', incremental=dict(assets=assets,
            manifest=self.add('manifest', json_bytes(manifest))))

    def add(self, name, data):
        identity = len(self.bodies) + 1
        self.bodies[identity] = data
        return verified_asset(dict(name=name, id=identity, size=len(data), state='uploaded',
            digest='sha256:' + hashlib.sha256(data).hexdigest()), self.repo)

    @contextmanager
    def _open(self, path, **kw):
        identity = int(path.rsplit('/', 1)[1])
        self.requests.append(identity)
        yield io.BytesIO(self.bodies[identity])


class IncrementalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        environment = patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.base / 'config'),
                                              'XDG_DATA_HOME': str(self.base / 'data')})
        environment.start()
        self.addCleanup(environment.stop)
        self.old = self.base / 'old'
        self.updates = self.base / 'updates'
        self.payload = fixture_payload()
        for name, content in self.payload.items():
            target = self.old / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (self.old / 'OMFITtemplates/GUIS/main.py').write_bytes(b'print("OLD GUI")\n')
        (self.old / 'current-results.txt').write_bytes(b'KEEP RESULTS')
        (self.old / 'OMFITtemplates/obsolete.py').write_bytes(b'old = 1')
        self.client = FixtureClient(self.payload)

    def plan(self):
        return plan_incremental(self.client, self.client.release, self.old / 'OMFITtemplates')

    def test_only_changed_file_is_downloaded_and_full_new_version_is_assembled(self):
        plan = self.plan()
        self.assertEqual(plan['changed'], ['OMFITtemplates/GUIS/main.py'])
        self.assertEqual(len(plan['reused']), len(self.payload) - 1)
        manifest_requests = len(self.client.requests)
        installed = Path(install_incremental(self.client, plan, self.updates))
        self.assertEqual(len(self.client.requests) - manifest_requests, 1)
        self.assertEqual(verify_installation(installed, self.updates), installed)
        self.assertTrue(all((installed / name).read_bytes() == value for name, value in self.payload.items()))
        self.assertFalse((installed / 'OMFITtemplates/obsolete.py').exists())
        self.assertEqual((self.old / 'current-results.txt').read_bytes(), b'KEEP RESULTS')
        self.assertTrue((self.old / 'OMFITtemplates/obsolete.py').is_file())
        self.assertIn(b'OLD GUI', (self.old / 'OMFITtemplates/GUIS/main.py').read_bytes())
        self.assertFalse((self.updates / 'active.json').exists())

    def test_all_matching_files_require_no_payload_download(self):
        (self.old / 'OMFITtemplates/GUIS/main.py').write_bytes(self.payload['OMFITtemplates/GUIS/main.py'])
        plan = self.plan()
        self.assertEqual(plan['download_bytes'], 0)
        self.assertEqual(plan['changed'], [])
        install_incremental(self.client, plan, self.updates)
        self.assertEqual(len(self.client.requests), 1)  # Manifest only.

    def test_omfit_relocated_sources_are_reused_by_hash(self):
        relocated = self.base / 'renamed.py'
        relocated.write_bytes(self.payload['OMFITtemplates/GUIS/main.py'])
        plan = plan_incremental(self.client, self.client.release, self.old / 'OMFITtemplates',
                                {'OMFITtemplates/GUIS/main.py': str(relocated)})
        self.assertEqual(plan['changed'], [])

    def test_source_changed_after_preview_aborts_without_switching(self):
        plan = self.plan()
        (self.old / 'OMFITtemplates/help.rst').write_bytes(b'USER EDIT')
        with self.assertRaisesRegex(TemplateError, '本地文件已变化'):
            install_incremental(self.client, plan, self.updates)
        self.assertFalse(list((self.updates / 'versions').iterdir()))

    def test_bad_blob_digest_and_cancel_keep_current_version(self):
        plan = self.plan()
        identity = next(iter(plan['assets'].values()))['asset_id']
        self.client.bodies[identity] = b'CORRUPTED'
        with self.assertRaises(TemplateError):
            install_incremental(self.client, plan, self.updates)
        self.client.cancel.set()
        with self.assertRaises(Cancelled):
            install_incremental(self.client, plan, self.updates)
        self.assertFalse(list((self.updates / 'versions').iterdir()))
        self.assertFalse((self.updates / 'active.json').exists())

    def test_decompressed_size_and_content_are_checked(self):
        plan = self.plan()
        key = next(iter(plan['assets']))
        plan['assets'][key] = self.client.add(key, gzip.compress(b'x' * 100000))
        with self.assertRaisesRegex(TemplateError, '内容校验'):
            install_incremental(self.client, plan, self.updates)
        self.assertFalse(list((self.updates / 'versions').iterdir()))

    def test_manifest_rejects_paths_sizes_modes_and_wrong_versions(self):
        for name in ('../private', '/absolute', 'OMFITtemplates/../../private', 'OMFITtemplates\\evil', 'CGYRO/Cases/result'):
            bad = copy.deepcopy(self.client.manifest)
            bad['files'][name] = next(iter(bad['files'].values()))
            with self.subTest(name=name), self.assertRaises(TemplateError):
                validate_manifest(bad, '1.7.0')
        for changes in ({'size': 9 * 1024 ** 2}, {'size': True}, {'mode': 0o777}, {'asset': 'other.gz'}):
            bad = copy.deepcopy(self.client.manifest)
            bad['files']['OMFITtemplates/help.rst'].update(changes)
            with self.assertRaises(TemplateError):
                validate_manifest(bad, '1.7.0')
        with self.assertRaises(TemplateError):
            validate_manifest(self.client.manifest, '1.8.0')

    def test_activation_is_verified_and_can_be_reverted(self):
        installed = install_incremental(self.client, self.plan(), self.updates)
        previous = activate_installation(installed, self.updates)
        self.assertIsNone(previous)
        self.assertEqual(active_launch(self.updates), Path(installed) / 'OMFITtemplates/launch.py')
        restore_activation(previous, self.updates)
        self.assertIsNone(active_launch(self.updates))
        activate_installation(installed, self.updates)
        (Path(installed) / 'OMFITtemplates/launch.py').write_bytes(b'TAMPERED')
        with self.assertRaises(TemplateError):
            active_launch(self.updates)

    def test_stale_activation_rollback_preserves_other_window(self):
        installed = install_incremental(self.client, self.plan(), self.updates)
        first = activate_installation(installed, self.updates, receipt=True)
        # Even activating the same installation again belongs to a different
        # window/transaction; comparing paths alone would miss this ABA case.
        second = activate_installation(installed, self.updates, receipt=True)
        current = (self.updates / 'active.json').read_bytes()
        with self.assertRaisesRegex(TemplateError, '其他窗口'):
            restore_activation(first, self.updates)
        self.assertEqual((self.updates / 'active.json').read_bytes(), current)
        restore_activation(second, self.updates)
        self.assertEqual((self.updates / 'active.json').read_bytes(), first.installed)
        restore_activation(first, self.updates)
        self.assertIsNone(active_launch(self.updates))

    def test_receipt_and_file_rewrite_cannot_replace_external_manifest_anchor(self):
        installed = Path(install_incremental(self.client, self.plan(), self.updates))
        activate_installation(installed, self.updates)
        active = (self.updates / 'active.json').read_bytes()
        receipt_path = installed / RECEIPT
        receipt = json.loads(receipt_path.read_bytes())
        content = b'print("ALTERED, NEVER EXECUTED")\n'
        (installed / 'OMFITtemplates/launch.py').write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        receipt['manifest']['files']['OMFITtemplates/launch.py'].update(
            size=len(content), sha256=digest, asset='omfit-file-' + digest + '.gz')
        altered_manifest = json_bytes(receipt['manifest'])
        for rewrite_raw, rewrite_receipt_digest in ((False, False), (False, True), (True, True)):
            if rewrite_raw:
                (installed / MANIFEST).write_bytes(altered_manifest)
            if rewrite_receipt_digest:
                receipt['manifest_sha256'] = hashlib.sha256(altered_manifest).hexdigest()
            receipt_path.write_bytes(json_bytes(receipt))
            with self.subTest(raw=rewrite_raw, receipt_digest=rewrite_receipt_digest):
                with self.assertRaises(TemplateError):
                    activate_installation(installed, self.updates)
                with self.assertRaises(TemplateError):
                    active_launch(self.updates)
                self.assertEqual((self.updates / 'active.json').read_bytes(), active)

    def test_missing_anchor_is_not_reconstructed_from_legacy_receipt(self):
        installed = Path(install_incremental(self.client, self.plan(), self.updates))
        activate_installation(installed, self.updates)
        (anchor_directory(self.updates) / (installed.name + '.json')).unlink()
        with patch.object(self.client, '_open', side_effect=AssertionError('startup must remain offline')):
            with self.assertRaisesRegex(TemplateError, '重新检查'):
                active_launch(self.updates)
            with self.assertRaisesRegex(TemplateError, '独立摘要'):
                activate_installation(installed, self.updates)
        self.assertTrue((installed / 'OMFITtemplates/launch.py').is_file())

    def test_anchor_version_and_raw_asset_digest_are_both_checked(self):
        installed = Path(install_incremental(self.client, self.plan(), self.updates))
        anchor_path = anchor_directory(self.updates) / (installed.name + '.json')
        anchor = json.loads(anchor_path.read_bytes())
        self.assertEqual(anchor['sha256'], self.client.release['incremental']['manifest']['sha256'])
        self.assertEqual(anchor['repository'], self.client.repo)
        anchor['version'] = '1.8.0'
        anchor_path.write_bytes(json_bytes(anchor))
        with self.assertRaisesRegex(TemplateError, '版本不匹配'):
            verify_installation(installed, self.updates)

    def test_malformed_anchor_fails_as_a_recoverable_validation_error(self):
        installed = Path(install_incremental(self.client, self.plan(), self.updates))
        anchor_path = anchor_directory(self.updates) / (installed.name + '.json')
        for invalid in (b'[]', b'{"sha256": 123, "version": "1.8.0"}', b'{}' + b' ' * 4096):
            with self.subTest(invalid=invalid[:70]):
                anchor_path.write_bytes(invalid)
                with self.assertRaisesRegex(TemplateError, '独立摘要锚点'):
                    verify_installation(installed, self.updates)

    def test_unanchored_redirect_keeps_trusted_original_launcher_offline(self):
        from contextlib import redirect_stderr
        import runpy
        from unittest.mock import Mock
        installed = Path(install_incremental(self.client, self.plan(), self.updates))
        activate_installation(installed, self.updates)
        (anchor_directory(self.updates) / (installed.name + '.json')).unlink()
        launcher = Path(__file__).resolve().parents[1] / 'launch.py'
        namespace = runpy.run_path(str(launcher), run_name='test_original_launcher')
        gui = Mock()
        errors = io.StringIO()
        with patch('OMFITlib_template_incremental.update_directory', return_value=self.updates), \
                patch.dict(namespace['main'].__globals__, {'gui_environment': gui}), \
                patch.object(sys, 'argv', [str(launcher)]), patch.object(os, 'execv') as execute, \
                redirect_stderr(errors):
            namespace['main']()
        execute.assert_not_called()
        gui.assert_called_once()
        self.assertIn('继续运行当前目录版本', errors.getvalue())
        self.assertIn('独立摘要', errors.getvalue())

    def test_manifest_plan_mutation_does_not_create_installation(self):
        plan = self.plan()
        plan['manifest']['files']['OMFITtemplates/help.rst']['sha256'] = '0' * 64
        plan['manifest']['files']['OMFITtemplates/help.rst']['asset'] = 'omfit-file-' + '0' * 64 + '.gz'
        with self.assertRaisesRegex(TemplateError, '附件不一致'):
            install_incremental(self.client, plan, self.updates)
        self.assertFalse(self.updates.exists())

    def test_default_anchor_is_outside_data_home_and_overlap_is_rejected(self):
        from OMFITlib_template_incremental import update_directory
        installed = Path(install_incremental(self.client, self.plan()))
        anchors = anchor_directory(update_directory())
        self.assertTrue((anchors / (installed.name + '.json')).is_file())
        self.assertTrue(anchors.is_relative_to(self.base / 'config'))
        self.assertFalse(anchors.is_relative_to(self.base / 'data'))
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.base / 'data' / 'config')}):
            with self.assertRaisesRegex(TemplateError, '不能位于'):
                activate_installation(installed)
            with self.assertRaisesRegex(TemplateError, '不能位于'):
                install_incremental(self.client, self.plan())

    def test_activation_lock_is_shared_between_processes(self):
        from OMFITlib_template_incremental import _activation_lock
        source = ('from pathlib import Path\n'
                  'from OMFITlib_template_incremental import _activation_lock\n'
                  'from OMFITlib_template_archive import TemplateError\n'
                  'import sys\n'
                  'try:\n'
                  '    with _activation_lock(Path(sys.argv[1])): pass\n'
                  'except TemplateError:\n'
                  '    sys.exit(3)\n')
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'LIB'))
        with _activation_lock(self.updates):
            result = subprocess.run([sys.executable, '-B', '-c', source, str(self.updates)],
                                    env=environment, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 3, result.stderr.decode('utf-8', 'replace'))
        # Closing the owner's descriptor releases the lock after failures too.
        with _activation_lock(self.updates):
            pass

    def test_current_symlink_is_downloaded_instead_of_followed(self):
        source = self.old / 'OMFITtemplates/help.rst'
        moved = self.base / 'external.txt'
        source.rename(moved)
        try:
            source.symlink_to(moved)
        except OSError:
            self.skipTest('symlinks unavailable')
        self.assertIn('OMFITtemplates/help.rst', self.plan()['changed'])

    def test_missing_incremental_asset_is_not_silently_installed(self):
        self.client.release['incremental']['assets'].clear()
        with self.assertRaisesRegex(TemplateError, '附件不完整'):
            self.plan()


class ManagerSessionTest(unittest.TestCase):
    def test_module_replacement_preserves_other_modules_and_settings(self):
        class Module(dict):
            def __init__(self, filename='', **kw):
                super().__init__(SETTINGS={'MODULE': {'ID': 'OMFITtemplates'}, 'SETUP': {'new_default': 5}},
                                 GUIS={'main': SimpleNamespace(run=lambda: calls.append('open'))})
                self.filename = filename
        calls = []
        previous = Module()
        previous['SETTINGS']['SETUP'] = {'user_value': 42}
        results = object()
        omfit = {'OMFITtemplates': previous, 'CGYRO_TGLF_scan': results}
        session = OMFITSession(omfit)
        saved = session.replace_manager('/fixture/new/OMFITtemplates')
        self.assertIs(saved, previous)
        self.assertIs(omfit['CGYRO_TGLF_scan'], results)
        self.assertEqual(omfit['OMFITtemplates']['SETTINGS']['SETUP'], {'new_default': 5, 'user_value': 42})
        self.assertEqual(previous['SETTINGS']['SETUP'], {'user_value': 42})
        session.reopen_manager()
        self.assertEqual(calls, ['open'])
        session.restore_manager(saved)
        self.assertIs(omfit['OMFITtemplates'], previous)

    def test_failed_module_constructor_leaves_original_tree(self):
        class Module(dict):
            def __init__(self, filename='', **kw):
                if filename:
                    raise OSError('load failed')
        previous = Module()
        omfit = {'OMFITtemplates': previous}
        with self.assertRaises(OSError):
            OMFITSession(omfit).replace_manager('/fixture/new')
        self.assertIs(omfit['OMFITtemplates'], previous)


if __name__ == '__main__':
    unittest.main()
