"""Install/open only OMFITtemplates from an OMFIT Command box.

Published as omfit-manager-bootstrap.py with a fixed manager version and digest.
The current project is never loaded from a ZIP or replaced by this bootstrap.
"""
from builtins import (Exception, RuntimeError, ValueError, any, bool, bytes, dict, getattr,
                      globals, int, isinstance, len, list, open, print, range, set, str, tuple, type)
import ast
import copy
import hashlib
from http.client import IncompleteRead, RemoteDisconnected
import io
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import time
from urllib import error, parse, request
import zipfile

MANAGER = None  # Filled by build_bootstrap.py in the published asset.
REPOSITORY = 'Liu-s-CGYRO-project/CGYRO_TGLF_scan'
DEFAULT_PROXY = 'http://47.102.120.146:18889'


class HTTPSRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('Manager download redirected away from HTTPS')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(proxy):
    if not isinstance(MANAGER, dict) or MANAGER.get('repository') != REPOSITORY:
        raise ValueError('Use the published omfit-manager-bootstrap.py release asset')
    url = ('https://github.com/' + REPOSITORY + '/releases/download/omfit-manager/v2/'
           + parse.quote(MANAGER['version'], safe='') + '/' + parse.quote(MANAGER['name'], safe=''))
    opener = request.build_opener(request.ProxyHandler({} if not proxy else {'http': proxy, 'https': proxy}), HTTPSRedirect())
    for attempt in range(3):
        try:
            print('Downloading OMFIT manager ' + MANAGER['version'] + ' ...')
            with opener.open(request.Request(url, headers={'User-Agent': 'OMFIT-manager-bootstrap'}), timeout=30) as response:
                data = response.read(MANAGER['bytes'] + 1)
            if len(data) != MANAGER['bytes'] or hashlib.sha256(data).hexdigest() != MANAGER['sha256']:
                raise ValueError('Manager package size/SHA-256 mismatch; current project unchanged')
            return data
        except (OSError, error.URLError, IncompleteRead, RemoteDisconnected):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def extract(data, directory):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None:
            raise ValueError('Manager ZIP failed CRC verification')
        names, total = set(), 0
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if (entry.filename in names or path.is_absolute() or path.parts[0] != 'OMFITtemplates'
                    or any(part in ('', '.', '..') for part in path.parts) or '\\' in entry.filename
                    or ':' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('Unsafe/duplicate manager ZIP member')
            names.add(entry.filename)
            total += entry.file_size
            if total > 12 * 1024 * 1024:
                raise ValueError('Manager ZIP expands beyond its size limit')
            target = directory.joinpath(*path.parts)
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open('xb') as writer:
                shutil.copyfileobj(source, writer)
        if 'OMFITtemplates/OMFITsave.txt' not in names:
            raise ValueError('Manager module entry is missing')
    return directory / 'OMFITtemplates'


def existing_version(module):
    try:
        node = module['LIB']['OMFITlib_template_versions']
        source = Path(node.filename).read_text(encoding='utf-8-sig')
        for item in ast.parse(source).body:
            if isinstance(item, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'MANAGER_VERSION' for target in item.targets):
                return tuple(int(part) for part in ast.literal_eval(item.value).split('.'))
    except (AttributeError, KeyError, OSError, TypeError, ValueError, SyntaxError):
        pass
    return ()


def install(omfit, proxy=DEFAULT_PROXY):
    if not isinstance(omfit, dict):
        raise ValueError('Execute this script inside the OMFIT Command box')
    from omfit_classes.omfit_base import OMFITmodule
    import tkinter as tk

    previous = dict.get(omfit, 'OMFITtemplates', None)
    if previous is not None and not any(base.__name__ == 'OMFITmodule' for base in type(previous).__mro__):
        raise ValueError('OMFITtemplates is occupied by a non-module node; project unchanged')
    parent = tk._default_root
    window = getattr(parent, '_omfit_template_manager', None) if parent is not None else None
    if window is not None and window.alive and window.busy:
        raise ValueError('The existing manager is busy; finish its current operation and run again')
    if previous is not None and MANAGER and existing_version(previous) >= tuple(int(part) for part in MANAGER['version'].split('.')):
        if window is not None and window.alive:
            window.close()
        previous['GUIS']['main'].run()
        return

    data = fetch(proxy)
    directory = Path(tempfile.mkdtemp(prefix='omfit-manager-bootstrap-')).resolve()
    directory.relative_to(Path(tempfile.gettempdir()).resolve())
    attached = False
    try:
        module_dir = extract(data, directory)
        current = OMFITmodule(str(module_dir / 'OMFITsave.txt'), quiet=True, developerMode=False)
        if current['SETTINGS']['MODULE'].get('ID', '') != 'OMFITtemplates' or 'main' not in current.get('GUIS', {}):
            raise ValueError('The downloaded package is not OMFITtemplates')
        if previous is not None:
            for name, value in previous.get('SETTINGS', {}).items():
                if name != 'MODULE':
                    current['SETTINGS'][name] = copy.deepcopy(value)
        current.filename = ''
        if window is not None and window.alive:
            window.close()
        omfit['OMFITtemplates'] = current
        attached = True
        current['GUIS']['main'].run()
        storage = getattr(omfit, '_template_bootstrap_storage', None)
        if storage is None:
            storage = []
            omfit._template_bootstrap_storage = storage
        storage.append(str(directory))  # Retain backing files until normal project save.
        print('Manager ready. Select a project release, preview, then update the current project.')
    except Exception:
        if attached:
            if previous is None:
                del omfit['OMFITtemplates']
            else:
                omfit['OMFITtemplates'] = previous
                try:
                    previous['GUIS']['main'].run()
                except Exception:
                    print('The previous manager module was restored; reopen its main GUI manually.')
        shutil.rmtree(str(directory), ignore_errors=True)
        raise


if 'OMFIT' in globals():
    install(globals()['OMFIT'], globals().get('BOOTSTRAP_PROXY', DEFAULT_PROXY))
elif __name__ == '__main__':
    raise RuntimeError('Run the published script from the OMFIT Command box; see FIRST_DEPLOY.md')
