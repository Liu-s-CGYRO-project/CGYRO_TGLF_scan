"""Install missing CGYRO archive readers, then compact the open OMFIT project.

Run from the OMFIT Command box. This uses the manager's transactional update
with keep/keep policies, not OMFIT.load() or replacement of the user's project.
All downloads are fixed release assets verified by size and SHA-256.
"""
from builtins import (Exception, OSError, RuntimeError, ValueError, all, any, dict, getattr,
                      globals, isinstance, len, list, print, range, set, str, sum, type)
import hashlib
from http.client import IncompleteRead, RemoteDisconnected
import json
from pathlib import Path, PurePosixPath
import stat
import tempfile
import time
from urllib import error, request
import zipfile

TOOL_VERSION = '1.3.1'
PROJECT_VERSION = '1.24.2'
REPOSITORY = 'Liu-s-CGYRO-project/CGYRO_TGLF_scan'
DEFAULT_PROXY = 'http://47.102.120.146:18889'
PACKAGES = {'code': {'name': 'CGYRO_TGLF_scan_code_only_1.24.2.zip', 'bytes': 995378, 'sha256': '70d6c6cf4cd100c6b6c290d77f67b7dba57ef5397c393b68e0644591caa5f12d'}, 'template': {'name': 'tdxy-liu__cgyro-tglf__1.24.2.omfittpl.zip', 'bytes': 998118, 'sha256': '326050920eac1cff007cdac6d376b81d51da4517ceed2bf140dcc3fa12a8b93d'}}

REQUIRED = {
    (): ('OMFITlib_cgyro_db', 'OMFITlib_cgyro_recover', 'OMFITlib_cgyro_scratch', 'OMFITlib_cgyro_storage', 'OMFITlib_cgyro_storage_files', 'OMFITlib_cgyro_checkpoint', 'OMFITlib_cgyro_continue',
         'OMFITlib_cgyro_results', 'OMFITlib_compare_cgyro_data', 'OMFITlib_compare_series',
         'OMFITlib_compare_status'),
    ('CGYRO_scan',): ('OMFITlib_cgyro_db', 'OMFITlib_cgyro_recover', 'OMFITlib_cgyro_scratch', 'OMFITlib_cgyro_storage', 'OMFITlib_cgyro_storage_files', 'OMFITlib_cgyro_checkpoint',
                    'OMFITlib_cgyro_continue', 'OMFITlib_cgyro_queue'),
}


class HTTPSRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith('https://'):
            raise ValueError('Archive tool download redirected away from HTTPS')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def ready(omfit):
    project = omfit.get('CGYRO_TGLF_scan', {})
    for path, names in REQUIRED.items():
        node = project
        for key in path:
            node = node.get(key, {})
        libraries = node.get('LIB', {})
        if not all(name in libraries for name in names):
            return False
        api = libraries['OMFITlib_cgyro_storage'].importCode(_relLoc=dict(root=node))
        if getattr(api, 'REFERENCE_WALK_VERSION', 0) < 3:
            return False  # Grouped archives need matching plot/resume readers.
        scratch = libraries['OMFITlib_cgyro_scratch'].importCode(_relLoc=dict(root=node))
        if getattr(scratch, 'START_LIMIT_POLICY_VERSION', 0) < 1:
            return False
    return True


