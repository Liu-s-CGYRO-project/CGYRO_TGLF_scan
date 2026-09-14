"""GitHub Releases transport. Credentials stay in gh/keyring or the environment."""
from builtins import all, any, bool, bytes, dict, int, len, list, max, min, open, range, set, sorted, str, tuple, type
import hashlib
import base64
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib import error, parse, request

from OMFITlib_template_archive import CHUNK, TemplateError, json_bytes, parse_json
from OMFITlib_template_service import EXTENSION, Template, check_cancel, new_file, release_name
from OMFITlib_template_proxy import ClosingTunnelHTTPSHandler, connection_label, login_environment, normalize_proxy, proxy_handler
from OMFITlib_template_versions import sort_releases

API = 'https://api.github.com'
DEFAULT_REPOSITORY = 'Liu-s-CGYRO-project/CGYRO_TGLF_scan'
MAX_ASSET = 2 * 1024 ** 3  # GitHub requires each asset to be strictly below 2 GiB.
MAX_RESPONSE = 16 * 1024 ** 2
MARKER = '<!-- omfit-template-release-v1\n'
API_VERSION = '2026-03-10'
INITIAL_README = '''# OMFIT 模板库

此仓库使用 GitHub Releases 分发 OMFIT 模板。模板附件名为
`作者__模板ID__版本.omfittpl.zip`，标签为 `omfit/作者/模板ID/版本`。

在 Linux 桌面的 OMFIT 中打开 OMFITtemplates 模块，连接此仓库，选择版本并拉取。
更新默认保留当前案例、计算结果和设置，也可选择模板示例与模板设置。
模板管理器生成独立的新工程 ZIP；打开前可备份当前 OMFIT 会话。

开发者先在 OMFIT 保存工程，选择模块，准备模板包并查看上传文件清单，再发布新版本。
默认仅发布代码和设置。包含示例时，应使用单独准备的小型工程；单个附件必须小于 2 GiB。
同一版本不可覆盖。上传中断时请检查 Releases 草稿。

每个 Release 的模板附件是 OMFIT 使用的版本内容。Git 标签固定仓库当时的提交，
不会自动把附件内源码提交到 Git；源码分支、代码审查和合并可沿用团队的 Git 工作流。
'''


def repository(value):
    """Accept owner/repo, HTTPS clone URL, or the usual GitHub SSH URL."""
    value = str(value).strip()
    if value.startswith('git@github.com:'):
        value = value[len('git@github.com:'):]
    elif '://' in value:
        parts = parse.urlsplit(value)
        if (parts.scheme != 'https' or parts.netloc.lower() != 'github.com'
                or parts.query or parts.fragment):
            raise TemplateError('仓库地址请使用 https://github.com/所有者/仓库 或 所有者/仓库')
        value = parts.path.lstrip('/')
    value = value.rstrip('/')
    if value.endswith('.git'):
        value = value[:-4]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', value):
        raise TemplateError('请填写 GitHub 仓库，例如 team/omfit-templates')
    if value.split('/')[1] in ('.', '..'):
        raise TemplateError('仓库名称无效')
    return value


def credentials():
    for key in ('GH_TOKEN', 'GITHUB_TOKEN'):
        token = os.environ.get(key, '').strip()
        if token:
            return token, key
    executable = shutil.which('gh')
    if executable:
        try:
            result = subprocess.run([executable, 'auth', 'token', '--hostname', 'github.com'],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=10, check=False)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.decode('utf-8').strip(), 'GitHub CLI'
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            pass
    return '', '未登录（仅公开仓库）'


def login(proxy=None):
    """User-triggered login in their Linux desktop terminal, with no shell text."""
    executable = shutil.which('gh')
    if not executable:
        raise TemplateError('请先安装 GitHub CLI（gh），然后执行：gh auth login --hostname github.com --web')
    command = [executable, 'auth', 'login', '--hostname', 'github.com', '--web', '--git-protocol', 'https']
    terminals = [('x-terminal-emulator', ['-e']), ('gnome-terminal', ['--']),
                 ('konsole', ['-e']), ('xfce4-terminal', ['-x']), ('xterm', ['-e'])]
    for name, arguments in terminals:
        terminal = shutil.which(name)
        if terminal:
            subprocess.Popen([terminal] + arguments + command, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                             env=login_environment(proxy))
            return
    raise TemplateError('未找到桌面终端。请在终端执行 gh auth login --hostname github.com --web，然后返回并连接仓库。')


