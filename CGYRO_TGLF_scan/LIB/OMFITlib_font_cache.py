"""Shared original-font cache, independent of Tk, Matplotlib and GitHub API.

Keep this stdlib-only library identical in the standalone manager. Public
HTTPS asset links need no REST requests or access tokens. Files are published
into the cache only after archive and individual-file verification.
"""
from builtins import all, any, dict, getattr, int, isinstance, len, min, next, open, set, sorted, str, tuple
import base64
import hashlib
from http.client import HTTPSConnection, IncompleteRead, RemoteDisconnected
import json
import os
from pathlib import Path
import ssl
import tempfile
import threading
from time import monotonic
from urllib import error, parse, request
import zipfile
from OMFITlib_font_manifest import FONT_BUNDLES, FONT_FILES

_directory = None
_proxy = Ellipsis
_checked = {}
_lock = threading.RLock()
_download_lock = threading.RLock()


class FontError(RuntimeError):
    pass


class FontCancelled(FontError):
    pass


class _Interrupted(FontError):
    pass


def _cancelled(cancel):
    if cancel is not None and cancel.is_set():
        raise FontCancelled('Font download cancelled; existing files are unchanged.')


def cache_directory():
    global _directory
    with _lock:
        if _directory is None:
            base = os.environ.get('XDG_CACHE_HOME') or os.environ.get('LOCALAPPDATA') or ''
            base = Path(base) if base and Path(base).is_absolute() else Path.home() / '.cache'
            directory = base / 'omfit-cgyro' / 'fonts'
            try:
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            except OSError:
                directory = Path(tempfile.mkdtemp(prefix='omfit-font-cache-'))
            _directory = directory
        return _directory


def set_proxy(proxy):
    """None uses system proxies; '' is direct; otherwise use an HTTP proxy."""
    global _proxy
    _proxy = proxy


def _selected_proxy():
    if _proxy is not Ellipsis:
        return _proxy
    config = os.environ.get('XDG_CONFIG_HOME', '')
    base = Path(config) if config and Path(config).is_absolute() else Path.home() / '.config'
    paths = (base / 'omfit-template-manager/settings.json', Path.home() / '.omfit-template-manager.json')
    for path in paths:
        if not path.is_file():
            continue
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            network = saved.get('network', {}) if isinstance(saved, dict) else {}
            if not isinstance(network, dict):
                raise ValueError
            mode = network.get('mode', 'manual')
            if mode == 'direct':
                return ''
            if mode == 'system':
                return None
            if network.get('username', ''):
                raise FontError('Open font settings from Template Manager to use the authenticated proxy.')
            host, port = str(network.get('host', '47.102.120.146')), int(network.get('port', 18889))
            if not host or any(char.isspace() or char in '/?#@' for char in host) or not 1 <= port <= 65535:
                raise ValueError
            host = '[' + host + ']' if ':' in host and not host.startswith('[') else host
            return 'http://{}:{}'.format(host, port)
        except (OSError, ValueError, TypeError):
            raise FontError('Cannot read the saved proxy settings. Open Template Manager network settings.') from None
    if request.getproxies().get('https', ''):
        return None
    return 'http://47.102.120.146:18889'


class _ExplicitProxy(request.ProxyHandler):
    def __init__(self, proxy):
        parts = parse.urlsplit(proxy)
        try:
            if parts.scheme != 'http' or not parts.hostname or not 1 <= parts.port <= 65535 or parts.path not in ('', '/') or parts.query or parts.fragment:
                raise ValueError
        except (ValueError, TypeError):
            raise FontError('The font downloader needs a valid HTTP proxy URL.') from None
        host = '[' + parts.hostname + ']' if ':' in parts.hostname else parts.hostname
        endpoint = '{}:{}'.format(host, parts.port)
        self.authorization = ''
        if parts.username is not None:
            credentials = parse.unquote(parts.username) + ':' + parse.unquote(parts.password or '')
            self.authorization = 'Basic ' + base64.b64encode(credentials.encode('utf-8')).decode('ascii')
        super().__init__({'http': endpoint, 'https': endpoint})

    def proxy_open(self, req, proxy, protocol):
        if self.authorization:
            req.add_unredirected_header('Proxy-Authorization', self.authorization)
        req.set_proxy(proxy, 'http')
        return None


