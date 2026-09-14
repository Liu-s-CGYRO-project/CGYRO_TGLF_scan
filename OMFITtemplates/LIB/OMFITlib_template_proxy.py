"""GitHub HTTP proxies and the existing SSH relay script, scoped to one client."""
from builtins import ValueError, any, dict, int, len, str
import base64
from http.client import HTTPSConnection
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib import parse, request

from OMFITlib_template_archive import TemplateError, parse_json

DEFAULT_RELAY = 'liu@47.102.120.146:22 → 127.0.0.1:18888'
PROXY_MODES = {'SSH 隧道 · 47.102.120.146': 'relay', '系统代理': 'system',
               '手动 HTTP 代理': 'manual', '不使用代理': 'direct'}
PROXY_ENV_KEYS = ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
                  'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY')
RELAY_ENV_KEYS = ('OMFIT_GITHUB_RELAY_PORT',) + PROXY_ENV_KEYS


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


def relay_proxy(environment=None):
    """Read the relay's dynamic loopback port and authentication from its script."""
    environment = os.environ if environment is None else environment
    port = str(environment.get('OMFIT_GITHUB_RELAY_PORT', '')).strip()
    if not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise TemplateError('尚未读取 SSH 中继端口。请加载已有连接脚本，或在运行该脚本的同一终端启动 OMFIT。')
    value = next((environment.get(key, '') for key in ('https_proxy', 'HTTPS_PROXY', 'http_proxy', 'HTTP_PROXY')
                  if environment.get(key, '')), '')
    if not value:
        raise TemplateError('连接脚本尚未提供 http_proxy / https_proxy 及代理认证信息')
    value = normalize_proxy(value)
    parts = parse.urlsplit(value)
    if parts.hostname not in ('127.0.0.1', 'localhost', '::1') or parts.port != int(port):
        raise TemplateError('脚本代理地址与 OMFIT_GITHUB_RELAY_PORT 不一致，请重新加载连接脚本')
    if parse.unquote(parts.username or '') != 'omfit' or not parts.password:
        raise TemplateError('脚本未提供 omfit 用户的代理认证，请在原连接脚本中检查密码读取配置')
    return value


def load_relay_script(path):
    """Explicit user action: source their script and capture only relay variables."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise TemplateError('请选择已有的 Linux SSH 中继连接脚本')
    executable = shutil.which('bash')
    if not executable:
        raise TemplateError('加载 SSH 中继脚本需要 Linux bash')
    capture = 'import json,os;print(json.dumps({k:os.environ.get(k, "") for k in ' + repr(RELAY_ENV_KEYS) + '}))'
    # Arguments remain separate; filenames and script contents never become shell text.
    command = [executable, '-c',
               'readonly omfit_proxy_script="$1" omfit_proxy_python="$2" omfit_proxy_capture="$3"; set --; '
               'source "$omfit_proxy_script" >/dev/null && export ' + ' '.join(RELAY_ENV_KEYS)
               + ' && "$omfit_proxy_python" -c "$omfit_proxy_capture"',
               'omfit-relay', str(source), sys.executable, capture]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=30, check=False)
        if result.returncode or len(result.stdout) > 65536:
            raise TemplateError('连接脚本未完成。若需要 SSH 交互登录，请先在终端加载脚本，再从同一终端启动 OMFIT。')
        try:
            environment = parse_json(result.stdout)
        except TemplateError:
            raise TemplateError('连接脚本未返回有效的中继环境') from None
        if not isinstance(environment, dict):
            raise TemplateError('连接脚本未返回有效的中继环境')
        relay_proxy(environment)
        return environment
    except (OSError, subprocess.TimeoutExpired):
        raise TemplateError('加载连接脚本失败或超时；请在终端检查 SSH 连接后重试') from None


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
