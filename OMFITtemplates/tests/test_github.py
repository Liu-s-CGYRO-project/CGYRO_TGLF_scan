"""Exercise the real HTTP transport against an isolated local GitHub API fixture."""
import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib import error, parse, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
import OMFITlib_template_github as github
from OMFITlib_template_archive import TemplateError
from OMFITlib_template_service import Cancelled, Template, list_library, publish
from OMFITlib_template_session import OMFITSession
from test_templates import fixture


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        state = self.server.state
        path = parse.urlsplit(self.path).path
        content = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        state.calls.append((self.command, self.path, dict(self.headers), content))
        status, body = state.dispatch(self.command, path, content)
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/octet-stream' if isinstance(body, bytes) else 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PATCH = do_PUT = handle_request


class LocalOpener:
    def __init__(self, port):
        self.port = port

    def open(self, req, timeout=30):
        url = parse.urlsplit(req.full_url)
        assert url.netloc in ('api.github.com', 'uploads.github.com'), req.full_url
        local = 'http://127.0.0.1:' + str(self.port) + url.path + ('?' + url.query if url.query else '')
        translated = request.Request(local, data=req.data, headers=dict(req.header_items()), method=req.method)
        return request.urlopen(translated, timeout=timeout)


class APIState:
    def __init__(self):
        self.calls, self.releases, self.assets = [], [], {}
        self.empty = False
        self.fail = ''
        self.cancel_after_upload = None

    def dispatch(self, method, path, content):
        base = '/repos/team/demo'
        if self.fail and (method + ' ' + path) == self.fail:
            return 403, {'message': 'sensitive-fixture-token must not be logged'}
        if method == 'GET':
            if path == base:
                return 200, {'private': True, 'default_branch': 'main', 'permissions': {'push': True}}
            if path == '/user':
                return 200, {'login': 'developer'}
            if path == base + '/commits':
                return (409, {'message': 'empty'}) if self.empty else (200, [{'sha': 'a' * 40}])
            if path == base + '/commits/main':
                return 200, {'sha': 'a' * 40}
            if path == base + '/releases':
                return 200, self.releases
            if path == base + '/releases/assets/17':
                return 200, self.assets[17]
            return 404, {'message': 'not found'}
        if method == 'POST' and path == base + '/releases':
            value = json.loads(content)
            value.update(id=1, upload_url='https://uploads.github.com/repos/team/demo/releases/1/assets{?name,label}')
            self.releases.append(value)
            return 201, value
        if method == 'POST' and path == base + '/releases/1/assets':
            self.assets[17] = content
            if self.cancel_after_upload:
                self.cancel_after_upload.set()
            return 201, {'id': 17, 'name': self.asset_name, 'state': 'uploaded', 'size': len(content),
                         'digest': 'sha256:' + hashlib.sha256(content).hexdigest()}
        if method == 'PATCH' and path == base + '/releases/1':
            self.releases[0].update(json.loads(content))
            return 200, self.releases[0]
        if method == 'PUT' and path == base + '/contents/README.md':
            self.empty = False
            return 201, {'content': {'name': 'README.md'}}
        return 500, {'message': 'unhandled ' + method + ' ' + path}


