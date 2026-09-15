"""Exercise automatic gh installation over HTTP into isolated user directories."""
import hashlib
from http.server import ThreadingHTTPServer
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
import OMFITlib_template_cli as cli
import OMFITlib_template_github as github
from OMFITlib_template_archive import TemplateError
from OMFITlib_template_service import Cancelled
from test_github import APIHandler, LocalOpener


def archive_data(kind='regular', version='2.99.0'):
    data = b'#!/bin/sh\nprintf "gh version ' + version.encode() + b' (fixture)\\n"\n'
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        name = 'gh_2.99.0_linux_amd64/bin/gh'
        info = tarfile.TarInfo('../escaped' if kind == 'traversal' else name)
        if kind in ('symlink', 'hardlink'):
            info.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
            info.linkname = '/tmp/omfit-test-escape'
            archive.addfile(info)
        else:
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
            if kind == 'duplicate':
                archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


class State:
    def __init__(self, data):
        self.calls = []
        self.data = data
        self.release = dict(tag_name='v2.99.0', draft=False, prerelease=False,
            assets=[dict(name='gh_2.99.0_linux_amd64.tar.gz', id=17, state='uploaded',
                         size=len(data), digest='sha256:' + hashlib.sha256(data).hexdigest())])

    def dispatch(self, method, path, content):
        if method == 'GET' and path == '/repos/cli/cli/releases/latest':
            return 200, self.release
        if method == 'GET' and path == '/repos/cli/cli/releases/assets/17':
            return 200, self.data
        return 404, {}


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux executable installation')
class CLITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), APIHandler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='omfit-gh-test-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {'XDG_DATA_HOME': str(self.directory)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.discovery = patch.object(cli.shutil, 'which', return_value=None)
        self.discovery.start()
        self.addCleanup(self.discovery.stop)
        architecture = patch.object(cli.platform, 'machine', return_value='x86_64')
        architecture.start()
        self.addCleanup(architecture.stop)
        self.state = self.server.state = State(archive_data())
        self.client = github.GitHub('cli/cli', token='', cancel=threading.Event())
        self.client.opener = LocalOpener(self.server.server_port)

    def assert_clean(self):
        self.assertFalse(cli.cli_path().exists())
        self.assertFalse([path for path in self.directory.rglob('*') if path.is_file()])

    def test_install_verify_reuse_and_shared_credential_discovery(self):
        before = dict(os.environ)
        executable = cli.ensure_cli(self.client)
        self.assertEqual(executable, str(cli.cli_path()))
        self.assertEqual(Path(executable).stat().st_mode & 0o777, 0o700)
        self.assertIn('gh version 2.99.0', subprocess.check_output([executable, '--version'], text=True))
        calls = len(self.state.calls)
        self.assertEqual(cli.ensure_cli(self.client), executable)
        self.assertEqual(len(self.state.calls), calls)
        self.assertEqual(dict(os.environ), before)
        self.assertFalse(any('Authorization' in call[2] for call in self.state.calls))
        self.assertEqual(list(cli.cli_path().parent.iterdir()), [cli.cli_path()])
        with patch.dict(os.environ, {}, clear=True), patch.object(cli, 'cli_path', return_value=Path(executable)), \
                patch.object(github.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'private-test-token')) as run:
            self.assertEqual(github.credentials(), ('private-test-token', 'GitHub CLI'))
            self.assertEqual(run.call_args.args[0][0], executable)

    def test_system_cli_reused_without_download(self):
        with patch.object(cli.shutil, 'which', return_value='/usr/bin/gh'):
            self.assertEqual(cli.ensure_cli(self.client), '/usr/bin/gh')
        self.assertEqual(self.state.calls, [])
        self.assert_clean()

    def test_checksum_truncation_and_excess_stop_before_execution(self):
        original = self.state.data
        for data in (b'x' + original[1:], original[:-1], original + b'excess'):
            with self.subTest(size=len(data)), patch.object(cli.subprocess, 'run') as run:
                self.state.data = data
                with self.assertRaises(TemplateError):
                    cli.ensure_cli(self.client)
                run.assert_not_called()
                self.assert_clean()

    def test_untrusted_or_incomplete_release_stops_before_download(self):
        for field, value in (('digest', None), ('size', cli.MAX_ARCHIVE + 1), ('id', -1), ('state', 'new')):
            self.state = self.server.state = State(archive_data())
            self.state.release['assets'][0][field] = value
            with self.subTest(field=field), self.assertRaises(TemplateError):
                cli.ensure_cli(self.client)
            self.assertEqual(len(self.state.calls), 1)
            self.assert_clean()
        for field, value in (('draft', True), ('prerelease', True), ('tag_name', '../../bad')):
            self.state = self.server.state = State(archive_data())
            self.state.release[field] = value
            with self.subTest(field=field), self.assertRaises(TemplateError):
                cli.ensure_cli(self.client)
            self.assert_clean()

    def test_links_path_traversal_duplicate_and_wrong_version_never_installed(self):
        for kind in ('symlink', 'hardlink', 'traversal', 'duplicate', 'wrong-version'):
            data = archive_data(kind, version='0.0.1' if kind == 'wrong-version' else '2.99.0')
            self.state = self.server.state = State(data)
            with self.subTest(kind=kind), self.assertRaises(TemplateError):
                cli.ensure_cli(self.client)
            self.assert_clean()

    def test_cancelled_download_cleans_staging(self):
        self.client.progress = lambda label, done, total: self.client.cancel.set() if done else None
        with self.assertRaises(Cancelled):
            cli.ensure_cli(self.client)
        self.assert_clean()

    def test_existing_unusable_file_is_not_overwritten(self):
        target = cli.cli_path()
        target.parent.mkdir(parents=True)
        target.write_bytes(b'keep-this-file')
        target.chmod(0o600)
        with self.assertRaises(TemplateError):
            cli.ensure_cli(self.client)
        self.assertEqual(target.read_bytes(), b'keep-this-file')

    def test_execution_failure_leaves_no_installation(self):
        with patch.object(cli.subprocess, 'run', side_effect=PermissionError(13, 'noexec')):
            with self.assertRaisesRegex(TemplateError, '执行权限'):
                cli.ensure_cli(self.client)
        self.assert_clean()

    def test_dangling_destination_link_is_not_followed(self):
        target = cli.cli_path()
        target.parent.mkdir(parents=True)
        outside = self.directory / 'unrelated'
        target.symlink_to(outside)
        with self.assertRaises(TemplateError):
            cli.ensure_cli(self.client)
        self.assertTrue(target.is_symlink())
        self.assertFalse(outside.exists())

    def test_architectures_and_official_repository(self):
        for machine, expected in [('x86_64', 'amd64'), ('aarch64', 'arm64'), ('armv7l', 'armv6'), ('i686', '386')]:
            with patch.object(cli.platform, 'machine', return_value=machine):
                self.assertEqual(cli.linux_architecture(), expected)
        with patch.object(cli.platform, 'machine', return_value='unsupported'), self.assertRaises(TemplateError):
            cli.ensure_cli(self.client)
        self.client.repo = 'other/cli'
        with self.assertRaisesRegex(TemplateError, '官方'):
            cli.ensure_cli(self.client)
        self.assertEqual(self.state.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
