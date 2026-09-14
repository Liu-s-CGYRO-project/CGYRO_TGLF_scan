"""Manager-only update checks and integrity validation against the real HTTP fixture."""
import copy
import hashlib
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'LIB'))
from OMFITlib_template_archive import TemplateError
from OMFITlib_template_github import GitHub
from OMFITlib_template_manager_update import check_manager_update, download_manager_package, package_names
from OMFITlib_template_service import Cancelled
from test_github import APIHandler, APIState, LocalOpener


class ManagerUpdateTest(unittest.TestCase):
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
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.state = APIState()
        self.server.state = self.state
        self.client = GitHub('team/demo', token='', cancel=threading.Event())
        self.client.opener = LocalOpener(self.server.server_port)

    def seed(self, version='1.4.0'):
        data = b'MANAGER-PACKAGE-INTEGRITY-FIXTURE'
        self.state.assets[17] = data
        assets = [dict(id=17, name=name, state='uploaded', size=len(data),
                       digest='sha256:' + hashlib.sha256(data).hexdigest()) for name in package_names(version).values()]
        release = dict(id=5, tag_name='omfit-manager/v' + version, draft=False, prerelease=False,
                       body='Manager changes', assets=assets, html_url='https://untrusted.example/')
        self.state.releases.append(release)
        return release

    def test_independent_semantic_versions_not_api_order_or_project_tags(self):
        self.seed('1.9.0')
        self.seed('1.10.0')
        self.seed('2.0.0')['draft'] = True
        self.seed('1.11.0')['prerelease'] = True
        self.seed('3.0.0-rc.1')
        self.seed('9.0.0')['tag_name'] = 'omfit/author/project/9.0.0'
        result = check_manager_update(self.client, '1.4.0')
        self.assertEqual(result['latest'], '1.10.0')
        self.assertTrue(result['available'])
        self.assertEqual(set(result['packages']), {'linux', 'omfit'})
        self.assertTrue(result['url'].startswith('https://github.com/team/demo/releases/tag/'))
        self.assertTrue(all(call[0] == 'GET' for call in self.state.calls))
        self.assertFalse(any('Authorization' in call[2] for call in self.state.calls))

    def test_current_ahead_and_no_independent_release_are_distinguished(self):
        self.assertEqual(check_manager_update(self.client)['latest'], '')
        self.seed()
        self.assertFalse(check_manager_update(self.client, '1.4.0')['available'])
        self.assertFalse(check_manager_update(self.client, '1.5.0')['available'])
        self.assertTrue(check_manager_update(self.client, '1.3.1')['available'])

    def test_incomplete_assets_are_not_offered_as_verified_downloads(self):
        release = self.seed()
        release['assets'][0]['digest'] = ''
        result = check_manager_update(self.client, '1.3.1')
        self.assertTrue(result['available'])
        self.assertEqual(set(result['packages']), {'omfit'})

    def test_download_is_verified_and_never_overwrites_an_existing_file(self):
        self.seed()
        package = check_manager_update(self.client)['packages']['linux']
        output = self.directory / package['name']
        self.assertEqual(download_manager_package(self.client, package, output), str(output))
        self.assertEqual(output.read_bytes(), self.state.assets[17])
        with self.assertRaises(TemplateError):
            download_manager_package(self.client, package, output)
        self.assertFalse(list(self.directory.glob('*.partial')))

    def test_bad_digest_truncation_cancel_and_changed_source_leave_no_file(self):
        self.seed()
        package = check_manager_update(self.client)['packages']['linux']
        output = self.directory / package['name']
        for changes in ({'sha256': 'a' * 64}, {'size': package['size'] + 1},
                        {'size': package['size'] - 1}, {'repository': 'other/repo'}):
            with self.assertRaises(TemplateError):
                download_manager_package(self.client, dict(package, **changes), output)
            self.assertFalse(list(self.directory.iterdir()))
        self.client.cancel.set()
        with self.assertRaises(Cancelled):
            download_manager_package(self.client, package, output)
        self.assertFalse(list(self.directory.iterdir()))


if __name__ == '__main__':
    unittest.main()
