"""Project navigation, explicit input handoffs and run prerequisites.

Reading the dashboard never submits jobs, inspects large result arrays, or
replaces inputs. All mutations below are explicit button actions.
"""
from builtins import all, any, bool, dict, float, int, isinstance, len, list, set, sorted, str, sum, tuple
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import uuid
from collections import OrderedDict
from OMFITlib_project_runtime import initialize_runtime, apply_runtime, shared_issues

MODULES = {
    'transfer': ('Transfer_tool',), 'cgyro': ('CGYRO_scan',),
    'tglf': ('TGLF_scan', 'TGLF'), 'tgyro': ('TGLF_scan', 'TGYRO'),
    'profiles': ('TGLF_scan', 'TGYRO', 'PROFILES_GEN'),
}
LABELS = {'transfer': '输入转换', 'cgyro': 'CGYRO', 'tglf': 'TGLF',
          'tgyro': 'TGYRO', 'profiles': 'PROFILES_GEN'}
PAGES = OrderedDict([
    ('1 项目概览', 'overview'), ('2 环境配置与记录', 'run'),
    ('3 输入准备与转换', 'transfer'), ('4 输入确认与覆盖', 'review'),
    ('5 CGYRO 扫描', 'cgyro'), ('6 TGLF 单文件与扫描', 'tglf'),
    ('7 TGLF 多剖面计算', 'multi'), ('8 绘图与对比', 'plots'), ('9 模板与 GitHub', 'templates'),
])
DEFAULTS = {'page': 'overview', 'runtime_module': 'cgyro', 'transfer_source': '',
            'cgyro_file': '', 'tglf_file': '', 'message': ''}


def read(node, path, default=None):
    try:
        for key in path:
            node = node[key]
        return node
    except (KeyError, TypeError, AttributeError):
        return default


def text_value(node, key):
    try:
        value = node.get(key, None)
        return '' if value is None else str(value).strip()
    except Exception:
        return ''  # An invalid OMFITexpression is reported as unresolved.


def location(path):
    return 'root' + ''.join('[{!r}]'.format(key) for key in path)


