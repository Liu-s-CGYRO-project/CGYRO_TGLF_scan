"""GitHub HTTP proxies, scoped to one client."""
from builtins import ValueError, any, dict, int, len, str
import base64
from http.client import HTTPSConnection
import os
from urllib import parse, request

from OMFITlib_template_archive import TemplateError

DEFAULT_PROXY_HOST = '47.102.120.146'
DEFAULT_PROXY_PORT = '18889'
PROXY_MODES = {'手动 HTTP 代理': 'manual', '系统代理': 'system', '不使用代理': 'direct'}
PROXY_ENV_KEYS = ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
                  'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY')


def network_preferences(saved=None):
    """Migrate the retired relay mode without carrying over its authentication."""
    defaults = dict(mode='manual', host=DEFAULT_PROXY_HOST, port=DEFAULT_PROXY_PORT, username='')
    if not isinstance(saved, dict) or saved.get('mode', '') not in PROXY_MODES.values():
        return defaults
    return {key: saved.get(key, value) for key, value in defaults.items()}


def normalize_proxy(value):
    """None inherits the system; '' disables proxies; HTTP URLs are explicit."""
    if value is None or value == '':
        return value
    try:
        parts = parse.urlsplit(str(value).strip())
        if (parts.scheme != 'http' or not parts.hostname or parts.port is None
                or not 1 <= parts.port <= 65535 or parts.path not in ('', '/')
                or parts.query or parts.fragment or any(c.isspace() for c in str(value))):
            raise ValueError
        host = parts.hostname.encode('idna').decode('ascii')
        authority = '[' + host + ']' if ':' in host else host
        credentials = ''
        if parts.username is not None:
            username = parse.unquote(parts.username)
            password = parse.unquote(parts.password or '')
            if not username or ':' in username or any(c in username + password for c in '\r\n\x00'):
                raise ValueError
            credentials = parse.quote(username, safe='') + ':' + parse.quote(password, safe='') + '@'
        return 'http://{}{}:{}'.format(credentials, authority, parts.port)
    except (ValueError, UnicodeError):
        raise TemplateError('请填写有效的 HTTP 代理地址和实际端口；不要填写 SSH 地址或 SOCKS5 地址') from None


def connection_label(proxy):
    proxy = normalize_proxy(proxy)
    if proxy is None:
        return '系统代理'
    if proxy == '':
        return '直连'
    parts = parse.urlsplit(proxy)
    host = '[' + parts.hostname + ']' if ':' in parts.hostname else parts.hostname
    return 'HTTP 代理 {}:{}'.format(host, parts.port)


def manual_proxy(host, port, username='', password=''):
    host, port = str(host).strip(), str(port).strip()
    if not host or any(c.isspace() or c in '/?#@' for c in host):
        raise TemplateError('代理主机只填写 IP 或主机名')
    if not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise TemplateError('请填写代理实际监听端口（1–65535）')
    authority = host if host.startswith('[') or ':' not in host else '[' + host + ']'
    credentials = ''
    if username:
        if not password:
            raise TemplateError('请填写代理密码；密码只保留在当前管理器窗口内')
        credentials = parse.quote(str(username), safe='') + ':' + parse.quote(str(password), safe='') + '@'
    return normalize_proxy('http://{}{}:{}'.format(credentials, authority, int(port)))


def login_environment(proxy):
    """Pass settings to the launched gh process, never mutate os.environ."""
    proxy = normalize_proxy(proxy)
    environment = dict(os.environ)
    if proxy is not None:
        for key in PROXY_ENV_KEYS:
            environment.pop(key, None)
        if proxy:
            for key in ('http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
                environment[key] = proxy
    return environment


class ExplicitHTTPProxy(request.ProxyHandler):
    """Use the selected route even if OMFIT inherited NO_PROXY=* from its shell."""
    def __init__(self, proxy):
        parts = parse.urlsplit(normalize_proxy(proxy))
        host = '[' + parts.hostname + ']' if ':' in parts.hostname else parts.hostname
        endpoint = '{}:{}'.format(host, parts.port)
        self._authorization = ''
        if parts.username is not None:
            credentials = parse.unquote(parts.username) + ':' + parse.unquote(parts.password or '')
            self._authorization = 'Basic ' + base64.b64encode(credentials.encode('utf-8')).decode('ascii')
        super().__init__({'http': endpoint, 'https': endpoint})

    def proxy_open(self, req, proxy, protocol):
        if self._authorization:
            # urllib moves this header into CONNECT and removes it from the TLS request.
            req.add_unredirected_header('Proxy-Authorization', self._authorization)
        req.set_proxy(proxy, 'http')
        return None


class ClosingTunnelHTTPSConnection(HTTPSConnection):
    def _tunnel(self):
        # Python 3.9/3.10 can leave CONNECT's response file open on a 407.
        # Retain the standard protocol implementation and close its reader.
        response_factory, response = self.response_class, None

        def capture_response(*args, **kwargs):
            nonlocal response
            response = response_factory(*args, **kwargs)
            return response

        self.response_class = capture_response
        try:
            return super()._tunnel()
        finally:
            self.response_class = response_factory
            if response is not None:
                response.close()


class ClosingTunnelHTTPSHandler(request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(ClosingTunnelHTTPSConnection, req, context=self._context)


def proxy_handler(proxy):
    proxy = normalize_proxy(proxy)
    if proxy is None:
        return request.ProxyHandler()
    return request.ProxyHandler({}) if proxy == '' else ExplicitHTTPProxy(proxy)
