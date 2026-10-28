"""Project navigation, explicit input handoffs and run prerequisites.

Input primitives live in project_inputs; CGYRO source/scan preflight lives in
cgyro_plan. This module keeps the public facade and explicit action boundary.
Reading the dashboard never submits jobs, inspects large result arrays, or
replaces inputs. Selection migration is handled by the planning helpers.
"""
from OMFITlib_plot_sources import run_choices
from OMFITlib_gui_api import task_action
# Keep these imports as compatibility exports for existing GUIs and saved scripts.
# New helpers depend on data/parameters only, never back on this action layer.
from OMFITlib_project_inputs import (read, text_value, location, input_digest,
    transfer_parameter_value, pending_inputs, input_difference, validate_input, transfer_upstream_digest)
from OMFITlib_cgyro_plan import (ISOTOPE_MASSES, ION_CASES, sync_cgyro_ion_cases,
    cgyro_ion_mode, cgyro_scan_axes, cgyro_plan_summary, cgyro_sources, sync_cgyro_choices,
    cgyro_plan_issues, cgyro_input_issues, _cgyro_case_id, _cgyro_main_indices,
    _cgyro_case_input, _original_ion_label, _cgyro_radius_number, _generated_particle_record)
from builtins import abs, all, any, bool, dict, enumerate, float, int, isinstance, iter, len, list, next, ord, print, range, set, sorted, str, sum, tuple
import ast
import copy
from datetime import datetime, timezone
import json
import math
import os
import re
import shlex
import uuid
from collections import OrderedDict
from OMFITlib_project_runtime import initialize_runtime, apply_runtime, applied_runtime, runtime_values, shared_issues
from OMFITlib_gacode_installations import (PROGRAMS, detection_is_current, installation_issues, merge_probe,
    parse_probe, probe_script, same_endpoint, sync_environment, valid_path)
from OMFITlib_server_capabilities import (adapt_draft, matching_profile, parse_probe as parse_capabilities,
    probe_script as capability_probe, resource_issues)
from OMFITlib_transfer_workflow import (generation_issues, initialize_generation,
                                      tgyro_batch_settings, tglf_input_format)
from OMFITlib_tglf_workbench import (PROFILE_PATH, RADII, initialize as initialize_tglf,
    fully_failed, generation_overrides, input_rows as tglf_rows, plan as tglf_plan)
from OMFITlib_tglf_multi_data import profile_digest, profile_info, tgyro_input
from OMFITlib_transfer_particles import particle_options
from OMFITlib_transfer_schemes import generate_schemes, scheme_runid
from OMFITlib_cgyro_parameters import (initialize_parameters,
    numeric_source, parameter_catalog)
from OMFITlib_cgyro_scan_values import scan_axes as configured_scan_axes
from OMFITlib_cgyro_isotopes import remap_physics
from OMFITlib_cgyro_run_state import stop_message, submission_pending
from OMFITlib_cgyro_queue import activate_run, collection_done, pending_runs, queue_records, queue_summary, save_current
from OMFITlib_cgyro_retry import retry_limit
from OMFITlib_cgyro_workflow import collect_batch, collect_run
from OMFITlib_cgyro_continue import continuation_plan
from OMFITlib_cgyro_storage import consolidate_storage

# Compatibility exports: saved scripts may still import these here.
from OMFITlib_workbench_catalog import MODULES, LABELS, PAGES

DEFAULTS = {'page': 'overview', 'runtime_module': 'cgyro', 'transfer_source': '',
            'cgyro_file': '', 'tglf_file': '', 'cgyro_source_mode': 'generated', 'cgyro_scan_page': 'input',
            'message': ''}
ERROR_NOTICE_SUFFIX = '，详情见“操作历史”。'


def error_notice(title, cancelled=False):
    title = (str(title).splitlines() or ['操作'])[0][:80]
    return title + ('：已中止' if cancelled else '：失败') + ERROR_NOTICE_SUFFIX


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


def collect_issues(root):
    if any(entry['manifest'].get('job_id', '') and entry['manifest'].get('status', '') != 'published'
           for _, entry in queue_records(read(root, ('CGYRO_scan',), {}))):
        return []
    manifest = read(root, ('CGYRO_scan', 'RUN_MANIFEST'), {})
    if submission_pending(manifest):
        return ['提交状态待确认，请先同步作业状态']
    if manifest.get('status', '') == 'failed' and not manifest.get('job_id', ''):
        return ['没有已确认提交的作业，无需收集']
    if not manifest or manifest.get('status', None) not in ('submitted', 'submitted_or_finished', 'running', 'loaded', 'failed', 'cancelled', 'cancel_requested'):
        return ['尚无已执行 / 已提交的 CGYRO 运行；仅生成输入后不能收集结果']
    if not manifest.get('points', None) or not manifest.get('workDir', None):
        return ['当前运行记录缺少扫描点或工作目录']
    return []


def sync_run_issues(root):
    queued = [entry['manifest'] for _, entry in queue_records(read(root, ('CGYRO_scan',), {}))
              if entry['manifest'].get('status', '') != 'published']
    if any(row.get('scheduler', '') == 'slurm' and
           (row.get('job_id', '') or submission_pending(row)) for row in queued):
        return []
    manifest = read(root, ('CGYRO_scan', 'RUN_MANIFEST'), {})
    if not manifest or manifest.get('status', '') == 'published':
        return ['尚无需要同步状态的 CGYRO 运行']
    if manifest.get('scheduler', '') == 'slurm' and submission_pending(manifest):
        return []
    if not re.fullmatch(r'[0-9]+', str(manifest.get('job_id', '') or '')):
        return ['当前记录没有 Slurm 作业号，不能推断远程状态']
    remote = read(root, ('CGYRO_scan', 'SETTINGS', 'REMOTE_SETUP'), {})
    scheduler = str(manifest.get('scheduler', '') or remote.get(
        str(manifest.get('serverPicker', '') or ''), {}).get('scheduler', '')).lower()
    if scheduler != 'slurm':
        return ['此按钮用于同步 Slurm 作业；其他运行可通过收集结果更新状态']
    return []


def comparison_issues(root, mode):
    problems = []
    if 'CGYRO' in mode and not read(root, ('CGYRO_scan', 'RUN_DB'), {}):
        problems.append('尚无已收集的 CGYRO 结果')
    if 'TGLF' in mode:
        if not run_choices(root):
            problems.append('尚无可供此绘图入口使用的 TGLF 扫描结果')
    return problems


