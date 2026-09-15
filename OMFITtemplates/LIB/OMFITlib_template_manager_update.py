"""Check and download manager-only releases without changing a running project."""
from builtins import dict, int, len, list, max, open, set, str
import hashlib
from pathlib import Path
import re
from urllib import parse

from OMFITlib_template_archive import CHUNK, TemplateError
from OMFITlib_template_service import check_cancel, new_file
from OMFITlib_template_versions import MANAGER_VERSION, semantic_version
from OMFITlib_template_incremental import manifest_name, verified_asset

MANAGER_TAG_PREFIX = 'omfit-manager/v'
MAX_MANAGER_PACKAGE = 128 * 1024 ** 2


def package_names(version):
    return {'linux': 'OMFIT_template_manager_linux_v' + version + '.tar.gz',
            'omfit': 'OMFIT_template_manager_' + version + '.omfit.zip'}


def check_manager_update(client, current_version=MANAGER_VERSION):
    current = semantic_version(current_version)
    if current is None:
        raise TemplateError('当前管理器版本号无效')
    candidates = []
    for release in client._pages(client.base + '/releases'):
        check_cancel(client.cancel)
        tag = str(release.get('tag_name', ''))
        if release.get('draft') or release.get('prerelease') or not tag.startswith(MANAGER_TAG_PREFIX):
            continue
        version = tag[len(MANAGER_TAG_PREFIX):]
        key = semantic_version(version)
        if key is not None and key[3] == 1:
            candidates.append((key, version, release))
    result = dict(current=current_version, latest='', available=False, repository=client.repo,
                  packages={}, url='https://github.com/' + client.repo + '/releases', notes='')
    if not candidates:
        return result
    key, version, release = max(candidates, key=lambda item: item[0])
    assets = release.get('assets', [])
    if len(assets) >= 100:
        assets = list(client._pages(client.base + '/releases/' + str(int(release['id'])) + '/assets'))
    packages = {}
    for kind, name in package_names(version).items():
        matches = [asset for asset in assets if asset.get('name') == name and asset.get('state') == 'uploaded']
        if len(matches) != 1:
            continue
        asset = matches[0]
        digest = str(asset.get('digest', ''))
        try:
            size, identity = int(asset['size']), int(asset['id'])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 < size <= MAX_MANAGER_PACKAGE and identity > 0 and re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            packages[kind] = dict(name=name, size=size, asset_id=identity, sha256=digest[7:], repository=client.repo)
    incremental_assets = {}
    duplicates = set()
    for asset in assets:
        item = verified_asset(asset, client.repo)
        if item:
            if item['name'] in incremental_assets:
                duplicates.add(item['name'])
            incremental_assets[item['name']] = item
    for name in duplicates:
        incremental_assets.pop(name, None)
    manifest = incremental_assets.get(manifest_name(version))
    result.update(latest=version, available=key > current, packages=packages,
                  incremental=dict(manifest=manifest, assets=incremental_assets) if manifest is not None else None,
                  url='https://github.com/' + client.repo + '/releases/tag/' + parse.quote(MANAGER_TAG_PREFIX + version, safe=''),
                  notes=str(release.get('body') or '')[:20000])
    return result


def download_manager_package(client, package, destination):
    if package.get('repository') != client.repo:
        raise TemplateError('管理器更新源已改变，请重新检查更新')
    size, identity = int(package['size']), int(package['asset_id'])
    digest = str(package['sha256'])
    if not (0 < size <= MAX_MANAGER_PACKAGE and identity > 0 and re.fullmatch(r'[a-f0-9]{64}', digest)):
        raise TemplateError('管理器安装包信息无效')
    destination = Path(destination).expanduser().resolve()
    with new_file(destination) as temporary:
        done, hasher = 0, hashlib.sha256()
        with client._open(client.base + '/releases/assets/' + str(identity), accept='application/octet-stream') as response:
            with open(temporary, 'wb') as output:
                while True:
                    check_cancel(client.cancel)
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > size:
                        raise TemplateError('管理器下载超过声明大小')
                    output.write(chunk)
                    hasher.update(chunk)
                    if client.progress:
                        client.progress('正在下载管理器', done, size)
        check_cancel(client.cancel)
        if done != size or hasher.hexdigest() != digest:
            raise TemplateError('管理器安装包大小或 SHA-256 校验失败，请重试')
    return str(destination)