class GitHubError(TemplateError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class SafeRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = parse.urlsplit(newurl)
        if (target.scheme != 'https' or target.username or target.password or target.port not in (None, 443)
                or not (target.hostname == 'github.com' or target.hostname == 'api.github.com'
                        or (target.hostname or '').endswith('.githubusercontent.com'))):
            raise TemplateError('GitHub 返回了不受支持的下载地址')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and parse.urlsplit(req.full_url).netloc != target.netloc:
            redirected.remove_header('Authorization')
        return redirected


def file_hash(path, cancel=None):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            check_cancel(cancel)
            chunk = stream.read(CHUNK)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def release_tag(metadata):
    release_name(metadata)
    return 'omfit/' + '/'.join(metadata[k] for k in ('author', 'id', 'version'))


def summary_from_body(body):
    if not isinstance(body, str):
        return {}
    body = body.replace('\r\n', '\n').replace('\r', '\n')
    if MARKER not in body:
        return {}
    try:
        content = body.rsplit(MARKER, 1)[1].split('\n-->', 1)[0]
        result = parse_json(content.encode('utf-8'))
        if not isinstance(result, dict):
            return {}
        release_name(result)
        if (type(result.get('examples')) is not bool or not isinstance(result.get('roots'), list)
                or not all(isinstance(root, str) for root in result['roots'])
                or not re.fullmatch(r'[a-f0-9]{64}', str(result.get('sha256', '')))):
            return {}
        return result
    except (TemplateError, KeyError, ValueError):
        return {}


class GitHub:
    def __init__(self, repo, token=None, cancel=None, progress=None, proxy=None):
        self.repo = repository(repo)
        self._token, self.auth_source = credentials() if token is None else (token, '会话凭据')
        if any(character.isspace() for character in self._token):
            raise TemplateError('GitHub 凭据格式无效，请重新登录')
        self.cancel, self.progress = cancel, progress
        self.base = '/repos/' + self.repo
        proxy = normalize_proxy(proxy)
        self.connection = connection_label(proxy)
        self.opener = request.build_opener(proxy_handler(proxy), ClosingTunnelHTTPSHandler(), SafeRedirect())

    def _open(self, path, method='GET', data=None, accept='application/vnd.github+json', upload=False, size=None):
        check_cancel(self.cancel)
        origin = 'https://uploads.github.com' if upload else API
        headers = {'Accept': accept, 'X-GitHub-Api-Version': API_VERSION,
                   'User-Agent': 'OMFIT-template-manager/1.3'}
        if self._token:
            headers['Authorization'] = 'Bearer ' + self._token
        if data is not None:
            headers['Content-Type'] = 'application/zip' if upload else 'application/json'
        if size is not None:
            headers['Content-Length'] = str(size)
        req = request.Request(origin + path, data=data, headers=headers, method=method)
        try:
            return self.opener.open(req, timeout=30)
        except error.HTTPError as exc:
            status = exc.code
            remaining = exc.headers.get('X-RateLimit-Remaining', '')
            exc.close()
            message = {401: 'GitHub 登录已失效，请重新登录。',
                       403: 'GitHub 拒绝访问，请检查仓库权限、组织 SSO 或 API 限额。',
                       404: 'GitHub 仓库或版本不存在，或当前账号没有访问权限。',
                       407: 'HTTP 代理认证失败，请重新加载 SSH 连接脚本或检查代理用户名和密码。',
                       422: 'GitHub 拒绝此版本：可能已存在同名标签或资源，或仓库尚无提交。'}.get(status,
                        'GitHub 请求失败（HTTP {}），请稍后检查远端状态。'.format(status))
            if status in (403, 429) and remaining == '0':
                message = 'GitHub API 限额已用完，请稍后重试；公开仓库也可登录后提高可用限额。'
            raise GitHubError(status, message) from None
        except (error.URLError, OSError, TimeoutError) as exc:
            if '407' in str(getattr(exc, 'reason', exc)):
                raise TemplateError('HTTP 代理认证失败，请重新加载 SSH 连接脚本或检查代理用户名和密码。') from None
            raise TemplateError('连接 GitHub 失败或超时（{}）。请检查 SSH 隧道、本地代理端口与网络。'.format(self.connection)) from None

    def _json(self, path, method='GET', payload=None, **kwargs):
        data = json_bytes(payload) if payload is not None else None
        with self._open(path, method, data=data, **kwargs) as response:
            content = response.read(MAX_RESPONSE + 1)
        if len(content) > MAX_RESPONSE:
            raise TemplateError('GitHub 响应过大，已停止读取')
        return parse_json(content)

    def probe(self):
        self._json('/rate_limit')
        return {'connection': self.connection, 'https_verified': True}

    def connect(self):
        info = self._json(self.base)
        user = self._json('/user').get('login', '') if self._token else ''
        try:
            commits = self._json(self.base + '/commits?per_page=1')
            empty = not commits
        except GitHubError as exc:
            if exc.status != 409:
                raise
            empty = True
        return {'repository': self.repo, 'login': user, 'auth_source': self.auth_source,
                'private': bool(info.get('private')), 'default_branch': info.get('default_branch', ''),
                'can_push': bool(info.get('permissions', {}).get('push')),
                'empty': empty,
                'url': 'https://github.com/' + self.repo}

    def initialize_empty(self):
        if not self._token:
            raise TemplateError('初始化需要先登录具有仓库写权限的 GitHub 账号')
        connection = self.connect()
        if not connection['empty']:
            raise TemplateError('仓库已有提交，无需初始化；没有修改任何文件')
        # No sha means this endpoint cannot overwrite an existing README.
        self._json(self.base + '/contents/README.md', 'PUT', {
            'message': 'Initialize OMFIT template release library',
            'content': base64.b64encode(INITIAL_README.encode('utf-8')).decode('ascii')})
        return 'https://github.com/' + self.repo

    def _pages(self, path):
        for page in range(1, 101):
            values = self._json(path + '?per_page=100&page=' + str(page))
            if not isinstance(values, list):
                raise TemplateError('GitHub 列表格式无效')
            yield from values
            if len(values) < 100:
                return
        raise TemplateError('仓库版本超过 10000 项，请拆分模板库后重试')

    def list_releases(self):
        entries, errors = [], []
        for release in self._pages(self.base + '/releases'):
            if release.get('draft'):
                continue
            metadata = summary_from_body(release.get('body'))
            assets = release.get('assets', [])
            if len(assets) >= 100:
                assets = list(self._pages(self.base + '/releases/' + str(int(release['id'])) + '/assets'))
            for asset in assets:
                name = asset.get('name', '')
                if not name.endswith(EXTENSION) or asset.get('state') != 'uploaded':
                    continue
                try:
                    author, identity, version = name[:-len(EXTENSION)].split('__')
                    item = dict(author=author, id=identity, version=version)
                    if release_name(item) != name:
                        raise TemplateError('文件名无效')
                    declared = metadata if metadata and release_name(metadata) == name else {}
                    size = int(asset['size'])
                    if not 0 < size < MAX_ASSET:
                        raise TemplateError('模板包必须小于 2 GiB')
                    item.update(name=declared.get('name', identity), roots=declared.get('roots', []),
                                examples=declared.get('examples'), description=declared.get('description', release.get('body') or ''),
                                sha256=declared.get('sha256', ''), archive_bytes=size,
                                created=release.get('published_at') or '', repository=self.repo,
                                tag=release.get('tag_name', ''), asset_id=int(asset['id']),
                                asset_digest=asset.get('digest') or '', publisher=release.get('author', {}).get('login', ''),
                                prerelease=bool(release.get('prerelease')), remote=True,
                                url='https://github.com/' + self.repo + '/releases/tag/' + parse.quote(release.get('tag_name', ''), safe=''))
                    entries.append(item)
                except (ValueError, KeyError, TypeError, TemplateError) as exc:
                    errors.append('忽略模板附件 {}：{}'.format(name, exc))
        return sort_releases(entries), errors

    def _verify_download(self, path, release):
        if Path(path).stat().st_size != release['archive_bytes']:
            raise TemplateError('下载大小不一致，请重新拉取此版本')
        digest = file_hash(path, self.cancel)
        expected = release.get('asset_digest', '')
        if expected and not re.fullmatch(r'sha256:[a-f0-9]{64}', expected):
            raise TemplateError('GitHub 返回了不支持的附件校验值')
        if (expected and expected != 'sha256:' + digest) or (release.get('sha256') and release['sha256'] != digest):
            raise TemplateError('GitHub 模板包 SHA-256 校验失败')
        with Template(path) as template:
            template.verify(self.cancel)
            if release_name(template.manifest) != release_name(release):
                raise TemplateError('模板内容与 GitHub 版本标识不一致')
            if release.get('sha256') and any(template.manifest[k] != release[k] for k in ('roots', 'examples')):
                raise TemplateError('模板内容与 GitHub 版本说明不一致')
        return digest

    def pull(self, release, library):
        if release.get('repository') != self.repo:
            raise TemplateError('仓库已经改变，请重新选择版本')
        name = release_name(release)
        identity = int(release['asset_id'])
        if identity <= 0 or not 0 < release['archive_bytes'] < MAX_ASSET:
            raise TemplateError('GitHub 附件信息无效')
        # Repository and asset ID isolate different teams' identically named versions.
        target = Path(library).expanduser().resolve() / 'github' / self.repo.lower() / str(identity) / name
        if target.exists():
            self._verify_download(target, release)
            return str(target)
        with new_file(target) as temporary:
            with self._open(self.base + '/releases/assets/' + str(identity), accept='application/octet-stream') as response:
                with open(temporary, 'wb') as stream:
                    done = 0
                    while True:
                        check_cancel(self.cancel)
                        chunk = response.read(CHUNK)
                        if not chunk:
                            break
                        done += len(chunk)
                        if done > release['archive_bytes']:
                            raise TemplateError('下载超过声明大小，已停止')
                        stream.write(chunk)
                        if self.progress:
                            self.progress('正在从 GitHub 拉取', done, release['archive_bytes'])
            self._verify_download(temporary, release)
        return str(target)

    def prepare_publish(self, path):
        if not self._token:
            raise TemplateError('发布到 GitHub 需要先登录具有仓库写权限的账号')
        with Template(path) as template:
            template.verify(self.cancel)
            metadata = {key: template.manifest[key] for key in ('author', 'id', 'version', 'name', 'roots', 'examples', 'description')}
        size = Path(path).stat().st_size
        if size >= MAX_ASSET:
            raise TemplateError('GitHub 单个附件必须小于 2 GiB，请减小示例工程或关闭“包含案例与结果”')
        connection = self.connect()
        if not connection['login']:
            raise TemplateError('未能确认 GitHub 登录账号')
        branch = connection['default_branch']
        if not branch or connection['empty']:
            raise TemplateError('仓库尚无提交。请先使用“设置与记录”页的“初始化空仓库”，再上传本地模板包')
        commit = self._json(self.base + '/commits/' + parse.quote(branch, safe='')).get('sha', '')
        if not re.fullmatch(r'[a-f0-9]{40,64}', commit):
            raise TemplateError('未能确认 GitHub 仓库的目标提交')
        tag = release_tag(metadata)
        self._ensure_new_tag(tag)
        return dict(metadata=metadata, path=str(Path(path).resolve()), bytes=size,
                    sha256=file_hash(path, self.cancel), repository=self.repo, tag=tag,
                    commit=commit, login=connection['login'], private=connection['private'])

    def _ensure_new_tag(self, tag):
        try:
            self._json(self.base + '/releases/tags/' + parse.quote(tag, safe=''))
        except GitHubError as exc:
            if exc.status == 404:
                # A draft or an existing Git tag must also not be reused.
                for release in self._pages(self.base + '/releases'):
                    if release.get('tag_name') == tag:
                        raise TemplateError('同一版本已存在（可能为未完成草稿），请先在 GitHub 检查或更换版本号')
                try:
                    self._json(self.base + '/git/ref/tags/' + parse.quote(tag, safe=''))
                except GitHubError as tag_exc:
                    if tag_exc.status == 404:
                        return
                    raise
                raise TemplateError('GitHub 上已存在同名标签，请使用新的版本号')
            raise
        raise TemplateError('此 GitHub 版本已存在，请使用新的版本号')

    def publish_release(self, plan):
        if plan['repository'] != self.repo or plan['tag'] != release_tag(plan['metadata']):
            raise TemplateError('发布目标已经改变，请重新准备发布')
        if Path(plan['path']).stat().st_size != plan['bytes'] or file_hash(plan['path'], self.cancel) != plan['sha256']:
            raise TemplateError('模板包已改变，请重新准备发布')
        if self.connect()['login'] != plan['login']:
            raise TemplateError('GitHub 登录账号已经改变，请重新准备发布')
        self._ensure_new_tag(plan['tag'])
        metadata = dict(plan['metadata'], sha256=plan['sha256'])
        body = (str(metadata.get('description', '')) + '\n\nOMFIT template: ' + release_name(metadata)
                + '\nSHA-256: ' + plan['sha256'] + '\n\n' + MARKER
                + json_bytes(metadata).decode('utf-8').strip() + '\n-->')
        draft_id = None
        page = 'https://github.com/' + self.repo + '/releases'
        try:
            draft = self._json(self.base + '/releases', 'POST', dict(tag_name=plan['tag'],
                target_commitish=plan['commit'], name=metadata['name'] + ' · ' + metadata['author'] + ' · ' + metadata['version'],
                body=body, draft=True, prerelease=False, make_latest='false'))
            draft_id = int(draft['id'])
            # Follow the documented upload relation only after checking its host and path.
            upload = parse.urlsplit(draft['upload_url'].split('{', 1)[0])
            expected = self.base + '/releases/' + str(draft_id) + '/assets'
            if upload.scheme != 'https' or upload.netloc != 'uploads.github.com' or upload.path.lower() != expected.lower():
                raise TemplateError('GitHub 上传地址无效')
            endpoint = expected + '?' + parse.urlencode({'name': release_name(metadata)})
            digest = hashlib.sha256()

            def chunks(stream):
                done = 0
                while True:
                    check_cancel(self.cancel)
                    chunk = stream.read(CHUNK)
                    if not chunk:
                        break
                    digest.update(chunk)
                    done += len(chunk)
                    if self.progress:
                        self.progress('正在上传 GitHub 草稿', done, plan['bytes'])
                    yield chunk

            with open(plan['path'], 'rb') as stream:
                with self._open(endpoint, 'POST', data=chunks(stream), upload=True, size=plan['bytes']) as response:
                    content = response.read(MAX_RESPONSE + 1)
            if len(content) > MAX_RESPONSE:
                raise TemplateError('GitHub 上传响应过大')
            asset = parse_json(content)
            if (digest.hexdigest() != plan['sha256'] or asset.get('size') != plan['bytes']
                    or asset.get('state') != 'uploaded' or asset.get('name') != release_name(metadata)
                    or (asset.get('digest') and asset['digest'] != 'sha256:' + plan['sha256'])):
                raise TemplateError('上传校验失败，草稿未发布')
            check_cancel(self.cancel)
            self._json(self.base + '/releases/' + str(draft_id), 'PATCH', {'draft': False, 'make_latest': 'false'})
        except Exception as exc:
            # No automatic retry or deletion after an uncertain remote write.
            raise TemplateError(str(exc) + '\n请检查 GitHub Releases 中的发布状态或草稿：' + page
                                + '\n尚未完成的草稿不会出现在模板版本列表中。') from None
        return 'https://github.com/' + self.repo + '/releases/tag/' + parse.quote(plan['tag'], safe='')
