"""Install the official GitHub CLI in the Linux user's application directory."""
from builtins import dict, int, len, min, open, str
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile

from OMFITlib_template_archive import CHUNK, TemplateError
from OMFITlib_template_paths import xdg_path
from OMFITlib_template_service import check_cancel, new_file

CLI_REPOSITORY = 'cli/cli'
MAX_ARCHIVE = 128 * 1024 ** 2
MAX_UNPACKED = 256 * 1024 ** 2


def cli_path():
    return xdg_path('XDG_DATA_HOME', '.local/share') / 'omfit-template-manager' / 'tools' / 'bin' / 'gh'


def find_cli():
    """Share discovery between login and token lookup without editing PATH."""
    executable = shutil.which('gh')
    if executable:
        return executable
    path = cli_path()
    return str(path) if path.is_file() and not path.is_symlink() and os.access(path, os.X_OK) else None


def linux_architecture():
    architectures = {'x86_64': 'amd64', 'amd64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64',
                     'i386': '386', 'i686': '386', 'armv6l': 'armv6', 'armv7l': 'armv6'}
    architecture = architectures.get(platform.machine().lower(), '')
    if platform.system() != 'Linux' or not architecture:
        raise TemplateError('GitHub CLI 自动安装支持 Linux x86、x86_64、ARM64 和 ARMv6/v7。')
    return architecture


def _package(release, architecture):
    tag = str(release.get('tag_name', ''))
    if release.get('draft') or release.get('prerelease') or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
        raise TemplateError('GitHub CLI 官方稳定版信息无效，请重试')
    version = tag[1:]
    name = 'gh_{}_linux_{}.tar.gz'.format(version, architecture)
    matches = [asset for asset in release.get('assets', [])
               if asset.get('name') == name and asset.get('state') == 'uploaded']
    if len(matches) != 1:
        raise TemplateError('GitHub CLI 官方版本缺少当前架构的安装包：' + architecture)
    asset = matches[0]
    try:
        size, identity = int(asset['size']), int(asset['id'])
        digest = str(asset['digest'])
        if not (0 < size <= MAX_ARCHIVE and identity > 0 and re.fullmatch(r'sha256:[a-f0-9]{64}', digest)):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise TemplateError('GitHub CLI 安装包缺少有效大小或 SHA-256，已停止安装') from None
    return dict(name=name, version=version, size=size, identity=identity, sha256=digest[7:])


def _download(client, package, target):
    done, hasher = 0, hashlib.sha256()
    if client.progress:
        client.progress('正在下载 GitHub CLI ' + package['version'], 0, package['size'])
    with client._open(client.base + '/releases/assets/' + str(package['identity']),
                      accept='application/octet-stream') as response, open(target, 'wb') as output:
        while True:
            check_cancel(client.cancel)
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            done += len(chunk)
            if done > package['size']:
                raise TemplateError('GitHub CLI 下载超过声明大小，已停止安装')
            output.write(chunk)
            hasher.update(chunk)
            if client.progress:
                client.progress('正在下载 GitHub CLI ' + package['version'], done, package['size'])
    check_cancel(client.cancel)
    if done != package['size'] or hasher.hexdigest() != package['sha256']:
        raise TemplateError('GitHub CLI 安装包大小或 SHA-256 校验失败，请重新点击登录重试')


def _unpack(archive_path, package, target, cancel):
    """Copy only the expected regular executable, never extract archive paths."""
    expected = package['name'][:-7] + '/bin/gh'
    found, count, size = False, 0, 0
    try:
        with tarfile.open(archive_path, 'r|gz') as archive:
            for member in archive:
                check_cancel(cancel)
                count += 1
                size += member.size
                if count > 4096 or member.size < 0 or size > MAX_UNPACKED:
                    raise TemplateError('GitHub CLI 解压内容超过限制')
                if member.name != expected:
                    continue
                if found or not member.isfile() or not 0 < member.size <= MAX_ARCHIVE:
                    raise TemplateError('GitHub CLI 安装包的可执行文件无效')
                found = True
                with archive.extractfile(member) as source, open(target, 'xb') as output:
                    remaining = member.size
                    while remaining:
                        check_cancel(cancel)
                        chunk = source.read(min(CHUNK, remaining))
                        if not chunk:
                            raise TemplateError('GitHub CLI 可执行文件不完整')
                        output.write(chunk)
                        remaining -= len(chunk)
    except (tarfile.TarError, EOFError):
        raise TemplateError('GitHub CLI 压缩包无效，请重新点击登录重试') from None
    if not found:
        raise TemplateError('GitHub CLI 安装包中没有预期的可执行文件')
    target.chmod(0o700)


def ensure_cli(client):
    """Called only by the login action; browsing never installs software."""
    check_cancel(client.cancel)
    executable = find_cli()
    if executable:
        return executable
    if client.repo != CLI_REPOSITORY:
        raise TemplateError('GitHub CLI 安装源必须为官方 cli/cli 仓库')
    architecture = linux_architecture()
    if client.progress:
        client.progress('正在检查 GitHub CLI 官方安装包', 0, 0)
    package = _package(client._json(client.base + '/releases/latest'), architecture)
    destination = cli_path()
    if destination.exists() or destination.is_symlink():
        raise TemplateError('GitHub CLI 安装位置已有不可用文件，请检查：' + str(destination))
    try:
        # Sibling staging keeps publication atomic on the user's filesystem.
        with new_file(destination) as temporary:
            with tempfile.TemporaryDirectory(prefix='.gh-download-', dir=destination.parent) as directory:
                archive = Path(directory) / 'gh.tar.gz'
                _download(client, package, archive)
                if client.progress:
                    client.progress('校验通过，正在安装 GitHub CLI', 0, 0)
                _unpack(archive, package, temporary, client.cancel)
            check_cancel(client.cancel)
            try:
                result = subprocess.run([str(temporary), '--version'], stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False)
            except (OSError, subprocess.TimeoutExpired):
                raise TemplateError('GitHub CLI 无法在用户目录运行，请检查目录执行权限与 Linux 架构后重试') from None
            if result.returncode or not result.stdout.startswith(('gh version ' + package['version'] + ' ').encode()):
                raise TemplateError('GitHub CLI 安装后运行验证失败，未启用该文件')
            check_cancel(client.cancel)
    except OSError as exc:
        raise TemplateError('GitHub CLI 无法写入用户目录（系统错误 {}）：{}'.format(exc.errno, destination.parent)) from None
    if client.progress:
        client.progress('GitHub CLI 已安装，正在打开登录', 0, 0)
    return str(destination)
