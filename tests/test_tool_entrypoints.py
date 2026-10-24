"""Trust and interruption boundaries of standalone deployment entry points."""
from contextlib import ExitStack
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'OMFITtemplates/LIB'))
import bootstrap_manager as bootstrap
import deploy_project as deploy
import run_regressions as runner
from OMFITlib_template_service import publish


class OMFITmodule(dict):
    pass


class LiveTree(dict):
    """Model native writes that mutate first and only then raise Abort."""
    abort_current = False
    refuse_restore = False

    def __setitem__(self, key, value):
        if self.refuse_restore and value is self.previous:
            raise RuntimeError('restore refused')
        super().__setitem__(key, value)
        if self.abort_current and value is self.current:
            raise KeyboardInterrupt('assignment interrupted after mutation')


class BootstrapTests(unittest.TestCase):
    def exercise(self, *, previous=True, fail_assignment=False, refuse_restore=False, reopen_error=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name) / 'bootstrap'
        directory.mkdir()
        original = KeyboardInterrupt('GUI interrupted')
        def interrupted():
            raise original
        def reopen():
            if reopen_error:
                raise KeyboardInterrupt('old GUI also interrupted')
        old = OMFITmodule(GUIS={'main': SimpleNamespace(run=reopen)}) if previous else None
        current = OMFITmodule(SETTINGS={'MODULE': {'ID': 'OMFITtemplates'}},
                              GUIS={'main': SimpleNamespace(run=interrupted)})
        tree = LiveTree()
        tree.previous, tree.current = old, current
        if previous:
            dict.__setitem__(tree, 'OMFITtemplates', old)
        tree.abort_current, tree.refuse_restore = fail_assignment, refuse_restore
        with ExitStack() as scope:
            scope.enter_context(patch.dict(sys.modules, {
                'omfit_classes.omfit_base': SimpleNamespace(OMFITmodule=lambda *a, **kw: current),
                'tkinter': SimpleNamespace(_default_root=None),
            }))
            scope.enter_context(patch.object(bootstrap, 'MANAGER', None))
            scope.enter_context(patch.object(bootstrap, 'fetch', return_value=b'fixture'))
            scope.enter_context(patch.object(bootstrap, 'extract', return_value=directory))
            scope.enter_context(patch.object(bootstrap.tempfile, 'mkdtemp', return_value=str(directory)))
            with self.assertRaises(KeyboardInterrupt) as caught:
                bootstrap.install(tree)
        return tree, old, current, directory, caught.exception, original

    def test_abort_after_attach_restores_previous_and_releases_unreferenced_files(self):
        tree, old, _, directory, caught, original = self.exercise()
        self.assertIs(caught, original)
        self.assertIs(tree['OMFITtemplates'], old)
        self.assertFalse(directory.exists())
        self.assertEqual(tree._template_bootstrap_storage, [])

    def test_abort_after_native_assignment_mutates_still_rolls_back(self):
        tree, old, _, directory, caught, _ = self.exercise(fail_assignment=True)
        self.assertIn('assignment interrupted', str(caught))
        self.assertIs(tree['OMFITtemplates'], old)
        self.assertFalse(directory.exists())

    def test_first_install_abort_removes_only_the_new_module(self):
        tree, _, _, directory, caught, original = self.exercise(previous=False)
        self.assertIs(caught, original)
        self.assertNotIn('OMFITtemplates', tree)
        self.assertFalse(directory.exists())

    def test_failed_restore_preserves_live_backing_and_original_abort(self):
        tree, _, current, directory, caught, original = self.exercise(refuse_restore=True)
        self.assertIs(caught, original)
        self.assertIs(tree['OMFITtemplates'], current)
        self.assertTrue(directory.exists())
        self.assertIn(str(directory), tree._template_bootstrap_storage)
        self.assertIn('restore refused', caught.bootstrap_rollback_errors[0])

    def test_reopen_failure_does_not_replace_original_abort(self):
        tree, old, _, directory, caught, original = self.exercise(reopen_error=True)
        self.assertIs(caught, original)
        self.assertIs(tree['OMFITtemplates'], old)
        self.assertFalse(directory.exists())
        self.assertIn('old GUI', caught.bootstrap_rollback_errors[0])