class _Redirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = parse.urlsplit(newurl)
        if (parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443)
                or not (parts.hostname == 'github.com' or (parts.hostname or '').endswith('.githubusercontent.com'))):
            raise FontError('Unsupported redirect from the font download server.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _ClosingTunnel(HTTPSConnection):
    def _tunnel(self):
        # Close CONNECT's response reader even on a proxy authentication error
        # (Python 3.9/3.10 can otherwise retain the socket).
        factory, response = self.response_class, None

        def capture(*args, **kwargs):
            nonlocal response
            response = factory(*args, **kwargs)
            return response

        self.response_class = capture
        try:
            return super()._tunnel()
        finally:
            self.response_class = factory
            if response is not None:
                response.close()


class _HTTPS(request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_ClosingTunnel, req, context=self._context)


def _hash_file(path, cancel=None):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            _cancelled(cancel)
            chunk = stream.read(256 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _font_path(name):
    asset = FONT_FILES[name]
    return cache_directory() / (asset['sha256'] + Path(name).suffix)


def _valid_font(name, verify=True):
    path = _font_path(name)
    asset = FONT_FILES[name]
    try:
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns)
        if stat.st_size != asset['bytes']:
            return False
        with _lock:
            if _checked.get(name, None) == key:
                return True
        if not verify:
            return False
        if _hash_file(path) != asset['sha256']:
            return False
        with _lock:
            _checked[name] = key
        return True
    except OSError:
        return False


def cached_fonts(kind, verify=True):
    """Reuse matching files; verify=False never hashes on the GUI thread."""
    if kind not in FONT_BUNDLES:
        raise FontError('Unknown font pack: ' + str(kind))
    names = FONT_BUNDLES[kind]['fonts']
    return {name: str(_font_path(name)) for name in names} if all(_valid_font(name, verify) for name in names) else None


def font_cache_status(kind):
    """A cheap display hint; actual font use still requires SHA verification."""
    if cached_fonts(kind, verify=False) is not None:
        return 'verified'
    try:
        if all(_font_path(name).stat().st_size == FONT_FILES[name]['bytes'] for name in FONT_BUNDLES[kind]['fonts']):
            return 'on disk; checked when used'
    except OSError:
        pass
    return 'not downloaded'


def _download(kind, path, progress, cancel):
    pack = FONT_BUNDLES[kind]
    proxy = _selected_proxy()
    handler = request.ProxyHandler() if proxy is None else _ExplicitProxy(proxy) if proxy else request.ProxyHandler({})
    opener = request.build_opener(handler, _HTTPS(), _Redirect())
    for attempt in (1, 2, 3):
        _cancelled(cancel)
        if progress:
            progress('Connecting: ' + pack['filename'] + (' (retry {})'.format(attempt) if attempt > 1 else ''), 0, pack['bytes'])
        digest, done, next_report = hashlib.sha256(), 0, 0.0
        try:
            req = request.Request(pack['url'], headers={'User-Agent': 'OMFIT-Fonts/1', 'Accept': 'application/octet-stream'})
            try:
                response = opener.open(req, timeout=30)
            except error.HTTPError as exc:
                status = exc.code
                exc.close()
                raise FontError('Font download returned HTTP {}. Retry later or import the offline font ZIP.'.format(status)) from None
            except (error.URLError, OSError, IncompleteRead, RemoteDisconnected) as exc:
                if isinstance(getattr(exc, 'reason', exc), ssl.SSLCertVerificationError):
                    raise FontError('Font HTTPS certificate verification failed. Check certificates and proxy settings.') from None
                raise _Interrupted from None
            with response, open(path, 'wb') as output:
                read = getattr(response, 'read1', response.read)
                while True:
                    _cancelled(cancel)
                    try:
                        chunk = read(min(65536, pack['bytes'] + 1 - done))
                    except (error.URLError, OSError, IncompleteRead, RemoteDisconnected):
                        raise _Interrupted from None
                    _cancelled(cancel)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > pack['bytes']:
                        raise FontError('Font download exceeds the declared size.')
                    output.write(chunk)
                    digest.update(chunk)
                    now = monotonic()
                    if progress and (now >= next_report or done == pack['bytes']):
                        progress('Downloading: ' + pack['filename'], done, pack['bytes'])
                        next_report = now + 0.1
            if done != pack['bytes']:
                raise _Interrupted
        except _Interrupted:
            if attempt == 3:
                raise FontError('Font connection interrupted or timed out after 3 attempts. Retry or import the offline ZIP.') from None
            if progress:
                progress('Connection interrupted; retrying...', 0, pack['bytes'])
            if cancel is not None:
                cancel.wait(attempt)
            else:
                threading.Event().wait(attempt)
            continue
        if digest.hexdigest() != pack['sha256']:
            raise FontError('Font archive SHA-256 mismatch; nothing was installed.')
        return


def _install(path, kind, cancel=None, progress=None):
    pack = FONT_BUNDLES[kind]
    if path.stat().st_size != pack['bytes'] or _hash_file(path, cancel) != pack['sha256']:
        raise FontError('The font ZIP size or SHA-256 does not match this version.')
    if progress:
        progress('Verifying and caching fonts...', 0, 0)
    try:
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix='.stage-', dir=cache_directory()) as temporary:
            entries = archive.infolist()
            if len(entries) != len(pack['members']) or {item.filename for item in entries} != set(pack['members']):
                raise FontError('Unexpected or duplicate font archive members.')
            staged = []
            for item in entries:
                _cancelled(cancel)
                expected = pack['members'][item.filename]
                if item.is_dir() or item.file_size != expected['bytes'] or Path(item.filename).name != item.filename or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise FontError('Invalid font archive member.')
                stage = Path(temporary) / item.filename
                digest, size = hashlib.sha256(), 0
                with archive.open(item) as source, open(stage, 'wb') as output:
                    while True:
                        _cancelled(cancel)
                        chunk = source.read(65536)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > expected['bytes']:
                            raise FontError('Unpacked font exceeds the declared size.')
                        output.write(chunk)
                        digest.update(chunk)
                if size != expected['bytes'] or digest.hexdigest() != expected['sha256']:
                    raise FontError('Unpacked font SHA-256 mismatch.')
                target = _font_path(item.filename) if item.filename in pack['fonts'] else cache_directory() / 'licenses' / kind / item.filename
                staged.append((stage, target))
            # Publish only after every member has passed verification.
            _cancelled(cancel)
            for stage, target in staged:
                _cancelled(cancel)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.replace(stage, target)
    except (zipfile.BadZipFile, EOFError):
        raise FontError('Invalid font ZIP; existing cached fonts were preserved.') from None
    result = cached_fonts(kind)
    if result is None:
        raise FontError('Font cache verification did not finish.')
    return result


def ensure_cached_fonts(kind, progress=None, cancel=None):
    with _download_lock:
        _cancelled(cancel)
        cached = cached_fonts(kind)
        if cached is not None:
            return cached
        with tempfile.TemporaryDirectory(prefix='.download-', dir=cache_directory()) as temporary:
            path = Path(temporary) / FONT_BUNDLES[kind]['filename']
            _download(kind, path, progress, cancel)
            _cancelled(cancel)
            return _install(path, kind, cancel, progress)


def import_font_pack(path, progress=None, cancel=None):
    """Import a pinned offline ZIP; do not trust its filename or manifest."""
    path = Path(path).expanduser().resolve(strict=True)
    size = path.stat().st_size
    if not any(size == pack['bytes'] for pack in FONT_BUNDLES.values()):
        raise FontError('This is not a supported original-font ZIP for this version.')
    digest = _hash_file(path, cancel)
    kind = next((key for key, pack in FONT_BUNDLES.items() if size == pack['bytes'] and digest == pack['sha256']), None)
    if kind is None:
        raise FontError('This is not a supported original-font ZIP for this version.')
    with _download_lock:
        return kind, _install(path, kind, cancel, progress)
