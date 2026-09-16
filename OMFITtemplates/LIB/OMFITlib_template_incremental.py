"""Verified file-level manager updates staged outside the running installation."""
from builtins import all, any, bool, bytearray, bytes, dict, int, len, list, max, min, open, set, sorted, str, sum, tuple, type
import ast
import gzip
import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from OMFITlib_template_archive import TemplateError, json_bytes, parse_json, parse_tree, safe_name
from OMFITlib_template_paths import xdg_path
from OMFITlib_template_service import check_cancel
from OMFITlib_template_versions import semantic_version

FORMAT = 'omfit-manager-files-v1'
MAX_MANIFEST = 512 * 1024
MAX_FILE = 8 * 1024 ** 2
MAX_TOTAL = 128 * 1024 ** 2
RECEIPT = '.omfit-manager-install.json'


def manifest_name(version):
    return 'omfit-manager-' + version + '.files.json'


def update_directory():
    return xdg_path('XDG_DATA_HOME', '.local/share') / 'omfit-template-manager' / 'updates'


def verified_asset(asset, repo):
    try:
        size, identity = int(asset['size']), int(asset['id'])
        digest = str(asset.get('digest', ''))
        if (asset.get('state') == 'uploaded' and 0 < size <= MAX_TOTAL and identity > 0
                and re.fullmatch(r'sha256:[a-f0-9]{64}', digest)):
            return dict(name=asset['name'], size=size, asset_id=identity, sha256=digest[7:], repository=repo)
    except (KeyError, TypeError, ValueError):
        pass
    return None


def validate_manifest(manifest, version):
    if not isinstance(manifest, dict) or manifest.get('format') != FORMAT or manifest.get('version') != version:
        raise TemplateError('增量更新清单格式或版本不匹配')
    key = semantic_version(version)
    files = manifest.get('files')
    if key is None or key[3] != 1 or not isinstance(files, dict) or not 1 <= len(files) <= 256:
        raise TemplateError('增量更新文件清单无效')
    total = 0
    for name, spec in files.items():
        if (safe_name(name) != name or '\\' in name or ':' in name or name.endswith('/')
                or not (name.startswith('OMFITtemplates/') or name in ('README.md', 'SHA256SUMS.json', 'start_manager.sh', 'install_desktop.sh'))):
            raise TemplateError('增量更新包含管理器之外的路径：' + name)
        if (not isinstance(spec, dict) or type(spec.get('size')) is not int or not 0 <= spec['size'] <= MAX_FILE
                or spec.get('mode') not in (0o644, 0o755) or not re.fullmatch(r'[a-f0-9]{64}', str(spec.get('sha256', '')))
                or spec.get('asset') != 'omfit-file-' + spec['sha256'] + '.gz'):
            raise TemplateError('增量文件信息无效：' + name)
        total += spec['size']
    required = {'OMFITtemplates/OMFITsave.txt', 'OMFITtemplates/SettingsNamelist.txt', 'OMFITtemplates/launch.py',
                'OMFITtemplates/GUIS/main.py', 'OMFITtemplates/LIB/OMFITlib_template_versions.py'}
    if total > MAX_TOTAL or not required <= set(files):
        raise TemplateError('增量更新内容不完整或超过限制')
    return manifest


def file_matches(path, spec):
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != spec['size']:
            return False
        with path.open('rb') as stream:
            return hashlib.sha256(stream.read(MAX_FILE + 1)).hexdigest() == spec['sha256']
    except OSError:
        return False