class DeploymentTrustTests(unittest.TestCase):
    def fixture(self, directory, malicious=False):
        project = directory / 'source.zip'
        rows = ["['CGYRO_TGLF_scan'] <-:-:-> OMFITmodule <-:-:->  <-:-:-> {}",
                "['OMFITtemplates'] <-:-:-> OMFITmodule <-:-:->  <-:-:-> {}"]
        contents = {}
        marker = directory / 'untrusted-code-executed'
        for module in deploy.RUNTIME:
            name = 'OMFITtemplates/LIB/' + module + '.py'
            rows.append("['OMFITtemplates']['LIB'][" + repr(module) + "] <-:-:-> OMFITpython <-:-:-> ./" + name + ' <-:-:-> {}')
            contents[name] = (ROOT / name).read_bytes()
            if malicious:
                contents[name] = ("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n").encode()
        with zipfile.ZipFile(project, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('OMFITsave.txt', '\n'.join(rows) + '\n')
            for name, content in contents.items():
                archive.writestr(name, content)
        template = Path(publish(project, directory / 'library', dict(
            author='tdxy-liu', id='cgyro-tglf', version='9.8.7', name='fixture'),
            ['CGYRO_TGLF_scan', 'OMFITtemplates']))
        return template, marker

    def pinned(self, template):
        data = template.read_bytes()
        return dict(repository=deploy.REPOSITORY, template=dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))

    def test_checkout_never_executes_self_hashed_template_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            template, marker = self.fixture(directory, malicious=True)
            stage = directory / 'stage'
            stage.mkdir()
            # Match a fresh CLI process: an already imported trusted updater
            # would accidentally hide execution of the archive's Python.
            with patch.dict(sys.modules), patch.object(deploy, 'RELEASE', None):
                for name in deploy.RUNTIME:
                    sys.modules.pop(name, None)
                with deploy.runtime(template, stage) as (engine, _, _, snapshot):
                    self.assertTrue(callable(engine.plan_update))
                    self.assertEqual(snapshot.read_bytes(), template.read_bytes())
                    self.assertFalse(marker.exists())
                self.assertFalse(any(name in sys.modules for name in deploy.RUNTIME))
            self.assertFalse(marker.exists())

    def test_release_rejects_wrong_local_digest_before_import_or_zip_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            template, marker = self.fixture(directory, malicious=True)
            release = self.pinned(template)
            release['template']['sha256'] = '0' * 64
            stage = directory / 'stage'
            stage.mkdir()
            with patch.object(deploy, 'RELEASE', release):
                with self.assertRaisesRegex(deploy.DeploymentError, 'does not match'):
                    with deploy.runtime(template, stage):
                        self.fail('Unverified template accepted')
            self.assertFalse(marker.exists())
            self.assertEqual(list(stage.iterdir()), [])

    def test_pinned_engine_ignores_cached_modules_and_restores_them_on_abort(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            template, _ = self.fixture(directory)
            stage = directory / 'stage'
            stage.mkdir()
            previous = {name: sys.modules.get(name) for name in deploy.RUNTIME}
            with patch.object(deploy, 'RELEASE', self.pinned(template)):
                with self.assertRaises(KeyboardInterrupt):
                    with deploy.runtime(template, stage) as (engine, _, _, snapshot):
                        self.assertIsNot(engine, previous['OMFITlib_template_service'])
                        template.write_bytes(b'replaced original input')
                        with engine.Template(snapshot) as checked:
                            checked.verify()
                        raise KeyboardInterrupt('caller interrupted')
            self.assertEqual({name: sys.modules.get(name) for name in deploy.RUNTIME}, previous)
            self.assertNotIn(str(stage), sys.path)


class RegressionRunnerTests(unittest.TestCase):
    def test_windows_failure_counts_are_not_lost_to_crlf(self):
        output = b'FAIL: case\r\nRan 3 tests in 0.1s\r\nFAILED (failures=1, errors=1, skipped=1)\r\n'
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(stdout=output, returncode=1)):
                row = runner.run_suite(ROOT / 'tests/test_example.py', ROOT, Path(temporary), {}, 10, False, None)
        self.assertEqual((row['tests'], row['failures'], row['errors'], row['skipped']), (3, 1, 1, 1))
        self.assertEqual(row['failed_tests'], ['case'])


if __name__ == '__main__':
    unittest.main()