def initialize(root, factory=dict):
    settings = root.setdefault('SETTINGS', factory()).setdefault('WORKBENCH', factory())
    for key, value in DEFAULTS.items():
        settings.setdefault(key, value)
    # Discard only the saved report from the former prerequisite checker.
    # Opening the page must not rerun checks or claim that old results are current.
    message = str(settings.get('message', '') or '')
    if message.startswith('输入转换：') and '\nCGYRO 前置流程：' in message:
        settings['message'] = ''
    sync_cgyro_ion_cases(settings, factory)
    settings.setdefault('cgyro_radii', factory())
    if settings['page'] in ('review', 'multi'):
        if settings['page'] == 'multi':
            settings.setdefault('tglf', factory())['page'] = 'multi'
        settings['page'] = 'tglf'
    if '：脚本已返回。' in str(settings.get('message', '')):
        settings['message'] = ''
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
    shared = shared_issues(root)
    if shared:
        return shared
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
            for key, label in [('queue', '队列 / 分区'), ('w', '运行时限')]:
                if not text_value(cfg, key):
                    problems.append(label + '未填写')
            resource_keys = [('nodes', '节点数'), ('ntasks_per_node', '每节点 MPI 数'),
                             ('array_parallel', 'CGYRO 并发点数')] if scheduler == 'slurm' else [
                             ('nodes', '节点数'), ('ppn', '每节点 MPI 数')]
            for key, label in resource_keys:
                try:
                    value = int(cfg.get(key, 0))
                    if value < 1 or str(value) != str(cfg.get(key, None)).strip():
                        raise ValueError()
                except (TypeError, ValueError):
                    problems.append(label + '必须为正整数')
        if picker != 'localhost':
            for key, label in [('server', '服务器地址'), ('workDir', '工作目录')]:
                if not text_value(cfg, key) and not text_value(remote, key):
                    problems.append(label + '未填写')
    else:
        if name == 'transfer':
            try:
                tgyro_batch_settings(node)
            except ValueError as exc:
                problems.append(str(exc))
            selected = remote.get(text_value(remote, 'serverPicker'), {}) or {}
            if not (text_value(selected, 'environment') or text_value(remote, 'environment')
                    or text_value(setup, 'executable')):
                problems.append('GACODE 环境初始化为空，请应用统一环境')
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


def transfer_generated_rows(root):
    """Inspect saved file names and radius metadata, not solver contents."""
    prefix = ('Transfer_tool', 'OUTPUTS', 'Profiles_gen')
    files = read(root, prefix, {})
    grouped = {}
    for key in files.keys():
        match = re.fullmatch(r'input\.(cgyro|tglf)_(\d+)', str(key))
        if match and int(match.group(2)) > 0:
            grouped.setdefault(int(match.group(2)), {})[match.group(1)] = prefix + (key,)
    metadata = read(root, ('Transfer_tool', 'OUTPUTS', 'Particle_processing', 'local_inputs'), {})
    rows = []
    for nr, paths in sorted(grouped.items()):
        rho = None
        for path in paths.values():
            try:
                value = float(metadata.get(str(path[-1]), {}).get('rho', None))
                if math.isfinite(value):
                    rho = value
                    break
            except (TypeError, ValueError, OverflowError):
                pass
        label = 'nr={}'.format(nr) + (' · rho={:g}'.format(rho) if rho is not None else '')
        rows.append(dict(key=str(nr), label=label, mode='generated', paths=paths))
    prefix = ('Transfer_tool', 'Transfer_file')
    files = read(root, prefix, {})
    paths = {code: prefix + ('input.' + code,) for code in ('cgyro', 'tglf') if 'input.' + code in files}
    if paths:
        rows.append(dict(key='local', label='局部互转文件', mode='imported', paths=paths))
    return rows


def generated_tglf_sources(root):
    sources = {str(radius): json.dumps(['TGLF_scan', 'input.tglf', radius])
               for radius in read(root, ('TGLF_scan', 'input.tglf'), {}).keys()}
    for row in transfer_generated_rows(root):
        if 'tglf' in row['paths']:
            sources['Transfer_tool / ' + row['label']] = json.dumps(row['paths']['tglf'])
    return sources


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
        'cgyro_runs': len([key for key in cg.get('RUN_DB', {}) if not str(key).startswith('__')]),
        'cgyro_status': manifest.get('status', '尚无运行记录'),
        'tglf_radii': len(tg.get('scanResults_spectra', {})),
    }