def input_digest(value):
    def plain(item):
        if hasattr(item, 'keys'):
            return {str(key): plain(item[key]) for key in item.keys()}
        if hasattr(item, 'tolist'):
            return plain(item.tolist())
        if isinstance(item, (list, tuple)):
            return [plain(part) for part in item]
        return item
    payload = json.dumps(plain(value), sort_keys=True, ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def pending_inputs(root, destination=None):
    return {key: value for key, value in read(root, ('PROJECT_STATE', 'activity'), {}).items()
            if value.get('status', None) == 'awaiting_choice' and
            (destination is None or value.get('destination', 'tglf') == destination)}


def tglf_input_issues(root):
    if pending_inputs(root, 'tglf'):
        return ['TGLF 输入存在待确认的差异，请先选择保留或覆盖']
    value = read(root, MODULES['tglf'] + ('FILES', 'input.tglf'))
    if value is None:
        return ['请先导入或传递 input.tglf']
    try:
        validate_input(value, 'tglf')
    except (TypeError, ValueError) as exc:
        return [str(exc)]
    return []


def input_difference(current, incoming):
    rows = []
    for key in sorted(set(current.keys()) | set(incoming.keys()), key=str):
        before, after = key in current, key in incoming
        if before and after and input_digest(current[key]) == input_digest(incoming[key]):
            continue
        rows.append((str(key), '变化' if before and after else ('新增' if after else '移除'),
                     str(current[key]) if before else '—', str(incoming[key]) if after else '—'))
    return rows


def validate_input(value, kind):
    required = ('N_SPECIES', 'N_RADIAL', 'N_THETA', 'Q', 'RMIN', 'RMAJ') if kind == 'cgyro' else ('NS', 'KY')
    missing = [key for key in required if key not in value.keys()]
    if missing:
        raise ValueError('input.{} 缺少：{}'.format(kind, ', '.join(missing)))
    for key in (('N_SPECIES', 'N_RADIAL', 'N_THETA') if kind == 'cgyro' else ('NS',)):
        number = float(value[key])
        if not math.isfinite(number) or number < 1 or int(number) != number:
            raise ValueError(key + ' 必须为正整数')
    input_digest(value)


def transfer_upstream_digest(root):
    values = {}
    for path in [('Transfer_file', 'input.gacode'), ('Transfer_file', 'input.tglf'),
                 ('INPUTS', 'input.gacode'), ('INPUTS', 'input.tglf'), ('INPUTS', 'input.tgyro'),
                 ('OUTPUTS', 'Profiles_gen', 'input.gacode')]:
        value = read(root, ('Transfer_tool',) + path)
        if value is not None:
            values['/'.join(path)] = input_digest(value)
    return input_digest(values)


def cgyro_input_issues(root):
    if pending_inputs(root, 'transfer'):
        return ['请先处理 Transfer tool 的 TGLF 输入覆盖选择']
    node = read(root, MODULES['cgyro'], {})
    current = node.get('INPUTS', {}).get('input.cgyro', None)
    if current is None:
        return ['先在 Transfer tool 准备 input.cgyro，再验证并传入 CGYRO']
    marker = read(root, ('PROJECT_STATE', 'pipeline', 'cgyro'), {})
    if not marker:
        return ['Transfer 输入准备尚未确认；请在“传递输入”中验证并送入 CGYRO']
    source_path = marker.get('source', None)
    if not isinstance(source_path, (list, tuple)) or not source_path or source_path[0] != 'Transfer_tool':
        return ['输入传递记录无效，请重新验证并传递']
    source = read(root, source_path)
    if source is None:
        return ['Transfer 源输入已移除，请重新准备和传递输入']
    try:
        validate_input(current, 'cgyro')
        if transfer_upstream_digest(root) != marker.get('upstream_digest', None):
            return ['Transfer 上游剖面或 TGLF 输入已经变化，请重新生成并传递 CGYRO 输入']
        if input_digest(source) != marker.get('source_digest', None):
            return ['Transfer 输入已经变化，请重新验证并传递给 CGYRO']
        if input_digest(current) != marker.get('input_digest', None):
            return ['CGYRO 输入已经变化，请在 Transfer tool 重新准备并传递']
    except (TypeError, ValueError) as exc:
        return [str(exc)]
    return []


def collect_issues(root):
    manifest = read(root, ('CGYRO_scan', 'RUN_MANIFEST'), {})
    if not manifest or manifest.get('status', None) not in ('submitted', 'submitted_or_finished', 'running', 'loaded', 'published'):
        return ['尚无已执行 / 已提交的 CGYRO 运行；仅生成输入后不能收集结果']
    if not manifest.get('points', None) or not manifest.get('workDir', None):
        return ['当前运行记录缺少扫描点或工作目录']
    return []


def comparison_issues(root, mode):
    problems = []
    if 'CGYRO' in mode and not read(root, ('CGYRO_scan', 'RUN_DB'), {}):
        problems.append('尚无已收集的 CGYRO 结果')
    if 'TGLF' in mode:
        tg = root.get('TGLF_scan', {})
        if not any(tg.get(key, None) for key in ('scanResults', 'scanResults_spectra', 'scanResults2D', 'scanResults2D_spectra')):
            problems.append('尚无可供此绘图入口使用的 TGLF 扫描结果')
    return problems


def initialize(root, factory=dict):
    settings = root.setdefault('SETTINGS', factory()).setdefault('WORKBENCH', factory())
    for key, value in DEFAULTS.items():
        settings.setdefault(key, value)
    if settings['page'] not in PAGES.values():
        settings['page'] = 'overview'
    if settings['runtime_module'] not in MODULES:
        settings['runtime_module'] = 'cgyro'
    return settings


def module(root, name):
    result = read(root, MODULES[name])
    if result is None:
        raise ValueError('工程缺少模块：' + LABELS[name])
    return result


def runtime_issues(root, name):
    """Check the fields actually used by each current execution route."""
    if shared_issues(root):
        return shared_issues(root)
    node = read(root, MODULES[name])
    if node is None:
        return ['缺少模块']
    settings = node.get('SETTINGS', {})
    setup, remote = settings.get('SETUP', {}), settings.get('REMOTE_SETUP', {})
    problems = []
    if name == 'cgyro':
        picker = text_value(remote, 'serverPicker')
        cfg = remote.get(picker, {})
        if not picker or not isinstance(cfg, dict):
            return ['未选择有效的服务器配置']
        if not cfg:
            return ['所选服务器尚无 CGYRO 配置']
        for key, label in [('executable', 'CGYRO 命令'), ('environment', '环境初始化')]:
            if not text_value(cfg, key):
                problems.append(label + '未填写')
        scheduler = text_value(cfg, 'scheduler').lower()
        if scheduler not in ('local', 'slurm', 'pbs'):
            problems.append('调度器未设置为 local / slurm / pbs')
        elif (picker == 'localhost') != (scheduler == 'local'):
            problems.append('localhost 与 local 调度器必须配套')
        if scheduler in ('slurm', 'pbs'):
            for key in ('queue', 'w'):
                if not text_value(cfg, key):
                    problems.append(key + '未填写')
            resource_keys = ('nodes', 'ntasks_per_node', 'array_parallel') if scheduler == 'slurm' else ('nodes', 'ppn')
            for key in resource_keys:
                try:
                    value = int(cfg.get(key, 0))
                    if value < 1 or str(value) != str(cfg.get(key, None)).strip():
                        raise ValueError()
                except (TypeError, ValueError):
                    problems.append(key + '必须为正整数')
        if picker != 'localhost':
            for key in ('server', 'workDir'):
                if not text_value(cfg, key) and not text_value(remote, key):
                    problems.append('远程 ' + key + '未填写')
    else:
        if not text_value(remote, 'server'):
            problems.append('实际执行服务器未解析；可同步 OMFIT 连接配置')
        if not text_value(setup, 'executable'):
            problems.append('执行命令为空或表达式无法求值')
    return problems


def transfer_sources(root):
    result = {}
    for suffix in [('Transfer_file',), ('OUTPUTS', 'Profiles_gen'), ('INPUTS',)]:
        branch = read(root, ('Transfer_tool',) + suffix, {})
        for key in branch.keys():
            if any(str(key) == 'input.' + kind or str(key).startswith('input.' + kind + '_')
                   for kind in ('gacode', 'cgyro', 'tglf')):
                path = ('Transfer_tool',) + suffix + (key,)
                result[' / '.join(suffix + (str(key),))] = json.dumps(path)
    return result


def generated_tglf_sources(root):
    return {str(radius): json.dumps(['TGLF_scan', 'input.tglf', radius])
            for radius in read(root, ('TGLF_scan', 'input.tglf'), {}).keys()}


def summary(root):
    cases = root.get('TGLF_CASES', {})
    cg = root.get('CGYRO_scan', {})
    tg = root.get('TGLF_scan', {})
    manifest = cg.get('RUN_MANIFEST', {})
    return {
        'transfer_inputs': len(transfer_sources(root)),
        'cgyro_input': 'input.cgyro' in cg.get('INPUTS', {}),
        'tglf_input': 'input.tglf' in read(tg, ('TGLF', 'FILES'), {}),
        'profiles': 'input.gacode' in read(tg, ('TGYRO', 'PROFILES_GEN', 'OUTPUTS'), {}),
        'multi_cases': len(cases), 'multi_selected': sum(bool(c.get('enabled', None)) for c in cases.values()),
        'cgyro_runs': len(cg.get('RUN_DB', {})),
        'cgyro_status': manifest.get('status', '尚无运行记录'),
        'tglf_radii': len(tg.get('scanResults_spectra', {})),
    }


class ProjectActions:
    def __init__(self, root, factory=dict, readers=None, resolve_server=None, workdir=None, register_server=None):
        self.root, self.factory = root, factory
        self.settings = initialize(root, factory)
        self.readers = readers or {}
        self.resolve_server, self.workdir = resolve_server, workdir
        self.register_server = register_server

    def _record(self, title, **values):
        state = self.root.setdefault('PROJECT_STATE', self.factory())
        records = state.setdefault('activity', self.factory())
        key = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8]
        record = self.factory()
        record.update(dict(id=key, title=title, created=datetime.now(timezone.utc).isoformat(), **values))
        records[key] = record
        return record

    def open_page(self, page):
        self.settings['page'] = page

    def call(self, title, path, **kwargs):
        task = read(self.root, path)
        if task is None:
            raise ValueError('工程缺少入口：' + '/'.join(path))
        record = self._record(title, status='running')
        try:
            result = task.run(**kwargs)
        except BaseException as exc:
            record.update(dict(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed', error=str(exc)))
            self.settings['message'] = title + '：' + str(exc)
            raise
        record['status'] = 'returned'
        self.settings['message'] = title + '：脚本已返回。计算状态请查看对应运行记录。'
        return result

    def replace(self, title, replacements):
        """Prepare independent copies before changing any destination input."""
        prepared, previous = [], self.factory()
        for path, value in replacements:
            parent = read(self.root, path[:-1])
            if parent is None:
                raise ValueError('缺少目标目录：' + '/'.join(path[:-1]))
            duplicate = value.duplicate() if hasattr(value, 'duplicate') else copy.deepcopy(value)
            if path[-1] in parent:
                previous[location(path)] = copy.deepcopy(parent[path[-1]])
            prepared.append((parent, path[-1], duplicate))
        record = self._record(title, status='inputs_copied', previous_inputs=previous)
        for parent, key, value in prepared:
            parent[key] = value
        record['destinations'] = [location(path) for path, _ in replacements]
        self.settings['message'] = title + '。原输入已保存在 Project 的输入历史中。'

    def import_input(self, kind, location=None):
        filename = self.settings[kind + '_file']
        if not filename:
            return
        obj = self.readers[kind](filename)
        validate_input(obj, kind)
        if kind == 'cgyro':
            target = MODULES['transfer'] + ('Transfer_file', 'input.cgyro')
            self.replace('载入 Transfer tool 待准备输入', [(target, obj)])
            self.settings.update(dict(cgyro_file='', page='transfer'))
            self.settings['message'] = 'input.cgyro 已载入 Transfer tool。请在“传递输入”中验证并送入 CGYRO。'
            return
        self.propose_tglf(obj, '导入 input.tglf：' + str(filename))
        self.settings[kind + '_file'] = ''

    def handoff(self, target):
        selected = self.settings['transfer_source']
        if selected not in transfer_sources(self.root).values():
            raise ValueError('请先选择 Transfer tool 中的输入或生成结果。')
        source_path = tuple(json.loads(selected))
        source = read(self.root, source_path)
        kind = str(source_path[-1]).split('_')[0]
        if target in ('cgyro', 'tglf'):
            if kind != 'input.' + target:
                raise ValueError('此目标需要 input.' + target + '，请先转换或选择对应文件。')
            validate_input(source, target)
            if target == 'tglf':
                self.propose_tglf(source, 'Transfer tool → TGLF', source_path)
                return
            source_digest = input_digest(source)
            upstream_digest = transfer_upstream_digest(self.root) if target == 'cgyro' else None
            path = MODULES[target] + (('INPUTS', kind) if target == 'cgyro' else ('FILES', kind))
            self.replace('送入 ' + LABELS[target], [(path, source)])
            if target == 'cgyro':
                pipeline = self.root['PROJECT_STATE'].setdefault('pipeline', self.factory())
                marker = self.factory()
                marker.update(dict(source=list(source_path), source_digest=source_digest,
                              input_digest=input_digest(read(self.root, path)), upstream_digest=upstream_digest, status='ready'))
                pipeline['cgyro'] = marker
        elif target == 'transfer':
            if kind != 'input.gacode':
                raise ValueError('请先选择 input.gacode。')
            self.replace('设为 Transfer tool 当前剖面', [(MODULES['transfer'] + ('INPUTS', kind), source)])
        elif target == 'profiles':
            if kind != 'input.gacode':
                raise ValueError('剖面流程需要 input.gacode。')
            paths = [(MODULES['profiles'] + (group, name), source)
                     for group in ('INPUTS', 'OUTPUTS') for name in ('input.gacode', 'input.gacode_base')]
            scan = self.root['TGLF_scan']
            # Explicitly changing the upstream profile invalidates old local inputs.
            # Preserve their associated results before the existing setup regenerates them.
            old = self.factory()
            cache_keys = ('input.tglf', 'tgyro_output', 'scanResults', 'scanResults_spectra',
                          'scanResults2D', 'scanResults2D_spectra', 'UQResults', 'UQResults_spectra',
                          'Experimental_fluxes', 'Experimental_spectra', '_scan_cache_provenance',
                          '_radial_cache_provenance', '_input_cache_provenance')
            for key in cache_keys:
                if key in scan:
                    old[key] = copy.deepcopy(scan[key])
            self.replace('送入 TGLF 剖面准备流程', paths)
            if old:
                self._record('切换剖面前的 TGLF 数据', status='archived', tglf_data=old)
            for key in cache_keys:
                scan.pop(key, None)
            pg = module(self.root, 'profiles')['SETTINGS']
            pg['PHYSICS']['start_from'] = 'input.gacode'
            pg['DEPENDENCIES']['profpowbal'] = "root['INPUTS']['input.gacode']"
        else:
            raise ValueError('未知输入目标。')

    def sync_endpoint(self, name):
        node = module(self.root, name)
        remote = node['SETTINGS']['REMOTE_SETUP']
        picker = text_value(remote, 'serverPicker')
        if not picker:
            raise ValueError('请先选择服务器。')
        endpoint = self.resolve_server(node)
        server = str(endpoint.get('server', None) or '')
        if not server and picker == 'localhost':
            server = 'localhost'
        if not server:
            raise ValueError('OMFIT 个人配置未提供此服务器的连接信息。')
        values = dict(server=server, tunnel=str(endpoint.get('tunnel', None) or ''),
                      workDir=str(self.workdir(node, server)))
        remote.update(values)
        if name == 'cgyro':
            cfg = remote.setdefault(picker, self.factory())
            cfg.update(values)
            if picker == 'localhost':
                cfg['scheduler'] = 'local'
        self.settings['message'] = LABELS[name] + '：已同步连接与工作目录，保留原命令和资源设置。'

    def runtime_server_issues(self, match_connection=False):
        config = initialize_runtime(self.root, self.factory)
        picker = text_value(config, 'serverPicker')
        if not picker:
            return ['请先选择或填写 OMFIT 服务器配置名']
        if self.resolve_server is None:
            return []
        try:
            endpoint = self.resolve_server(picker)
        except KeyError:
            return ['服务器“{}”未在当前 OMFIT 个人设置中登记。请选择已登记的服务器，'
                    '或填写下方连接信息后点击“登记此连接到 OMFIT”。'.format(picker)]
        if not text_value(endpoint, 'server'):
            return ['OMFIT 服务器“{}”尚未填写有效的连接地址，请在个人服务器设置中补充。'.format(picker)]
        if match_connection and any(text_value(config, key) != text_value(endpoint, key) for key in ('server', 'tunnel')):
            return ['工程连接与 OMFIT 个人服务器配置不一致。请从 OMFIT 读取连接信息，'
                    '或修改个人服务器设置后重新读取。']
        return []

    def register_runtime_endpoint(self):
        if self.register_server is None:
            self.settings['message'] = '当前宿主未提供服务器登记入口，请打开 OMFIT 的个人服务器设置。'
            return
        config = initialize_runtime(self.root, self.factory)
        try:
            persisted = self.register_server(config)
        except ValueError as exc:
            self.settings['message'] = str(exc)
            return
        self.settings['message'] = '已登记服务器“{}”；请点击“应用到整个工程”同步计算模块。'.format(
            text_value(config, 'serverPicker'))
        if not persisted:
            self.settings['message'] += ' 当前会话已生效，但个人设置未能保存，请在 OMFIT 首选项中保存设置。'

    def sync_runtime_endpoint(self):
        config = initialize_runtime(self.root, self.factory)
        picker = text_value(config, 'serverPicker')
        issues = self.runtime_server_issues()
        if issues:
            self.settings['message'] = '；'.join(issues)
            return
        try:
            endpoint = self.resolve_server(picker)
        except KeyError:
            self.settings['message'] = '服务器配置已变更，请刷新页面后重新选择；现有连接信息保持不变。'
            return
        server = str(endpoint.get('server', None) or ('localhost' if picker == 'localhost' else ''))
        if not server:
            raise ValueError('OMFIT 个人配置未提供此服务器的连接信息。')
        config.update(dict(server=server, tunnel=str(endpoint.get('tunnel', None) or '')))
        if not text_value(config, 'workDir'):
            config['workDir'] = str(self.workdir(self.root, server))
        if picker == 'localhost':
            config['scheduler'] = 'local'
        elif config['scheduler'] == 'local':
            config['scheduler'] = 'slurm'
        self.settings['message'] = '已读取 OMFIT 连接信息。检查下方共用配置后点击“应用到整个工程”。'

    def apply_runtime(self):
        issues = self.runtime_server_issues(match_connection=True)
        if issues:
            self.settings['message'] = '；'.join(issues)
            return
        targets = apply_runtime(self.root, self.factory)
        self.settings['message'] = '统一 GACODE 环境已应用到 {} 个模块；案例和结果保留。'.format(len(targets))
        self._record('应用统一 GACODE 环境', status='complete', modules=targets)
        return targets

    def run_cgyro(self, prepare=False):
        node = module(self.root, 'cgyro')
        if node['SETTINGS']['SETUP'].get('icgyro', None) != 1:
            raise ValueError('此页面使用 CGYRO；旧 GYRO 提交后端不可用。')
        issues = cgyro_input_issues(self.root) + runtime_issues(self.root, 'cgyro')
        if issues:
            raise ValueError('；'.join(issues))
        setup = node['SETTINGS']['SETUP']
        previous = setup.get('irun', None)
        try:
            setup['irun'] = 0 if prepare else 1
            if prepare:
                return self.call('CGYRO 生成输入', MODULES['cgyro'] + ('SCRIPTS', 'subscan_lin.py'),
                                 scan_dimensions=int(setup['idimrun']))
            return self.call('CGYRO 运行扫描', MODULES['cgyro'] + ('SCRIPTS', 'runCGYRO.py'))
        finally:
            setup['irun'] = previous

    def run(self, name, script, required=()):
        node = module(self.root, name)
        issues = runtime_issues(self.root, name)
        if name == 'tglf':
            issues += tglf_input_issues(self.root)
        if name == 'transfer' and pending_inputs(self.root, 'transfer'):
            issues.append('请先确认 Transfer tool 的 TGLF 输入')
        for path in required:
            if read(node, path) is None:
                issues.append('缺少 ' + '/'.join(path))
        if issues:
            raise ValueError('；'.join(issues))
        if name == 'tglf' and script == 'runTGLF':
            validate_input(node['FILES']['input.tglf'], 'tglf')
        return self.call(LABELS[name] + ' / ' + script, MODULES[name] + ('SCRIPTS', script))

    def check(self):
        self.settings['message'] = '\n'.join(
            LABELS[name] + '：' + ('；'.join(runtime_issues(self.root, name)) or '基础字段已填写；尚未验证目标程序和资源')
            for name in MODULES)
        prerequisites = cgyro_input_issues(self.root)
        self.settings['message'] += '\nCGYRO 前置流程：' + ('；'.join(prerequisites) or 'Transfer 输入已验证并传递')

    def collect(self):
        issues = collect_issues(self.root)
        if issues:
            raise ValueError('；'.join(issues))
        self.call('收集 CGYRO 当前结果', MODULES['cgyro'] + ('SCRIPTS', 'downsync.py'))
        node = module(self.root, 'cgyro')
        setup = node['SETTINGS']['SETUP']
        old_run, old_download = setup.get('irun', None), setup.get('idownsync', None)
        try:
            setup['irun'], setup['idownsync'] = 0, 0
            script = 'CGYROScan.py' if node['RUN_MANIFEST']['dimensions'] == 1 else 'CGYROScan_2d.py'
            return self.call('归档已收集的 CGYRO 结果', MODULES['cgyro'] + ('SCRIPTS', script))
        finally:
            setup['irun'], setup['idownsync'] = old_run, old_download

    def save_command(self, name):
        command = self.settings.get('command_draft', '').strip()
        if not command:
            raise ValueError('命令不能为空。')
        module(self.root, name)['SETTINGS']['SETUP']['executable'] = command
        self.settings['message'] = LABELS[name] + '：已保存手动命令。'

    def use_generated_tglf(self):
        selected = self.settings.get('generated_tglf_source', None)
        if selected not in generated_tglf_sources(self.root).values():
            raise ValueError('请先选择 TGYRO 生成的局部 TGLF 输入。')
        source = tuple(json.loads(selected))
        self.propose_tglf(read(self.root, source), 'TGYRO 局部输入 → TGLF 单文件', source)

    def install_tglf(self, incoming, title, destination='tglf'):
        """Archive the old result container so its inputs never become relabelled."""
        if destination == 'transfer':
            node = module(self.root, 'transfer')
            self.replace(title, [(MODULES['transfer'] + ('INPUTS', 'input.tglf'), incoming)])
            if 'TGYRO' in node.get('OUTPUTS', {}):
                self._record('更换 Transfer TGLF 输入前的 TGYRO 结果', status='archived',
                             tgyro_result=copy.deepcopy(node['OUTPUTS']['TGYRO']))
                node['OUTPUTS'].pop('TGYRO')
            return
        node = module(self.root, 'tglf')
        previous = node.get('FILES', self.factory())
        archived = previous.duplicate() if hasattr(previous, 'duplicate') else copy.deepcopy(previous)
        new_files = self.factory()
        new_files['input.tglf'] = incoming.duplicate() if hasattr(incoming, 'duplicate') else copy.deepcopy(incoming)
        self._record(title, status='inputs_copied', previous_tglf_files=archived)
        node['FILES'] = new_files
        self.settings['message'] = title + '。原 TGLF 输入和对应结果已保存在输入历史中。'

    def propose_tglf(self, incoming, title, source_path=None, destination='tglf'):
        validate_input(incoming, 'tglf')
        if destination not in ('tglf', 'transfer'):
            raise ValueError('未知 TGLF 输入目标')
        branch = 'FILES' if destination == 'tglf' else 'INPUTS'
        current = read(self.root, MODULES[destination] + (branch, 'input.tglf'))
        if current is None:
            self.install_tglf(incoming, title, destination)
            return
        # No destination is changed until the user resolves the displayed diff.
        candidate = incoming.duplicate() if hasattr(incoming, 'duplicate') else copy.deepcopy(incoming)
        baseline = current.duplicate() if hasattr(current, 'duplicate') else copy.deepcopy(current)
        differences = input_difference(baseline, candidate)
        for record in pending_inputs(self.root, destination).values():
            record['status'] = 'superseded'
        self._record(title, status='awaiting_choice', current=baseline, incoming=candidate,
                     destination=destination,
                     current_digest=input_digest(current), incoming_digest=input_digest(incoming),
                     source=list(source_path) if source_path else [], differences=differences)
        self.settings.update(dict(page='review', message='目标已有 TGLF 输入。请查看参数差异后选择保留或覆盖。'))

    def resolve_input(self, record_id, use_incoming):
        record = pending_inputs(self.root).get(record_id, None)
        if record is None:
            raise ValueError('这条输入选择已经处理，请刷新页面。')
        if use_incoming:
            destination = record.get('destination', 'tglf')
            branch = 'FILES' if destination == 'tglf' else 'INPUTS'
            current = read(self.root, MODULES[destination] + (branch, 'input.tglf'))
            if current is None or input_digest(current) != record['current_digest']:
                raise ValueError('当前 TGLF 输入在预览后发生变化，请重新传入以更新差异。')
            if record['source']:
                source = read(self.root, record['source'])
                if source is None or input_digest(source) != record['incoming_digest']:
                    raise ValueError('Transfer 源输入或生成的局部输入在预览后发生变化，请重新传入。')
            if input_digest(record['incoming']) != record['incoming_digest']:
                raise ValueError('待传入副本已改变，请重新传入。')
            self.install_tglf(record['incoming'], '用户选择使用待传入 TGLF 输入', destination)
            record['status'] = 'accepted'
        else:
            record['status'] = 'kept_current'
            self.settings['message'] = '已保留当前 TGLF 输入；Transfer / 导入候选保存在输入历史中。'

    def import_transfer_seed(self, kind):
        key = 'transfer_' + kind + '_file'
        filename = self.settings.get(key, None)
        if not filename:
            return
        incoming = self.readers[kind](filename)
        incoming.keys()
        if kind == 'tglf':
            self.propose_tglf(incoming, 'Transfer tool 的 TGLF 计算输入', destination='transfer')
        elif kind == 'tgyro':
            if 'DIR' not in incoming:
                raise ValueError('input.tgyro 缺少 DIR 配置')
            self.replace('载入 Transfer input.tgyro', [(MODULES['transfer'] + ('INPUTS', 'input.tgyro'), incoming)])
            node = module(self.root, 'transfer')
            if 'TGYRO' in node.get('OUTPUTS', {}):
                self._record('更换 input.tgyro 前的结果', status='archived', tgyro_result=copy.deepcopy(node['OUTPUTS']['TGYRO']))
                node['OUTPUTS'].pop('TGYRO')
        self.settings[key] = ''