class GitHubTest(unittest.TestCase):
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
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        source = self.directory / 'source.zip'
        fixture(source, 2)
        self.meta = dict(author='alice', id='demo', version='1.0', name='示例', description='修复设置')
        self.template = publish(source, self.directory / 'library', self.meta, ['Demo'])
        self.state = APIState()
        self.state.asset_name = Path(self.template).name
        self.server.state = self.state
        self.client = github.GitHub('team/demo', token='sensitive-fixture-token')
        self.client.opener = LocalOpener(self.server.server_port)

    def seed_release(self):
        content = Path(self.template).read_bytes()
        self.state.assets[17] = content
        metadata = dict(self.meta, roots=['Demo'], examples=False, sha256=hashlib.sha256(content).hexdigest())
        release = dict(id=1, tag_name='omfit/alice/demo/1.0', draft=False, prerelease=False,
                       body=github.MARKER + json.dumps(metadata) + '\n-->', published_at='2026-09-11T00:00:00Z',
                       author={'login': 'developer'}, assets=[dict(id=17, name=self.state.asset_name, state='uploaded',
                       size=len(content), digest='sha256:' + metadata['sha256'])])
        self.state.releases.append(release)
        return self.client.list_releases()[0][0]

    def test_release_metadata_accepts_line_endings(self):
        expected = self.seed_release()
        original = self.state.releases[0]['body']
        for newline in ('\n', '\r\n', '\r'):
            with self.subTest(newline=repr(newline)):
                self.state.releases[0]['body'] = original.replace('\n', newline)
                releases, errors = self.client.list_releases()
                self.assertEqual(errors, [])
                self.assertEqual(len(releases), 1)
                for key in ('name', 'description', 'roots', 'examples', 'sha256'):
                    self.assertEqual(releases[0][key], expected[key])

    def test_repository_normalization_and_untrusted_urls(self):
        for value in ('team/demo', 'https://github.com/team/demo.git', 'git@github.com:team/demo.git'):
            self.assertEqual(github.repository(value), 'team/demo')
        for value in ('https://evil.test/team/demo', 'https://token@github.com/team/demo', 'team/..',
                      'https://github.com/team/demo?token=secret', 'team/demo/../../user', 'team/demo\n?x'):
            with self.subTest(value=value), self.assertRaises(TemplateError):
                github.repository(value)

    def test_public_connection_needs_no_credential(self):
        self.client._token = ''
        result = self.client.connect()
        self.assertEqual(result['login'], '')
        self.assertFalse(any(path == '/user' for _, path, _, _ in self.state.calls))
        self.assertTrue(all('Authorization' not in headers for _, _, headers, _ in self.state.calls))

    def test_real_http_download_hash_verification_and_offline_cache(self):
        release = self.seed_release()
        self.assertEqual(release['publisher'], 'developer')
        self.assertFalse(release['examples'])
        events = []
        self.client.progress = lambda *args: events.append(args)
        target = self.client.pull(release, self.directory / 'cache')
        with Template(target) as template:
            template.verify()
        self.assertIn('/github/team/demo/17/', target)
        self.assertTrue(events)
        self.assertEqual(len(list_library(self.directory / 'cache')[0]), 1)
        count = len(self.state.calls)
        self.assertEqual(self.client.pull(release, self.directory / 'cache'), target)
        self.assertEqual(count, len(self.state.calls))

    def test_bad_digest_and_truncated_download_never_commit_cache(self):
        release = self.seed_release()
        release['sha256'] = '0' * 64
        with self.assertRaisesRegex(TemplateError, 'SHA-256'):
            self.client.pull(release, self.directory / 'cache')
        self.assertFalse(list((self.directory / 'cache').rglob('*.zip')))
        self.assertFalse(list((self.directory / 'cache').rglob('*.partial')))
        release['sha256'] = ''
        self.state.assets[17] = self.state.assets[17][:-50]
        with self.assertRaisesRegex(TemplateError, '大小'):
            self.client.pull(release, self.directory / 'cache')

    def test_changed_repository_rejects_old_selection(self):
        release = self.seed_release()
        release['repository'] = 'other/demo'
        with self.assertRaisesRegex(TemplateError, '仓库已经改变'):
            self.client.pull(release, self.directory / 'cache')

    def test_drafts_hidden_and_manual_packages_identified(self):
        self.seed_release()
        draft = copy.deepcopy(self.state.releases[0])
        draft['draft'] = True
        self.state.releases.append(draft)
        self.state.releases[0]['body'] = 'manually uploaded package'
        entries, errors = self.client.list_releases()
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0]['examples'])
        self.assertFalse(errors)

    def test_pagination_does_not_hide_old_versions(self):
        pages = [[{}] * 100, [{'sentinel': True}]]
        with patch.object(self.client, '_json', side_effect=pages) as api:
            result = list(self.client._pages('/releases'))
        self.assertEqual(len(result), 101)
        self.assertIn('page=2', api.call_args.args[0])

    def test_prepare_is_read_only_then_draft_upload_publish(self):
        plan = self.client.prepare_publish(self.template)
        self.assertEqual(plan['login'], 'developer')
        self.assertTrue(all(call[0] == 'GET' for call in self.state.calls))
        self.assertIn('omfit/alice/demo/1.0', plan['tag'])
        url = self.client.publish_release(plan)
        writes = [(method, path) for method, path, _, _ in self.state.calls if method != 'GET']
        self.assertEqual([method for method, _ in writes], ['POST', 'POST', 'PATCH'])
        self.assertFalse(self.state.releases[0]['draft'])
        self.assertEqual(self.state.assets[17], Path(self.template).read_bytes())
        self.assertTrue(url.startswith('https://github.com/team/demo/releases/tag/'))
        self.assertFalse(any('sensitive-fixture-token' in content.decode(errors='ignore') for _, _, _, content in self.state.calls))

    def test_existing_draft_is_not_overwritten(self):
        self.state.releases = [{'tag_name': 'omfit/alice/demo/1.0', 'draft': True}]
        with self.assertRaisesRegex(TemplateError, '同一版本已存在'):
            self.client.prepare_publish(self.template)
        self.assertTrue(all(call[0] == 'GET' for call in self.state.calls))

    def test_changed_package_does_not_write_remote(self):
        plan = self.client.prepare_publish(self.template)
        with open(self.template, 'ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(TemplateError, '模板包已改变'):
            self.client.publish_release(plan)
        self.assertTrue(all(call[0] == 'GET' for call in self.state.calls))

    def test_upload_failure_keeps_draft_and_redacts_server_message(self):
        plan = self.client.prepare_publish(self.template)
        self.state.fail = 'POST /repos/team/demo/releases/1/assets'
        with self.assertRaises(TemplateError) as context:
            self.client.publish_release(plan)
        self.assertIn('草稿', str(context.exception))
        self.assertNotIn('sensitive-fixture-token', str(context.exception))
        self.assertTrue(self.state.releases[0]['draft'])
        self.assertFalse(any(method in ('PATCH', 'DELETE') for method, _, _, _ in self.state.calls))

    def test_cancel_after_upload_does_not_publish_or_delete_draft(self):
        plan = self.client.prepare_publish(self.template)
        self.client.cancel = self.state.cancel_after_upload = threading.Event()
        with self.assertRaisesRegex(TemplateError, '草稿'):
            self.client.publish_release(plan)
        self.assertTrue(self.state.releases[0]['draft'])

    def test_empty_repository_init_creates_only_reviewed_readme(self):
        self.state.empty = True
        self.assertTrue(self.client.connect()['empty'])
        with self.assertRaisesRegex(TemplateError, '尚无提交'):
            self.client.prepare_publish(self.template)
        self.client.initialize_empty()
        writes = [call for call in self.state.calls if call[0] != 'GET']
        self.assertEqual(len(writes), 1)
        payload = json.loads(writes[0][3])
        self.assertNotIn('sha', payload)
        self.assertEqual(base64.b64decode(payload['content']).decode(), github.INITIAL_README)
        with self.assertRaisesRegex(TemplateError, '已有提交'):
            self.client.initialize_empty()

    def test_anonymous_user_cannot_prepare_publish_or_initialize(self):
        self.client._token = ''
        with self.assertRaisesRegex(TemplateError, '先登录'):
            self.client.prepare_publish(self.template)
        with self.assertRaisesRegex(TemplateError, '先登录'):
            self.client.initialize_empty()
        self.assertFalse(self.state.calls)

    def test_redirect_drops_authorization_and_blocks_non_github(self):
        req = request.Request('https://api.github.com/repos/team/demo/releases/assets/17',
                              headers={'Authorization': 'Bearer secret', 'Accept': 'application/octet-stream'})
        handler = github.SafeRedirect()
        redirected = handler.redirect_request(req, None, 302, 'Found', {}, 'https://objects.githubusercontent.com/asset')
        self.assertIsNone(redirected.get_header('Authorization'))
        self.assertEqual(redirected.get_header('Accept'), 'application/octet-stream')
        for url in ('http://objects.githubusercontent.com/asset', 'https://evil.test/asset',
                    'https://objects.githubusercontent.com.evil.test/asset'):
            with self.assertRaises(TemplateError):
                handler.redirect_request(req, None, 302, 'Found', {}, url)

    def test_credentials_precedence_and_no_secret_in_repr(self):
        with patch.dict(os.environ, {'GH_TOKEN': 'one', 'GITHUB_TOKEN': 'two'}):
            self.assertEqual(github.credentials(), ('one', 'GH_TOKEN'))
        self.assertNotIn('sensitive-fixture-token', repr(self.client))


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.target = self.directory / 'new.zip'
        fixture(self.target, 2)
        self.calls = []
        calls = self.calls
        class FakeOMFIT:
            filename = ''
            def saveas(self, path, **options):
                calls.append(('save', path, options))
                fixture(path, 1)
                self.filename = path
            def load(self, path):
                calls.append(('load', path))
                self.filename = path
        self.omfit = FakeOMFIT()
        self.session = OMFITSession(self.omfit)

    def test_open_saves_current_session_before_loading_new_project(self):
        original = self.target.read_bytes()
        backup = self.session.backup_and_open(self.target)
        self.assertTrue(Path(backup).is_file())
        self.assertEqual([call[0] for call in self.calls], ['save', 'load'])
        self.assertEqual(self.calls[0][2], dict(zip=True, quiet=False, skip_save_errors=False))
        self.assertEqual(self.target.read_bytes(), original)

    def test_failed_save_prevents_load(self):
        with patch.object(self.omfit, 'saveas', side_effect=OSError('failed')):
            with self.assertRaises(OSError):
                self.session.backup_and_open(self.target)
        self.assertFalse(self.calls)

    def test_failed_load_attempts_restore_from_backup(self):
        with patch.object(self.omfit, 'load', side_effect=[OSError('bad load'), None]) as load:
            with self.assertRaisesRegex(TemplateError, '已从会话备份恢复'):
                self.session.backup_and_open(self.target)
        self.assertEqual(load.call_count, 2)
        self.assertIn('__before_open_', load.call_args.args[0])

    def test_snapshot_does_not_overwrite_and_worker_calls_are_rejected(self):
        with self.assertRaisesRegex(TemplateError, '已存在'):
            self.session.save_as(self.target)
        errors = []
        def work():
            try:
                self.session.save_as(self.directory / 'snapshot.zip')
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=work)
        worker.start()
        worker.join()
        self.assertEqual(len(errors), 1)
        self.assertIn('主线程', str(errors[0]))


if __name__ == '__main__':
    unittest.main(verbosity=2)