class ProjectActions:
    """UI action boundary: validate, prepare copies, mutate, then record outcome.

    The injected factory/readers/executor are native OMFIT services. Library
    helpers must not capture a global root: callbacks can outlive a GUI render.
    """
    def __init__(self, root, factory=dict, readers=None, resolve_server=None, workdir=None, register_server=None,
                 remote_execute=None, root_name='root'):
        self.root, self.factory = root, factory
        self.settings = initialize(root, factory)
        self.readers = readers or {}
        self.resolve_server, self.workdir = resolve_server, workdir
        self.register_server = register_server
        self.remote_execute = remote_execute
        self.root_name = str(root_name)
        self._migrate_error_message()
        # Keep old unresolved candidates in history without blocking the workbench.
        for record in pending_inputs(root).values():
            record['status'] = 'kept_current'
        if '请查看参数差异后选择保留或覆盖' in str(self.settings.get('message', '')):
            self.settings['message'] = ''

    def _migrate_error_message(self):
        """Replace legacy pinned exceptions without discarding their history."""
        message = str(self.settings.get('message', '') or '')
        if not message or message.endswith(ERROR_NOTICE_SUFFIX):
            return
        if message.startswith('应用配置失败：'):
            self.report_error('应用配置', message.split('：', 1)[1])
            return
        records = read(self.root, ('PROJECT_STATE', 'activity'), {})
        for record in list(records.values())[::-1]:
            if record.get('status', None) not in ('failed', 'cancelled'):
                continue
            title, error = str(record.get('title', '')), str(record.get('error', ''))
            if error and message == title + '：' + error:
                self.settings['message'] = error_notice(title, record['status'] == 'cancelled')
                return
        if 'Traceback (most recent call last):' in message:
            title, separator, error = message.partition('：')
            if separator:
                self.report_error(title, error)

    def _record(self, title, **values):
        state = self.root.setdefault('PROJECT_STATE', self.factory())
        records = state.setdefault('activity', self.factory())
        key = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8]
        record = self.factory()
        record.update(dict(id=key, title=title, created=datetime.now(timezone.utc).isoformat(), **values))
        records[key] = record
        return record

    def report_error(self, title, exc, record=None):
        if record is None:
            record = self._record(title)
        cancelled = isinstance(exc, KeyboardInterrupt) or record.get('status', None) == 'cancelled'
        record.update(dict(status='cancelled' if cancelled else 'failed', error=str(exc)))
        self.settings['message'] = error_notice(title, cancelled)
        return record

    def clear_failed_tglf_records(self):
        scan, keys = self.root.get('TGLF_scan', {}), []
        for branch in ('_workbench_runs', 'RUN_DB'):  # RUN_DB is old-project compatibility only.
            runs = scan.get(branch, {})
            failed = [key for key, record in runs.items() if fully_failed(record)]
            for key in failed:
                del runs[key]
            keys.extend(failed)
        settings, _ = initialize_tglf(self.root, self.factory)
        if settings.get('result_run', '') in keys:
            settings['result_run'] = ''
            settings['result_point'] = ''
        self._record('清理 TGLF 失败记录', status='complete', removed_run_ids=keys)
        self.settings['message'] = ''

    def open_page(self, page):
        if page in ('review', 'multi'):
            settings, _ = initialize_tglf(self.root, self.factory)
            settings['page'] = 'multi' if page == 'multi' else 'scan'
            if page == 'review':
                settings['scan_page'] = 'input'
            page = 'tglf'
        self.settings['page'] = page

    def call(self, title, path, **kwargs):
        task = read(self.root, path)
        if task is None:
            raise ValueError('工程缺少入口：' + '/'.join(path))
        record = self._record(title, status='running')
        try:
            result = task_action(task, **kwargs)
        except BaseException as exc:
            self.report_error(title, exc, record)
            raise
        record['status'] = 'returned'
        self.settings['message'] = '' if 'GUIS' in path else title + '：脚本已返回。计算状态请查看对应运行记录。'
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

    def save_transfer_input(self, path, edits, expected_digest):
        path = tuple(path)
        available = [source for row in transfer_generated_rows(self.root) for source in row['paths'].values()]
        available.extend(row['path'] for row in tglf_rows(self.root))
        current = read(self.root, path)
        if path not in available or current is None or input_digest(current) != expected_digest:
            raise ValueError('输入已更新，请点击“重载 / 撤销”后重新编辑。')
        code = 'cgyro' if str(path[-1]).startswith('input.cgyro') else 'tglf'
        changes = {}
        for name, text in edits.items():
            if name not in current or str(name).startswith('__'):
                raise ValueError('参数已变化：' + str(name))
            parsed = transfer_parameter_value(code, name, text, current[name])
            if input_digest(parsed) != input_digest(current[name]):
                changes[name] = parsed
        if not changes:
            return current
        candidate = current.duplicate() if hasattr(current, 'duplicate') else copy.deepcopy(current)
        candidate.update(changes)
        validate_input(candidate, code)
        if hasattr(candidate, 'save'):
            candidate.save()
        if input_digest(read(self.root, path)) != expected_digest:
            raise ValueError('保存期间输入已更新，请重载后再编辑。')
        if path == MODULES['tglf'] + ('FILES', 'input.tglf'):
            self.install_tglf(candidate, '编辑 TGLF 当前输入（{} 项）'.format(len(changes)))
        else:
            self.replace('编辑 {}（{} 项）'.format(path[-1], len(changes)), [(path, candidate)])
        return read(self.root, path)

    def import_input(self, kind, location=None):
        filename = self.settings[kind + '_file']
        if not filename:
            return
        if isinstance(filename, (list, tuple)):
            path, server, tunnel = filename
            server, tunnel = server or 'localhost', tunnel or ''
            obj = self.readers[kind](str(path), server=server, tunnel=tunnel)
        else:
            path, server, tunnel = str(filename), 'localhost', ''
            obj = self.readers[kind](filename)
        validate_input(obj, kind)
        if kind == 'cgyro':
            target = MODULES['transfer'] + ('Transfer_file', 'input.cgyro')
            self.replace('载入 Transfer tool 待准备输入', [(target, obj)])
            self.settings.update(dict(cgyro_file='', page='cgyro', cgyro_source_mode='imported'))
            self.settings['cgyro_import_source'] = dict(path=str(path), server=str(server), tunnel=str(tunnel))
            sync_cgyro_choices(self.root, self.settings, self.factory)
            self.settings['message'] = 'input.cgyro 已载入，可直接设置 CGYRO 扫描。'
            return
        detected = tglf_input_format(obj)
        self.propose_tglf(obj, '导入 TGLF 文件：' + str(path))
        self.settings['tglf_import_source'] = dict(path=str(path), server=str(server), tunnel=str(tunnel), format=detected)
        initialize_tglf(self.root, self.factory)[0].update(dict(source='current', page='scan', scan_page='settings'))
        self.settings[kind + '_file'] = str(path)

    def handoff(self, target, source=None):
        if target == 'cgyro':
            return self.prepare_cgyro_batch()
        selected = self.settings['transfer_source'] if source is None else source
        if selected not in transfer_sources(self.root).values():
            raise ValueError('请先选择 Transfer tool 中的输入或生成结果。')
        source_path = tuple(json.loads(selected))
        source = read(self.root, source_path)
        kind = str(source_path[-1]).split('_')[0]
        if target == 'tglf':
            if kind != 'input.' + target:
                raise ValueError('此目标需要 input.' + target + '，请先转换或选择对应文件。')
            validate_input(source, target)
            if source_path[:3] == ('Transfer_tool', 'OUTPUTS', 'Profiles_gen'):
                physics = self.root['Transfer_tool']['SETTINGS']['PHYSICS']
                chosen = particle_options(physics.get('generation', {}))
                previous_options = read(self.root, ('Transfer_tool', 'OUTPUTS', 'Particle_processing', 'options'))
                if previous_options is None or input_digest(chosen) != input_digest(previous_options):
                    raise ValueError('粒子方案或主离子识别半径已变化，或旧结果缺少自动识别记录；请重新运行 Transfer_tool 后再传递。')
            self.propose_tglf(source, 'Transfer tool → TGLF', source_path)
            return
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
                          'scanResults2D', 'scanResults2D_spectra', 'scanResults3D', 'scanResults3D_spectra', 'UQResults', 'UQResults_spectra',
                          'Experimental_fluxes', 'Experimental_spectra', '_scan_cache_provenance', '_workbench_index',
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

    def prepare_cgyro_batch(self, install_first=True):
        problems = cgyro_plan_issues(self.root)
        if problems:
            raise ValueError('；'.join(problems))
        rows = sync_cgyro_choices(self.root, self.settings, self.factory)
        ion_cases = [key for key in ION_CASES
                     if bool(sync_cgyro_ion_cases(self.settings, self.factory).get(key, False))]
        batch, records, plan = self.factory(), self.factory(), []
        physics = module(self.root, 'cgyro')['SETTINGS']['PHYSICS']
        dimensions = int(module(self.root, 'cgyro')['SETTINGS']['SETUP']['idimrun'])
        for row in rows:
            if not bool(self.settings['cgyro_radii'].get(row['key'], False)):
                continue
            source = read(self.root, row['path'])
            mains = _cgyro_main_indices(self.root, source, row['path'], row.get('particle_record', None))
            nr_key = row.get('batch_key', str(row['nr']))
            radial = self.factory()
            case_records = self.factory()
            source_ion_label = _original_ion_label(source, mains)
            for ion_case in ion_cases:
                value, case_physics, provenance, fixed = _cgyro_case_input(
                    self.root, row, source, ion_case, physics, dimensions)
                radial[ion_case] = value
                case_records[ion_case] = dict(isotope_preparation=provenance, fixed_parameters=dict(fixed),
                    scan_axes=configured_scan_axes(case_physics, dimensions, value))
                plan.append(dict(nr=row['nr'], rho=row['rho'], ion_case=ion_case, batch_key=nr_key,
                                 runid=scheme_runid(module(self.root, 'cgyro')['SETTINGS']['EXPERIMENT']['runid'],
                                                   row.get('scheme', '')),
                                 ion_label=source_ion_label if ion_case == 'BASE' else ion_case,
                                 case_id=_cgyro_case_id(row, ion_case), source_key=row['key'],
                                 source=list(row['path']),
                                 changed_main_species=provenance['source_main_species'] if provenance else [],
                                 isotope_preparation=provenance,
                                 scan_axes=configured_scan_axes(case_physics, dimensions, value)))
            batch[nr_key] = radial
            record = self.factory()
            record.update(dict(source=list(row['path']), source_digest=input_digest(source),
                               rho=row['rho'], main_species=mains, cases=ion_cases,
                               fixed_parameters=dict(fixed),
                               case_preparation=case_records,
                               original_ion_label=source_ion_label))
            records[nr_key] = record
        if not plan:
            raise ValueError('没有可运行的 CGYRO 组合。')
        node = module(self.root, 'cgyro')
        first = plan[0]
        active = batch[first['batch_key']][first['ion_case']]
        marker = self.factory()
        # Resolve metadata against the original sources before installing the
        # first isotope copy (especially when source_mode is 'current').
        scan = cgyro_plan_summary(self.root)
        marker.update(dict(status='ready', inputs=records,
                           upstream_digest=transfer_upstream_digest(self.root),
                           batch_digest=input_digest(batch), combinations=len(plan),
                           scan_axes=copy.deepcopy(scan['axes']),
                           points_per_case=scan['points_per_case'], total_points=scan['total_points']))
        active_copy = (active.duplicate() if hasattr(active, 'duplicate') else copy.deepcopy(active)) if install_first else None
        node['BATCH_INPUTS'] = batch
        if install_first:
            node['INPUTS']['input.cgyro'] = active_copy
        self._record('准备 CGYRO 批量输入', status='ready', combinations=len(plan),
                     batch_digest=marker['batch_digest'])
        pipeline = self.root.setdefault('PROJECT_STATE', self.factory()).setdefault('pipeline', self.factory())
        pipeline['cgyro'] = marker
        self.settings['message'] = 'CGYRO 已准备 {} 个组合。'.format(len(plan))
        return plan

    def edit_cgyro_parameter(self, name):
        """A committed native Entry edit applies directly, without a checkbox."""
        physics = module(self.root, 'cgyro')['SETTINGS']['PHYSICS']
        physics['fixed_parameters'][name]['enabled'] = True
        self.settings['message'] = name + ' 已更新。'

    def inherit_cgyro_parameters(self):
        physics = module(self.root, 'cgyro')['SETTINGS']['PHYSICS']
        for item in physics.get('fixed_parameters', {}).values():
            item['enabled'] = False
        self.settings['message'] = '固定参数已改为沿用各输入。'

    def reset_cgyro_parameters(self, names, source_key=''):
        rows = sync_cgyro_choices(self.root, self.settings, self.factory)
        row = next((item for item in rows if item['key'] == source_key), None)
        if source_key and row is None:
            raise ValueError('参考输入已变化，请重新选择。')
        source = read(self.root, row['path']) if row is not None else {}
        physics = module(self.root, 'cgyro')['SETTINGS']['PHYSICS']
        parameters = initialize_parameters(physics, source, self.factory)
        values = numeric_source(source)
        catalog = parameter_catalog([source])
        for name in names:
            if name not in parameters:
                continue
            parameters[name]['enabled'] = False
            if name in catalog:
                parameters[name]['value'] = values.get(name, catalog[name]['reference'])
        self.settings['message'] = '参数已恢复为沿用各输入的值。'

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
            return ['服务器“{}”尚未登记，请选择已有配置或点击“新增服务器”。'.format(picker)]
        if not text_value(endpoint, 'server'):
            return ['OMFIT 服务器“{}”尚未填写有效的连接地址，请在个人服务器设置中补充。'.format(picker)]
        if match_connection and any(text_value(config, key) != text_value(endpoint, key) for key in ('server', 'tunnel')):
            return ['工程连接与 OMFIT 个人服务器配置不一致。请从 OMFIT 读取连接信息，'
                    '或修改个人服务器设置后重新读取。']
        return []

    def begin_runtime_server(self):
        """Edit a separate connection draft; opening/cancelling cannot switch jobs."""
        if self.register_server is None:
            self.settings['message'] = '当前宿主未提供服务器登记入口，请打开 OMFIT 的个人服务器设置。'
            return
        config = initialize_runtime(self.root, self.factory)
        draft = self.factory()
        # Offer recovery for a project carrying an unregistered server name.
        missing = self.runtime_server_issues()
        draft.update({key: text_value(config, key) if missing else ''
                      for key in ('serverPicker', 'server', 'tunnel', 'workDir')})
        self.settings['server_draft'] = draft
        self.settings['message'] = ''

    def cancel_runtime_server(self):
        self.settings.pop('server_draft', None)
        self.settings['message'] = ''

    def register_runtime_endpoint(self):
        if self.register_server is None:
            self.settings['message'] = '当前宿主未提供服务器登记入口，请打开 OMFIT 的个人服务器设置。'
            return
        draft = self.settings.get('server_draft', None)
        config = draft if draft is not None else initialize_runtime(self.root, self.factory)
        try:
            persisted = self.register_server(config)
        except ValueError as exc:
            self.settings['message'] = str(exc)
            return
        if draft is not None:
            current = initialize_runtime(self.root, self.factory)
            current.update({key: text_value(draft, key) for key in ('serverPicker', 'server', 'tunnel', 'workDir')})
            if current['scheduler'] == 'local':
                current['scheduler'] = 'slurm'
            self.settings.pop('server_draft', None)
        self.settings['message'] = '已登记服务器“{}”；请点击“应用到整个工程”同步计算模块。'.format(
            text_value(config, 'serverPicker'))
        if not persisted:
            self.settings['message'] += ' 当前会话已生效，但个人设置未能保存，请在 OMFIT 首选项中保存设置。'
        return True

    def sync_runtime_endpoint(self, replace_directory=False):
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
        values = dict(server=server, tunnel=str(endpoint.get('tunnel', None) or ''))
        if replace_directory or not text_value(config, 'workDir'):
            directory = text_value(endpoint, 'workDir')
            if not directory and self.workdir is not None:
                try:
                    directory = str(self.workdir(self.root, server))
                except (KeyError, ValueError, TypeError):
                    directory = ''
            values['workDir'] = directory
        config.update(values)
        if picker == 'localhost':
            config['scheduler'] = 'local'
        elif config['scheduler'] == 'local':
            config['scheduler'] = 'slurm'
        self.settings['message'] = '已读取连接信息；确认配置后点击“应用到整个工程”。'

    def select_gacode_install(self, location=None):
        """Select one shared installation for all programs and the script."""
        if self.settings.get('gacode_draft', None) is not None or self.settings.get('server_draft', None) is not None:
            raise ValueError('请先保存或取消正在编辑的配置')
        name = str(self.settings.get('gacode_selected', '') or '')
        if not name:
            self.settings['message'] = '请在“常用配置”分别选择程序版本。'
            return
        config = initialize_runtime(self.root, self.factory)
        path = str(config['gacode_installs'].get(name, '') or '')
        if not valid_path(path):
            raise ValueError('请先保存有效的安装路径：' + name)
        for program in PROGRAMS:
            config[program + '_install'] = name
        sync_environment(config)
        self.settings['gacode_entry'] = name
        self.settings['message'] = '已选用 ' + name + '，环境脚本已同步；点击“应用到整个工程”。'

    def begin_gacode_install(self, edit=False):
        config = initialize_runtime(self.root, self.factory)
        name = str(self.settings.get('gacode_entry', '') or '') if edit else ''
        installs = config['gacode_installs']
        if edit and name not in installs:
            raise ValueError('请先选择要编辑的 GACODE 安装')
        self.settings['gacode_draft'] = dict(name=name, path=str(installs.get(name, '') or ''), original=name)

    def save_gacode_install(self):
        draft = self.settings.get('gacode_draft', None)
        if draft is None:
            return
        name, path = str(draft['name']).strip(), str(draft['path']).strip().rstrip('/')
        if not name or len(name) > 100 or any(ord(char) < 32 for char in name):
            raise ValueError('请填写有效的安装名称')
        if not valid_path(path):
            raise ValueError('请填写 GACODE 根目录的绝对路径')
        config = initialize_runtime(self.root, self.factory)
        installs, original = config['gacode_installs'], draft['original']
        if name in installs and name != original:
            raise ValueError('安装名称已存在，请换一个名称')
        if any(str(value) == path and key != original for key, value in installs.items()):
            raise ValueError('此路径已在安装列表中')
        if original and original != name:
            installs.pop(original)
            for program in PROGRAMS:
                if config[program + '_install'] == original:
                    config[program + '_install'] = name
        installs[name] = path
        self.settings['gacode_entry'] = name
        self.settings.pop('gacode_draft', None)
        self.settings['message'] = '安装路径已保存；点击自动检测检查程序。'

    def cancel_gacode_install(self):
        self.settings.pop('gacode_draft', None)

    def remove_gacode_install(self):
        config = initialize_runtime(self.root, self.factory)
        name = str(self.settings.get('gacode_entry', '') or '')
        if any(config[program + '_install'] == name for program in PROGRAMS):
            raise ValueError('此安装仍被使用，请先在“常用配置”更换程序版本')
        config['gacode_installs'].pop(name, None)
        self.settings['gacode_entry'] = ''
        self.settings['message'] = '已从安装列表移除；服务器文件保留。'

    def _probe_gacode(self, scan=True):
        if self.remote_execute is None:
            raise ValueError('当前宿主未提供服务器检测入口')
        config = initialize_runtime(self.root, self.factory)
        issues = self.runtime_server_issues(match_connection=True)
        if issues:
            raise ValueError('；'.join(issues))
        stdout, stderr = [], []
        os.environ.setdefault('SHELL', '/bin/bash')
        script = probe_script(config, scan) + (capability_probe() if scan else '')
        code = self.remote_execute(str(config['server']), 'bash -c ' + shlex.quote(script),
                                   '.', tunnel=str(config.get('tunnel', '') or ''), std_out=stdout, std_err=stderr,
                                   quiet=True, ignoreReturnCode=True, use_bang_command=False)
        if code != 0:
            raise RuntimeError('GACODE 自动检测失败；原列表保留。\n' + '\n'.join(stderr)[-2000:])
        records = parse_probe(stdout)
        # Parse everything before mutating settings; an interrupted capability
        # scan must not replace a previously valid installation inventory.
        profile = parse_capabilities(stdout, config) if scan else None
        added, detection = merge_probe(config, records, self.factory)
        state = self.root.setdefault('PROJECT_STATE', self.factory())
        previous = state.get('gacode_detection', {})
        if same_endpoint(previous.get('endpoint', {}), detection['endpoint']):
            entries = dict(previous.get('entries', {}))
            entries.update(records)
            detection['entries'] = entries
            if profile is None and previous.get('capabilities', {}):
                detection['capabilities'] = copy.deepcopy(previous['capabilities'])
        if profile is not None:
            detection['capabilities'] = profile
        state['gacode_detection'] = detection
        if self.settings.get('gacode_entry', '') not in config['gacode_installs']:
            self.settings['gacode_entry'] = next(iter(config['gacode_installs']), '')
        return added, detection

    def detect_gacode(self):
        if self.settings.get('server_draft', None) is not None:
            raise ValueError('请先保存或取消正在编辑的服务器')
        if self.settings.get('gacode_draft', None) is not None:
            raise ValueError('请先保存或取消正在编辑的安装')
        added, detection = self._probe_gacode()
        config = initialize_runtime(self.root, self.factory)
        profile = matching_profile(config, detection)
        changes = adapt_draft(config, profile)
        if profile:
            profile['draft_changes'] = changes
        self.settings['message'] = '检测完成：{} 套安装，新增 {} 套。选择各程序版本后应用。'.format(
            len(detection['entries']), added)
        if changes:
            self.settings['message'] += '资源草稿调整：' + '；'.join(changes) + '。应用后生效。'
        return detection

    def apply_runtime(self, progress=None):
        if self.settings.get('server_draft', None) is not None:
            self.settings['message'] = '请先保存或取消新增服务器。'
            return
        if self.settings.get('gacode_draft', None) is not None:
            self.settings['message'] = '请先保存或取消 GACODE 安装编辑。'
            return
        issues = self.runtime_server_issues(match_connection=True)
        if issues:
            self.settings['message'] = '；'.join(issues)
            return
        config = initialize_runtime(self.root, self.factory)
        profile = matching_profile(config, self.root.get('PROJECT_STATE', {}).get('gacode_detection', {}))
        issues = resource_issues(config, profile)
        if issues:
            raise ValueError('；'.join(issues))
        original = runtime_values(config)
        if config['gacode_installs']:
            detection = self.root.get('PROJECT_STATE', {}).get('gacode_detection', {})
            if not detection_is_current(config, detection):
                if progress is not None:
                    progress('正在校验服务器上的 GACODE 安装…')
                _, detection = self._probe_gacode(scan=False)
            if runtime_values(config) != original:
                raise ValueError('校验期间配置已改变，请重新应用')
            issues = installation_issues(config, detection)
            if issues:
                raise ValueError('；'.join(issues))
        if progress is not None:
            progress('正在同步各模块的运行配置…')
        targets = apply_runtime(self.root, self.factory)
        self.settings['message'] = '统一 GACODE 环境已应用到 {} 个模块；案例和结果保留。'.format(len(targets))
        self._record('应用统一 GACODE 环境', status='complete', modules=targets)
        return targets

    def run_cgyro(self, prepare=False):
        node = module(self.root, 'cgyro')
        if node['SETTINGS']['SETUP'].get('icgyro', None) != 1:
            raise ValueError('此页面使用 CGYRO；旧 GYRO 提交后端不可用。')
        issues = cgyro_input_issues(self.root)
        if not prepare:
            issues += runtime_issues(self.root, 'cgyro')
        if issues:
            raise ValueError('；'.join(issues))
        retry_limit(node)
        if not prepare and pending_runs(node):
            if not sync_run_issues(self.root):
                self.sync_cgyro_run()
            if pending_runs(node):
                raise ValueError('上一批 CGYRO 还有活动、待收集或提交状态不明的案例，请先同步并收集结果。')
        plan = self.prepare_cgyro_batch(install_first=prepare)
        if prepare:
            return plan
        setup = node['SETTINGS']['SETUP']
        physics = node['SETTINGS']['PHYSICS']
        if int(physics.get('restart_mode', 0)) == 1 and len(plan) != 1:
            raise ValueError('重启只能运行一个 nr 与一个主离子案例；批量组合请使用“新计算”。')
        remote = node['SETTINGS']['REMOTE_SETUP']
        scheduler = remote.get(str(remote.get('serverPicker', '') or ''), {}).get('scheduler', '')
        queued = str(scheduler).lower() in ('slurm', 'pbs')
        batch_id = uuid.uuid4().hex if queued else ''
        original_batch = copy.deepcopy(node.get('RUN_BATCH', self.factory()))
        if queued:
            batch = self.factory()
            batch.update(dict(batch_id=batch_id, case_ids=[item['case_id'] for item in plan],
                              tokens=[], status='submitting', stop_requested=False))
            node['RUN_BATCH'] = batch
        else:
            node['RUN_BATCH'] = self.factory()
        previous = dict(irun=setup.get('irun', None), idownsync=setup.get('idownsync', None))
        original_input = node['INPUTS'].get('input.cgyro', None)
        experiment = node['SETTINGS']['EXPERIMENT']
        original_runid = experiment['runid']
        case_keys = ('nr', 'rho', 'mass', 'case_id')
        # Missing is different from a saved None in native settings. Restore
        # membership as well as values after a failed/cancelled batch.
        original_case = {key: physics[key] for key in case_keys if key in physics}
        dimensions = int(setup['idimrun'])
        group_name = str(dimensions) + 'd'
        original_controls = {key: physics.get(key, None) for key in ('fixed_parameters', group_name)}
        original_physics = {key: physics[key] for key in physics.keys()}
        record = self._record('CGYRO 批量扫描', status='running', combinations=copy.deepcopy(plan))
        completed = []
        collecting = False
        try:
            setup['irun'], setup['idownsync'] = 1, 0 if queued else 1
            for case_number, item in enumerate(plan):
                nr, ion_case = item['nr'], item['ion_case']
                provenance = item.get('isotope_preparation', None)
                case_physics = (remap_physics(original_physics, dimensions, provenance['index_map'])
                                if provenance else original_physics)
                for key in original_controls:
                    if key in case_physics:
                        physics[key] = case_physics[key]
                    else:
                        physics.pop(key, None)
                node['INPUTS']['input.cgyro'] = node['BATCH_INPUTS'][item['batch_key']][ion_case].duplicate()
                experiment['runid'] = item['runid']
                physics['nr'], physics['rho'], physics['mass'] = nr, item['rho'], ion_case
                physics['case_id'] = item['case_id']
                print('[CGYRO] Starting case {}: initializing native task context.'.format(item['case_id']), flush=True)
                self.call('CGYRO {}'.format(item['case_id']),
                           MODULES['cgyro'] + ('SCRIPTS', 'runCGYRO.py'),
                           wait_for_completion=not queued, batch_id=batch_id, check_temp_start=case_number == 0)
                manifest = node.get('RUN_MANIFEST', {})
                if manifest.get('stop_requested', False):
                    if queued:
                        collecting = True
                        completed = self._collect_cgyro_queue(automatic=True)
                    record.update(dict(status='cancelled', completed=completed,
                                       stopped_case=item['case_id'], remote_status=manifest.get('status', '')))
                    self.settings['message'] = stop_message(manifest)
                    return completed
                if not queued and manifest.get('status', '') == 'published':
                    completed.append(item['case_id'])
            if queued:
                node['RUN_BATCH']['status'] = 'submitted'
                collecting = True
                completed = self._collect_cgyro_queue(automatic=True)
                if node['RUN_BATCH'].get('stop_requested', False):
                    record.update(dict(status='cancelled', completed=completed))
                    self.settings['message'] = queue_summary(node) + ' 取消后已自动收集，可从结果记录选择未完成点继续计算。'
                    return completed
                if len(completed) != len(plan):
                    record.update(dict(status='partial', completed=completed))
                    self.settings['message'] = queue_summary(node) + ' 未完成案例的原输入和已有输出保留。'
                    return completed
            record.update(dict(status='complete', completed=completed))
            if len(completed) != len(plan):
                record['status'] = 'partial'
                self.settings['message'] = '已有结果已保留，未完成的计算点可从结果记录继续计算。'
                return completed
            self.settings['message'] = '已完成 {} 个输入组合，结果已保存到 RUN_DB。'.format(len(completed))
            return completed
        except BaseException as exc:
            if queued:
                manifest = node.get('RUN_MANIFEST', {})
                if manifest.get('batch_id', '') == batch_id and manifest.get('status', '') == 'prepared':
                    manifest['status'] = 'failed'
                save_current(node, self.factory)
                node['RUN_BATCH'].update(dict(status='partial', error=str(exc)))
                completed = list(node['RUN_BATCH'].get('completed', completed))
                if not node['RUN_BATCH'].get('tokens', []) and manifest.get('batch_id', '') != batch_id:
                    node['RUN_BATCH'] = original_batch  # Preparation failed before any new run was committed.
            record.update(dict(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed',
                               completed=completed, error=str(exc)))
            if (queued and not collecting and node.get('RUN_BATCH', {}).get('stop_requested', False)
                    and node['RUN_BATCH'].get('batch_id', '') == batch_id and isinstance(exc, Exception)):
                # Kill during upload may leave earlier H/D cases accepted. Sync
                # honors the saved stop intent, then collect every confirmed job.
                try:
                    self.call('确认已停止的提交', MODULES['cgyro'] + ('SCRIPTS', 'refresh_run_status.py'))
                except Exception as sync_error:
                    record['stop_sync_error'] = str(sync_error)
                completed = self._collect_cgyro_queue(automatic=True)
                record.update(dict(status='cancelled', completed=completed))
                self.settings['message'] = queue_summary(node) + ' 提交已停止，已有输出已收集。'
                return completed
            raise
        finally:
            experiment['runid'] = original_runid
            setup['irun'], setup['idownsync'] = previous['irun'], previous['idownsync']
            for key in case_keys:
                if key in original_case:
                    physics[key] = original_case[key]
                else:
                    physics.pop(key, None)
            for key, value in original_controls.items():
                if value is None:
                    physics.pop(key, None)
                else:
                    physics[key] = value
            if original_input is None:
                node['INPUTS'].pop('input.cgyro', None)
            else:
                node['INPUTS']['input.cgyro'] = original_input

    def optimize_cgyro_storage(self):
        node = module(self.root, 'cgyro')
        report = consolidate_storage(node, self.factory)
        self.settings['message'] = ('归档已去重：处理 {} 份结果、{} 份提交 ZIP，减少归档载荷约 {:.2f} GB。'
            '检查点已检测择一保留；{} 个结果有备用文件或检查告警，详见 RUN_DB/__STORAGE__/checkpoints。'
            '请另存工程以减少 ZIP 体积。').format(
                report['converted_copies'], report['converted_input_zips'],
                report['duplicate_bytes'] / 1e9, report['checkpoint_warnings'])
        return report

    def _cgyro_script(self, title, name, **kwargs):
        """Adapter used by cgyro_workflow; retain native logging/Abort semantics."""
        return self.call(title, MODULES['cgyro'] + ('SCRIPTS', name), **kwargs)

    def _collect_cgyro_queue(self, automatic=False):
        """Compatibility entry; only run_cgyro may opt into waiting/retries."""
        return collect_batch(module(self.root, 'cgyro'), self._cgyro_script,
                             self.factory, automatic=automatic)

    def set_cgyro_ions(self, location=None):
        mode = self.settings.get('cgyro_ion_mode', 'original')
        if mode in ('original', 'hdt'):
            selected = ('BASE',) if mode == 'original' else ('H', 'D', 'T')
            sync_cgyro_ion_cases(self.settings, self.factory).update({key: key in selected for key in ION_CASES})

    def select_cgyro_radii(self, selected=True):
        rows = sync_cgyro_choices(self.root, self.settings, self.factory)
        self.settings['cgyro_radii'].update({row['key']: bool(selected) for row in rows})

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

    def run_transfer(self):
        node = module(self.root, 'transfer')
        options = dict(initialize_generation(node, self.factory))
        source = node['SETTINGS']['PHYSICS']['start_from']
        issues = runtime_issues(self.root, 'transfer') + generation_issues(node, source, options)
        if pending_inputs(self.root, 'transfer'):
            issues.append('请先确认 Transfer_tool 的 TGLF 种子输入。')
        if issues:
            raise ValueError('；'.join(issues))
        self.call('运行 Transfer_tool', MODULES['transfer'] + ('SCRIPTS', 'main.py'),
                  profile_source=source, radial_settings=options)
        self.settings['cgyro_source_mode'] = 'generated'
        rows = sync_cgyro_choices(self.root, self.settings, self.factory)
        self.settings['message'] = 'Transfer_tool 已完成：已生成 {} 个 CGYRO 半径输入。'.format(len(rows))

    def generate_transfer_schemes(self):
        node = module(self.root, 'transfer')
        issues = runtime_issues(self.root, 'transfer')
        if pending_inputs(self.root, 'transfer'):
            issues.append('请先确认 Transfer_tool 的 TGLF 种子输入。')
        if issues:
            raise ValueError('；'.join(issues))
        options = dict(initialize_generation(node, self.factory))
        def generate(source, settings, label):
            self.call('生成转换方案：' + label, MODULES['transfer'] + ('SCRIPTS', 'main.py'),
                      profile_source=source, radial_settings=settings)
        keys = generate_schemes(node, self.settings.get('transfer_scheme_flags', {}), options,
                                generate, self.factory)
        self.settings['cgyro_source_mode'] = 'schemes'
        sync_cgyro_choices(self.root, self.settings, self.factory)
        self.settings['message'] = '已生成 {} 个转换方案的独立输入；到 CGYRO 扫描页选择半径并提交。'.format(len(keys))

    def check(self):
        problems = []
        shared = shared_issues(self.root)
        if shared:
            problems.append('共用配置：' + '；'.join(shared))
        else:
            for name in MODULES:
                issues = runtime_issues(self.root, name)
                if issues:
                    problems.append(LABELS[name] + '：' + '；'.join(issues))
        issues = cgyro_input_issues(self.root)
        if issues:
            problems.append('CGYRO 输入与扫描：' + '；'.join(issues))
        self.settings['message'] = '需要修改：\n' + '\n'.join(problems) if problems else '配置检查通过'

    def continue_cgyro(self, token, point_ids, additional_time, selections=None, scope=None):
        """Continue frozen archived inputs, then merge only the selected points."""
        issues = runtime_issues(self.root, 'cgyro')
        if issues:
            raise ValueError('；'.join(issues))
        node = module(self.root, 'cgyro')
        plan = continuation_plan(node, token, point_ids, additional_time, selections=selections, scope=scope)
        for point, reason in plan['rejected'].items():
            print('CGYRO 续算跳过 {}：{}'.format(point, reason))
        setup = node['SETTINGS']['SETUP']
        previous = {key: setup.get(key, None) for key in ('irun', 'idownsync', 'idimrun')}
        try:
            setup['irun'], setup['idownsync'] = 1, 1
            setup['idimrun'] = int(plan['info'].get('scan_dimensions', plan['info']['dimensions']))
            self.call('CGYRO 选定计算点续算', MODULES['cgyro'] + ('SCRIPTS', 'runCGYRO.py'),
                      continuation={key: plan[key] for key in ('source_token', 'points', 'additional_time', 'selections', 'scope')})
            manifest = node.get('RUN_MANIFEST', {})
            if manifest.get('status', '') == 'published':
                self.settings['message'] = '已续算并更新 {} 个计算点，其余结果保留。'.format(len(plan['points']))
            elif collection_done(manifest):
                self.settings['message'] = stop_message(manifest)
            elif manifest.get('stop_requested', False):
                self.settings['message'] = stop_message(manifest)
        finally:
            setup.update(previous)
            if plan['rejected']:
                self.settings['message'] += ' {} 个点未提交，原因见控制台。'.format(len(plan['rejected']))

    def collect(self):
        issues = collect_issues(self.root)
        if issues:
            raise ValueError('；'.join(issues))
        node = module(self.root, 'cgyro')
        if queue_records(node) and any(entry['manifest'].get('status', '') != 'published'
                                      for _, entry in queue_records(node)):
            completed = self._collect_cgyro_queue()
            self.settings['message'] = queue_summary(node)
            return completed
        return collect_run(node, self._cgyro_script)

    def sync_cgyro_run(self):
        issues = sync_run_issues(self.root)
        if issues:
            raise ValueError('；'.join(issues))
        self.call('同步 CGYRO 作业状态', MODULES['cgyro'] + ('SCRIPTS', 'refresh_run_status.py'))
        node = module(self.root, 'cgyro')
        if queue_records(node):
            self.settings['message'] = queue_summary(node) + ' 各案例的服务器状态已同步。'
            return
        state = read(self.root, ('CGYRO_scan', 'RUN_MANIFEST', 'status'), '')
        outcome = read(self.root, ('CGYRO_scan', 'RUN_MANIFEST', 'scheduler_sync', 'outcome'), '')
        self.settings['message'] = ('作业已{}；原记录和输出保留。{}'.format(
                                        '取消' if state == 'cancelled' else '失败',
                                        '收集归档已完成，可继续计算。' if collection_done(node['RUN_MANIFEST']) else
                                        '请先收集并归档已有输出，再开始下一次计算。') if state in ('cancelled', 'failed') else
                                    '取消请求已送达 Slurm，正在收尾；可稍后再次同步。' if state == 'cancel_requested' else
                                    '未能确认作业终态，原记录继续保留，请查看运行记录。' if outcome == 'unknown' else
                                    '作业仍在排队或运行。' if outcome == 'active' else
                                    '作业状态已同步；已结束的运行可继续收集结果。')

    def recover_cgyro_job(self):
        """Reconnect through the native script so its SSH/Abort UI stays usable."""
        self.sync_endpoint('cgyro')
        job_id = str(self.settings.get('cgyro_recovery_job', '')).strip()
        original_manifest = (str(self.settings.get('cgyro_recovery_manifest', '')).strip()
                             if self.settings.get('cgyro_recovery_advanced', False) else '')
        self._cgyro_script('按作业号恢复 CGYRO', 'recover_job.py', job_id=job_id,
                          manifest_path=original_manifest)
        self.settings['message'] = ('作业 ' + job_id + ' 的记录已核对。运行中可同步状态；结束后点击'
                                    '“重新收集未归档结果”。请保存工程，以保留恢复记录。')

    def remove_cgyro_radius(self, runid, rho, nr='', expected=None):
        """The view confirms a concrete metadata preview before this action."""
        self._cgyro_script('删除指定 CGYRO 半径', 'remove_radius.py', runid=runid, rho=rho,
                          nr=nr, confirm=True, expected=expected)
        self.settings.pop('cgyro_result_view', None)
        self.settings['message'] = '已删除 {} / ρ={} 的任务记录和工程内结果，请另存工程。'.format(runid, rho)

    def remove_cgyro_tasks(self, tokens, expected, confirmation):
        """Only the reviewed task IDs enter the native deletion script."""
        self._cgyro_script('删除指定 CGYRO 任务', 'remove_tasks.py', tokens=list(tokens),
                          confirm=True, expected=expected, confirmation=confirmation)
        if expected.get('delete_results', False):
            self.settings.pop('cgyro_result_view', None)
        self.settings['message'] = '已删除所选 {} 条任务记录{}；物理文件清理请使用存储整理。'.format(
            len(tokens), '及已确认的结果引用' if expected.get('delete_results', False) else '，已归档结果保留')

    def save_command(self, name):
        command = self.settings.get('command_draft', '').strip()
        if not command:
            raise ValueError('命令不能为空。')
        module(self.root, name)['SETTINGS']['SETUP']['executable'] = command
        self.settings['message'] = LABELS[name] + '：已保存手动命令。'

    def use_generated_tglf(self):
        selected = self.settings.get('generated_tglf_source', None)
        if selected not in generated_tglf_sources(self.root).values():
            raise ValueError('请先选择已生成的局部 TGLF 输入。')
        source = tuple(json.loads(selected))
        if source[0] == 'Transfer_tool':
            return self.handoff('tglf', source=selected)
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
        node.get('_workbench_index', {}).pop(('FILES',), None)
        self.settings['message'] = title + '。原 TGLF 输入和对应结果已保存在输入历史中。'

    def propose_tglf(self, incoming, title, source_path=None, destination='tglf'):
        incoming = incoming.duplicate() if hasattr(incoming, 'duplicate') else copy.deepcopy(incoming)
        if 'rho' in incoming:
            del incoming['rho']  # Remove the legacy Transfer metadata from the solver copy.
        validate_input(incoming, 'tglf')
        if destination not in ('tglf', 'transfer'):
            raise ValueError('未知 TGLF 输入目标')
        branch = 'FILES' if destination == 'tglf' else 'INPUTS'
        current = read(self.root, MODULES[destination] + (branch, 'input.tglf'))
        for record in pending_inputs(self.root, destination).values():
            record['status'] = 'superseded'
        if current is not None and not input_difference(current, incoming):
            self.settings['message'] = '已选用此 TGLF 输入，参数内容未变化。'
            return
        self.install_tglf(incoming, title, destination)

    def run_tglf_plan(self):
        settings, _ = initialize_tglf(self.root, self.factory)
        prepared = tglf_plan(self.root, settings)
        issues = runtime_issues(self.root, 'tglf')
        if issues:
            raise ValueError('；'.join(issues))
        if any(source['group'] == 'transfer' for source in prepared['sources']):
            physics = self.root['Transfer_tool']['SETTINGS']['PHYSICS']
            chosen = particle_options(physics.get('generation', {}))
            previous = read(self.root, ('Transfer_tool', 'OUTPUTS', 'Particle_processing', 'options'))
            if previous is None or input_digest(chosen) != input_digest(previous):
                raise ValueError('粒子方案或半径已变化，请重新运行 Transfer_tool 生成输入。')
        try:
            self.call('运行 TGLF 扫描', ('TGLF_scan', 'SCRIPTS', 'run_workbench'),
                      plan=prepared, project_root=self.root)
        finally:
            settings['page'] = 'results'
        self.settings['message'] = ''

    def set_tglf_profile(self, profile, source):
        profile_info(profile)
        settings, _ = initialize_tglf(self.root, self.factory)
        previous = read(self.root, PROFILE_PATH)
        changed = previous is None or profile_digest(previous) != profile_digest(profile)
        paths = [(MODULES['profiles'] + (group, name), profile)
                 for group in ('INPUTS', 'OUTPUTS') for name in ('input.gacode', 'input.gacode_base')]
        self.replace('载入 TGLF 扫描剖面', paths)
        pg = module(self.root, 'profiles')['SETTINGS']
        pg['PHYSICS']['start_from'] = 'input.gacode'
        pg['DEPENDENCIES']['profpowbal'] = "root['INPUTS']['input.gacode']"
        settings.update(dict(source='radial', page='scan', scan_page='input', profile_source=dict(source),
                             profile_changed=changed or settings.get('profile_changed', False)))
        # Keep the last generated inputs/results until the new complete set is ready.
        self.settings['message'] = ''

    def import_tglf_profile(self):
        settings, _ = initialize_tglf(self.root, self.factory)
        filename = settings['profile_file']
        if not filename:
            return
        if isinstance(filename, (list, tuple)):
            path, server, tunnel = filename
            server, tunnel = server or 'localhost', tunnel or ''
        else:
            path, server, tunnel = str(filename), 'localhost', ''
        # Resolve only literal subscript paths inside this project; never eval a
        # file-picker string or send an OMFIT expression to the file reader.
        prefix = next((item for item in (self.root_name, 'root') if str(path).startswith(item + '[')), None)
        if prefix is not None:
            node = ast.parse('root' + str(path)[len(prefix):], mode='eval').body
            keys = []
            while isinstance(node, ast.Subscript):
                key = ast.literal_eval(node.slice)
                if not isinstance(key, (str, int)) or isinstance(key, bool):
                    raise ValueError('数据树地址只允许字符串或整数节点名')
                keys.insert(0, key)
                node = node.value
            if not isinstance(node, ast.Name) or node.id != 'root':
                raise ValueError('请选择本工程中的 input.gacode 数据树地址')
            profile = read(self.root, keys)
            if profile is None:
                raise ValueError('数据树中不存在该 input.gacode：' + str(path))
            address = self.root_name + location(keys)[4:]
            self.set_tglf_profile(profile, dict(path=address, tree_path=keys))
            settings['profile_file'] = address
            return
        if str(path).startswith('OMFIT['):
            raise ValueError('请选择本工程中的 input.gacode 数据树地址，或使用文件按钮导入')
        profile = self.readers['gacode'](str(path), GACODEtype='gacode', server=server, tunnel=tunnel)
        self.set_tglf_profile(profile, dict(path=str(path), server=str(server), tunnel=str(tunnel)))

    def use_transfer_tglf_profile(self):
        path = ('Transfer_tool', 'INPUTS', 'input.gacode')
        profile = read(self.root, path)
        if profile is None:
            raise ValueError('Transfer_tool 尚无 input.gacode')
        address = self.root_name + location(path)[4:]
        self.set_tglf_profile(profile, dict(path=address, tree_path=list(path)))
        initialize_tglf(self.root, self.factory)[0]['profile_file'] = address

    def generate_tglf_inputs(self):
        settings, _ = initialize_tglf(self.root, self.factory)
        issues = runtime_issues(self.root, 'tgyro')
        if issues:
            raise ValueError('；'.join(issues))
        profile = read(self.root, PROFILE_PATH)
        if profile is None:
            raise ValueError('请先载入 input.gacode')
        info = profile_info(profile)
        coordinate = settings['profile_coordinate']
        if coordinate not in ('rho', 'r/a') or settings['include_ions'] not in ('thermal', 'all'):
            raise ValueError('请选择径向坐标和离子选项')
        bounds = (info['rho_min'], info['rho_max']) if coordinate == 'rho' else (info['ra_min'], 1.0)
        if bounds[0] > RADII[0] or bounds[1] < RADII[-1]:
            raise ValueError('input.gacode 的 {} 范围不足以生成 0.01–0.99 的输入'.format(coordinate))
        input_text, radii = tgyro_input(profile, dict(radii=RADII, coordinate=coordinate,
                                     bounds=bounds, include_ions=settings['include_ions']))
        tgyro = module(self.root, 'tgyro')
        seed = tgyro['INPUTS'].get('input.tglf', None)
        if seed is None:
            seed = read(self.root, ('Transfer_tool', 'TEMPLATES', 'input.tglf'))
        if seed is None:
            raise ValueError('缺少 TGLF 种子输入，请恢复模板中的 input.tglf')
        parameters = generation_overrides(self.root, settings)
        remote = tgyro['SETTINGS']['REMOTE_SETUP']
        selected = remote.get(str(remote.get('serverPicker', '')), {})
        environment = str(selected.get('environment', '') or remote.get('environment', '') or '')
        if not environment.strip():
            raise ValueError('请在环境配置页应用 TGYRO 环境和队列')
        applied = applied_runtime(self.root) or {}
        command = str(applied.get('prepare_command', 'tgyro -t . -n {n_radii}')).replace('{n_radii}', str(len(radii)))
        self.call('生成 TGLF 输入文件', ('TGLF_scan', 'SCRIPTS', 'generate_tglf_inputs'),
            profile=profile, seed=seed, input_text=input_text, radii=list(radii),
            coordinate=coordinate, include_ions=settings['include_ions'],
            profile_digest=profile_digest(profile), source=dict(settings.get('profile_source', {})),
            environment=environment, command=command, parameters=parameters)
        settings.update(dict(source='radial', page='scan', scan_page='settings', profile_changed=False))
        self.settings['message'] = '输入文件已生成。'

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
