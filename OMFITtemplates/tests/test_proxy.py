"""Real HTTP CONNECT/TLS tests, plus preference migration and credential isolation."""
import base64
import gc
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import select
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
import warnings
from unittest.mock import patch
from urllib import parse, request

from test_github import APIHandler, APIState
import OMFITlib_template_github as github
import OMFITlib_template_proxy as proxy
from OMFITlib_template_archive import TemplateError


SECRET = 'proxy-test-only:+@'
URL = 'http://omfit:proxy-test-only%3A%2B%40@127.0.0.1:32123'


class ProxyTest(unittest.TestCase):
    def test_new_and_retired_preferences_use_public_proxy_without_credentials(self):
        for saved in (None, {}, [], {'mode': 'relay', 'host': '127.0.0.1', 'port': '12345',
                                    'username': 'omfit', 'script': '/old/script.sh', 'password': SECRET}):
            network = proxy.network_preferences(saved)
            self.assertEqual(network, dict(mode='manual', host='47.102.120.146', port='18889', username=''))
            self.assertEqual(proxy.manual_proxy(network['host'], network['port']), 'http://47.102.120.146:18889')

    def test_existing_manual_system_and_direct_preferences_are_preserved(self):
        for mode in ('manual', 'system', 'direct'):
            network = dict(mode=mode, host='proxy.example', port='3456', username='researcher')
            self.assertEqual(proxy.network_preferences(dict(network, password=SECRET, script='/old.sh')), network)
        self.assertEqual(proxy.connection_label(URL), 'HTTP 代理 127.0.0.1:32123')
        self.assertNotIn(SECRET, proxy.connection_label(URL))

    def test_invalid_urls_are_rejected_without_echoing_credentials(self):
        for value in ('socks5://omfit:secret@localhost:1080', 'http://omfit:secret@localhost:bad',
                      'http://omfit:secret@localhost', 'http://omfit:secret@localhost:123/a'):
            with self.subTest(value=value), self.assertRaises(TemplateError) as caught:
                proxy.normalize_proxy(value)
            self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(proxy.manual_proxy('127.0.0.1', '32123', 'omfit', SECRET), URL)

    def test_direct_and_system_modes_are_distinct_and_environment_is_unchanged(self):
        with patch.dict(os.environ, {'http_proxy': URL, 'HTTPS_PROXY': URL, 'NO_PROXY': '*'}, clear=True):
            original = dict(os.environ)
            self.assertEqual(proxy.login_environment(None), original)
            self.assertFalse(any(key in proxy.login_environment('') for key in proxy.PROXY_ENV_KEYS))
            selected = proxy.login_environment(URL)
            self.assertEqual(selected['https_proxy'], URL)
            self.assertNotIn('NO_PROXY', selected)
            self.assertEqual(dict(os.environ), original)
            self.assertEqual(proxy.proxy_handler('').proxies, {})
            self.assertIn('https', proxy.proxy_handler(None).proxies)

    def test_login_passes_proxy_only_in_child_environment(self):
        with patch.object(github.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name), \
                patch.object(github.subprocess, 'Popen') as launch:
            github.login(proxy=URL)
        self.assertEqual(launch.call_args.kwargs['env']['https_proxy'], URL)
        self.assertNotIn(SECRET, str(launch.call_args.args))
        self.assertNotIn(URL, str(launch.call_args.args))



class TLSHandler(APIHandler):
    def handle_request(self):
        if self.path == '/rate_limit':
            data = b'{"resources":{}}'
            self.send_response(200)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', 'https://objects.githubusercontent.com/after-redirect')
            self.send_header('Content-Length', '0')
            self.end_headers()
        elif self.path == '/after-redirect':
            self.server.redirect_headers = dict(self.headers)
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')
        else:
            super().handle_request()

    do_GET = do_POST = do_PATCH = do_PUT = handle_request


class ConnectHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        self.server.connects.append((self.path, dict(self.headers)))
        if self.headers.get('Proxy-Authorization') != self.server.expected:
            self.send_response(407)
            self.send_header('Proxy-Authenticate', 'Basic realm="fixture"')
            self.end_headers()
            return
        with socket.create_connection(('127.0.0.1', self.server.destination), timeout=5) as target:
            self.send_response(200)
            self.end_headers()
            peers = (self.connection, target)
            while True:
                ready, _, _ = select.select(peers, [], [], 5)
                if not ready:
                    return
                for incoming in ready:
                    content = incoming.recv(65536)
                    if not content:
                        return
                    outgoing = target if incoming is self.connection else self.connection
                    outgoing.sendall(content)


class TunnelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = shutil.which('openssl')
        if executable is None:
            raise unittest.SkipTest('openssl is required for the local TLS fixture')
        cls.temporary = tempfile.TemporaryDirectory()
        directory = Path(cls.temporary.name)
        cls.cert, key = directory / 'cert.pem', directory / 'key.pem'
        subprocess.run([executable, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cls.cert), '-days', '1',
                        '-subj', '/CN=api.github.com', '-addext',
                        'subjectAltName=DNS:api.github.com,DNS:uploads.github.com,DNS:objects.githubusercontent.com'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.cert, key)
        cls.api = ThreadingHTTPServer(('127.0.0.1', 0), TLSHandler)
        cls.api.socket = context.wrap_socket(cls.api.socket, server_side=True)
        cls.proxy = ThreadingHTTPServer(('127.0.0.1', 0), ConnectHandler)
        cls.proxy.destination = cls.api.server_port
        cls.workers = [threading.Thread(target=server.serve_forever, daemon=True)
                       for server in (cls.api, cls.proxy)]
        for worker in cls.workers:
            worker.start()

    @classmethod
    def tearDownClass(cls):
        for server in (cls.proxy, cls.api):
            server.shutdown()
            server.server_close()
        for worker in cls.workers:
            worker.join()
        cls.temporary.cleanup()

    def setUp(self):
        self.api.state = APIState()
        self.proxy.connects = []
        self.proxy.expected = 'Basic ' + base64.b64encode(('omfit:' + SECRET).encode()).decode()
        self.url = URL.replace('32123', str(self.proxy.server_port))
        context = ssl.create_default_context(cafile=str(self.cert))
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.tls = patch.object(ssl, '_create_default_https_context', return_value=context)
        self.tls.start()
        self.addCleanup(self.tls.stop)
        self.environment = patch.dict(os.environ, {'NO_PROXY': '*', 'no_proxy': '*'}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = github.GitHub('team/demo', token='github-test-token', proxy=self.url)

    def test_connect_and_download_redirect_use_proxy_and_keep_auth_separate(self):
        self.assertTrue(self.client.probe()['https_verified'])
        self.assertEqual(self.client.connect()['login'], 'developer')
        self.client._json('/redirect')
        targets = [target for target, _ in self.proxy.connects]
        self.assertIn('api.github.com:443', targets)
        self.assertIn('objects.githubusercontent.com:443', targets)
        for _, headers in self.proxy.connects:
            self.assertEqual(headers['Proxy-Authorization'], self.proxy.expected)
            self.assertNotIn('Authorization', headers)
        for _, _, headers, _ in self.api.state.calls:
            self.assertEqual(headers['Authorization'], 'Bearer github-test-token')
            self.assertNotIn('Proxy-Authorization', headers)
        self.assertNotIn('Authorization', self.api.redirect_headers)
        self.assertNotIn('Proxy-Authorization', self.api.redirect_headers)

    def test_authenticated_proxy_carries_upload_body_unchanged(self):
        content = b'example zip bytes'
        self.api.state.asset_name = 'example.zip'
        with self.client._open('/repos/team/demo/releases/1/assets', 'POST',
                               data=iter([content[:7], content[7:]]), upload=True, size=len(content)) as response:
            self.assertEqual(response.status, 201)
            response.read()
        self.assertEqual(self.api.state.assets[17], content)
        self.assertEqual(self.proxy.connects[0][0], 'uploads.github.com:443')
        self.assertNotIn('Proxy-Authorization', self.api.state.calls[0][2])

    def test_bad_auth_reports_proxy_error_without_secret_or_direct_fallback(self):
        client = github.GitHub('team/demo', token='', proxy=self.url.replace('proxy-test-only', 'wrong-secret'))
        with warnings.catch_warnings(record=True) as resources:
            warnings.simplefilter('always', ResourceWarning)
            with self.assertRaisesRegex(TemplateError, '代理认证失败') as caught:
                client.probe()
            self.assertNotIn('wrong-secret', str(caught.exception))
            del caught
            gc.collect()
        self.assertEqual([str(item.message) for item in resources
                          if issubclass(item.category, ResourceWarning)], [])
        self.assertEqual(self.api.state.calls, [])
        self.assertEqual(len(self.proxy.connects), 1)


if __name__ == '__main__':
    unittest.main()