def download(kind, destination, proxy):
    package = PACKAGES[kind]
    url = ('https://github.com/' + REPOSITORY + '/releases/download/omfit/tdxy-liu/cgyro-tglf/'
           + PROJECT_VERSION + '/' + package['name'])
    opener = request.build_opener(request.ProxyHandler({} if not proxy else {'http': proxy, 'https': proxy}), HTTPSRedirect())
    for attempt in range(3):
        try:
            print('Downloading verified ' + package['name'] + ' ...')
            with opener.open(request.Request(url, headers={'User-Agent': 'OMFIT-CGYRO-compaction'}), timeout=30) as response:
                data = response.read(package['bytes'] + 1)
            if len(data) != package['bytes'] or hashlib.sha256(data).hexdigest() != package['sha256']:
                raise ValueError('Package size/SHA-256 mismatch; current project unchanged')
            destination.write_bytes(data)
            break
        except (OSError, error.URLError, IncompleteRead, RemoteDisconnected):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    with zipfile.ZipFile(destination) as archive:
        seen, expanded = set(), 0
        for entry in archive.infolist():
            parts = PurePosixPath(entry.filename)
            if (parts.is_absolute() or entry.filename in seen or '\\' in entry.filename
                    or ':' in entry.filename or any(part in ('', '.', '..') for part in parts.parts)
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise ValueError('Unsafe package member')
            expanded += entry.file_size
            seen.add(entry.filename)
        if expanded > 16 * 1024 * 1024 or archive.testzip() is not None:
            raise ValueError('Package expansion/CRC check failed')
    return destination


def install_readers(omfit, proxy):
    from omfit_classes.omfit_base import OMFITtree
    from omfit_classes import OMFITx

    directory = Path(tempfile.mkdtemp(prefix='omfit-cgyro-compact-')).resolve()
    code = download('code', directory / PACKAGES['code']['name'], proxy)
    template = download('template', directory / PACKAGES['template']['name'], proxy)
    # A separate code-only tree supplies a verified updater even when the live
    # project has no manager or has incomplete LIB registrations. This is
    # code-only staging, not a load of a result ZIP over the user's OMFIT.
    incoming = OMFITtree(str(code), quiet=True, developerMode=False)
    manager = incoming['OMFITtemplates']
    context = dict(root=manager)
    live = manager['LIB']['OMFITlib_template_live'].importCode(_relLoc=context)
    session_api = manager['LIB']['OMFITlib_template_session'].importCode(_relLoc=context)
    prepared = live.Prepared(str(template), data_policy='keep', settings_policy='keep')
    # The installed manager and its current window stay under their existing
    # owner; only the scientific project's complete code is updated here.
    prepared.release['roots'] = ['CGYRO_TGLF_scan']
    session = session_api.OMFITSession(omfit, tree_factory=OMFITtree, gui_api=OMFITx)
    plan = session.preview_live(prepared)
    # Add/replace the official readers without removing extra local scripts.
    # Use this session's sentinel: separate native imports have distinct ones.
    plan.operations = [op for op in plan.operations if op['data'] or op['new'] is not session_api.MISSING]
    print('Installing matching project readers with existing inputs, settings and results preserved ...')
    session.apply_live(plan)
    # Compaction changes the data representation. An old-code-only undo after
    # that change could leave indexes without readers, so do not offer it.
    state = getattr(omfit, '_template_live_state', {})
    if state.get('undo', None) is plan:
        state['undo'] = None
    if not ready(omfit):
        raise RuntimeError('Code update did not register all required readers; compaction has not started')
    print('Project readers ready: ' + PROJECT_VERSION)


def compact(omfit, proxy=DEFAULT_PROXY):
    from omfit_classes.omfit_base import OMFITtree

    if not isinstance(omfit, dict):
        raise ValueError('Run this script in the OMFIT Command box')
    if not any(key in omfit for key in ('CGYRO_TGLF_scan', 'CGYRO_scan', 'OUTPUTScan')):
        raise ValueError('No CGYRO project or legacy result branch found; project unchanged')
    if not ready(omfit):
        print('Missing project archive libraries detected; preparing a complete compatible update.')
        install_readers(omfit, proxy)
    node = omfit['CGYRO_TGLF_scan']['CGYRO_scan']
    api = node['LIB']['OMFITlib_cgyro_storage'].importCode(_relLoc=dict(root=node))
    print('Checking checkpoints and hashing/copying retained result files. Large projects can take several minutes ...')
    report = api.consolidate_storage(node, OMFITtree)
    pool, state = api.result_pool(node), api.storage_state(node)
    report['physical_results'] = len([key for key in pool if key != '__FILES__'])
    sizes = state.get('bytes', {})
    report['physical_bytes'] = sum(sizes.get(key, 0) for key in pool if key != '__FILES__')
    file_sizes = state.get('file_bytes', {})
    report['input_zip_bytes'] = sum(file_sizes.get(key, 0) for key in pool.get('__FILES__', {}))
    print('CGYRO compaction completed: ' + json.dumps(report, sort_keys=True))
    print('Checkpoint details: CGYRO_scan / RUN_DB / __STORAGE__ / checkpoints')
    print('Use OMFIT Save As to save a NEW ZIP. Existing ZIPs and server files have not been deleted.')
    return report


if 'OMFIT' in globals():
    _cgyro_compact_report = compact(globals()['OMFIT'], globals().get('COMPACT_PROXY', DEFAULT_PROXY))
elif __name__ == '__main__':
    raise RuntimeError('Execute this script inside the OMFIT Command box; see COMMAND_BOX_COMPACTION.md')