def _read_asset(client, asset, limit, label):
    if asset.get('repository') != client.repo or not 0 < int(asset['size']) <= limit:
        raise TemplateError('增量更新来源或附件大小无效')
    data = bytearray()
    with client._open(client.base + '/releases/assets/' + str(int(asset['asset_id'])), accept='application/octet-stream') as response:
        while True:
            check_cancel(client.cancel)
            chunk = response.read(min(64 * 1024, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > asset['size']:
                raise TemplateError('增量下载超过声明大小：' + label)
    check_cancel(client.cancel)
    if len(data) != asset['size'] or hashlib.sha256(data).hexdigest() != asset['sha256']:
        raise TemplateError('增量下载校验失败：' + label)
    return bytes(data)


def plan_incremental(client, release, module_dir, source_overrides=None):
    descriptor = release.get('incremental')
    if not descriptor:
        return None
    raw = _read_asset(client, descriptor['manifest'], MAX_MANIFEST, '文件清单')
    manifest = validate_manifest(parse_json(raw), release['latest'])
    sources, changed, reused, assets = {}, [], [], {}
    module_dir = Path(module_dir).resolve()
    source_overrides = source_overrides or {}
    remote = descriptor['assets']
    for name, spec in manifest['files'].items():
        check_cancel(client.cancel)
        path = source_overrides.get(name, module_dir / name[len('OMFITtemplates/'):] if name.startswith('OMFITtemplates/') else module_dir.parent / name)
        if file_matches(path, spec):
            sources[name] = str(path)
            reused.append(name)
        else:
            asset = remote.get(spec['asset'])
            if not asset:
                raise TemplateError('增量附件不完整：' + name)
            assets[spec['asset']] = asset
            changed.append(name)
    return dict(version=release['latest'], manifest=manifest, manifest_sha256=hashlib.sha256(raw).hexdigest(),
                sources=sources, changed=sorted(changed), reused=sorted(reused), assets=assets,
                download_bytes=sum(item['size'] for item in assets.values()), total_files=len(manifest['files']))


def _source_version(data):
    """Read the packaged version literal without importing downloaded code."""
    try:
        tree = ast.parse(data)
        values = [node.value for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == 'MANAGER_VERSION' for target in node.targets)]
        if len(values) != 1:
            raise ValueError('MANAGER_VERSION must occur once')
        version = ast.literal_eval(values[0])
        if not isinstance(version, str) or semantic_version(version) is None:
            raise ValueError('MANAGER_VERSION must be a version string')
        return version
    except (SyntaxError, ValueError, TypeError, UnicodeError) as exc:
        raise TemplateError('管理器版本文件无效，不能确认安装版本') from exc


def _verify_tree(directory, manifest):
    files = manifest['files']
    for name, spec in files.items():
        if not file_matches(directory / name, spec):
            raise TemplateError('管理器文件校验失败：' + name)
    module = directory / 'OMFITtemplates'
    rows = parse_tree((module / 'OMFITsave.txt').read_bytes())
    settings = 'SettingsNamelist.txt'
    for row in rows:
        if row.ref:
            ref = row.ref[2:] if row.ref.startswith('./') else row.ref
            if 'OMFITtemplates/' + safe_name(ref) not in files:
                raise TemplateError('管理器树引用缺失：' + row.ref)
            if row.keys == ('SETTINGS',):
                if row.kind != 'OMFITsettings':
                    raise TemplateError('管理器设置节点类型不匹配')
                settings = ref
    identity = parse_json((module / settings).read_bytes()).get('MODULE', {})
    if identity.get('ID') != 'OMFITtemplates':
        raise TemplateError('管理器模块标识不匹配')
    version = _source_version((module / 'LIB/OMFITlib_template_versions.py').read_bytes())
    if version != manifest['version']:
        raise TemplateError('管理器代码版本与更新清单不匹配：{} / {}'.format(version, manifest['version']))


def install_incremental(client, plan, directory=None):
    """Build a complete new version using local bytes plus downloaded changes."""
    manifest = validate_manifest(plan['manifest'], plan['version'])
    directory = Path(directory) if directory is not None else update_directory()
    versions = directory / 'versions'
    versions.mkdir(parents=True, exist_ok=True, mode=0o700)
    # A fresh directory avoids modifying running scripts, custom files or an
    # installation another manager window may currently be preparing.
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=versions) as temporary:
        stage = Path(temporary)
        blobs = {}
        done, total = 0, plan['download_bytes']
        for name, spec in manifest['files'].items():
            check_cancel(client.cancel)
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if name in plan['sources']:
                source = Path(plan['sources'][name])
                if not file_matches(source, spec):
                    raise TemplateError('预览后本地文件已变化，请重新检查更新：' + name)
                shutil.copyfile(source, target)
            else:
                key = spec['asset']
                if key not in blobs:
                    compressed = _read_asset(client, plan['assets'][key], MAX_FILE + 65536, name)
                    # Bounded streaming decompression rejects oversized and
                    # concatenated gzip payloads without extracting paths.
                    import io
                    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                        data = stream.read(spec['size'] + 1)
                    if len(data) != spec['size'] or hashlib.sha256(data).hexdigest() != spec['sha256']:
                        raise TemplateError('增量文件内容校验失败：' + name)
                    blobs[key] = data
                    done += len(compressed)
                    if client.progress:
                        client.progress('正在下载变更文件', done, total)
                target.write_bytes(blobs[key])
            target.chmod(spec['mode'])
        _verify_tree(stage, manifest)
        check_cancel(client.cancel)
        receipt = dict(manifest=manifest, manifest_sha256=plan['manifest_sha256'])
        (stage / RECEIPT).write_bytes(json_bytes(receipt))
        destination = versions / (plan['version'] + '-' + uuid.uuid4().hex[:12])
        os.rename(stage, destination)
    return str(destination)


def verify_installation(path, directory=None):
    directory = (Path(directory) if directory is not None else update_directory()).resolve()
    path = Path(path)
    if path.is_symlink() or path.resolve().parent != directory / 'versions':
        raise TemplateError('管理器安装位置无效')
    receipt = parse_json((path / RECEIPT).read_bytes())
    manifest = receipt['manifest']
    validate_manifest(manifest, manifest['version'])
    _verify_tree(path, manifest)
    return path


def activate_installation(path, directory=None):
    directory = Path(directory) if directory is not None else update_directory()
    path = verify_installation(path, directory)
    state = directory / 'active.json'
    previous = state.read_bytes() if state.exists() else None
    temporary = state.with_name('.active-' + uuid.uuid4().hex + '.json')
    try:
        temporary.write_bytes(json_bytes(dict(path=str(path.resolve()),
            previous=parse_json(previous).get('path', '') if previous is not None else '')))
        os.replace(temporary, state)
    finally:
        if temporary.exists():
            temporary.unlink()
    return previous


def active_launch(directory=None):
    directory = Path(directory) if directory is not None else update_directory()
    state = directory / 'active.json'
    if not state.is_file():
        return None
    path = verify_installation(parse_json(state.read_bytes())['path'], directory)
    return path / 'OMFITtemplates/launch.py'


def restore_activation(previous, directory=None):
    directory = Path(directory) if directory is not None else update_directory()
    state = directory / 'active.json'
    if previous is None:
        state.unlink(missing_ok=True)
    else:
        temporary = state.with_name('.restore-' + uuid.uuid4().hex + '.json')
        try:
            temporary.write_bytes(previous)
            os.replace(temporary, state)
        finally:
            if temporary.exists():
                temporary.unlink()
