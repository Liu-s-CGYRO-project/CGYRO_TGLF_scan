"""Isolated TGYRO local dumps and TGLF executions through OMFIT."""
from builtins import all, dict, enumerate, float, int, isinstance, len, list, range, sorted, str, zip
import copy
from datetime import datetime, timezone
import os
from pathlib import Path, PurePosixPath
import uuid

from OMFITlib_tglf_multi_data import case_plan, initialize, profile_digest, tgyro_input, tglf_text


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:8]


class OMFITRunner:
    def __init__(self, root, ui, gacode, ascii_file, tglf, workdir, servers, factory=dict):
        self.root, self.ui = root, ui
        self.gacode, self.ascii_file, self.tglf = gacode, ascii_file, tglf
        self.workdir, self.servers, self.factory = workdir, servers, factory

    def endpoint(self, module, settings, relative):
        local = Path(str(self.workdir(self.root, ''))) / 'tglf_multi' / relative
        if settings['execution'] == 'local':
            return str(local) + os.sep, str(local) + os.sep, '', ''
        if settings['execution'] != 'module':
            raise ValueError('未知执行方式。')
        options = self.servers[module]
        server = str(options.get('server') or '')
        if not server:
            raise ValueError('请先在 OMFIT 模块设置中配置 ' + relative.split('/')[0] + ' 的服务器。')
        base = module['SETTINGS']['REMOTE_SETUP'].get('workDir')
        if not base:
            base = self.workdir(module, server)
        base = str(base)
        if not PurePosixPath(base).is_absolute():
            raise ValueError('远程工作目录必须为 Linux 绝对路径。')
        remote = str(PurePosixPath(base) / 'tglf_multi' / relative) + '/'
        return str(local) + os.sep, remote, server, str(options.get('tunnel') or '')

    def preflight(self, settings):
        if not str(settings['tgyro_command']).strip() or not str(settings['tglf_command']).strip():
            raise ValueError('TGYRO 和 TGLF 命令不能为空。')
        for name in ('TGYRO', 'TGLF'):
            self.endpoint(self.root['TGLF_scan'][name], settings, name + '/check')

    def execute(self, name, settings, relative, inputs, command, record):
        module = self.root['TGLF_scan'][name]
        local, remote, server, tunnel = self.endpoint(module, settings, name + '/' + relative)
        # A fresh leaf and clean=False protect every previous calculation.
        Path(local).mkdir(parents=True, exist_ok=False)
        record.update(workdir=local, remotedir=remote, server=server, command=command, stdout=[], stderr=[])
        script = '#!/bin/bash\nset -e\n' + str(settings['environment']) + '\n' + command + '\n'
        record['script'] = script
        code = self.ui.executable(module, inputs=inputs, outputs=['./'], clean=False,
                                  executable='bash %s', script=(script, 'run_case.sh'),
                                  workdir=local, remotedir=remote, server=server, tunnel=tunnel,
                                  ignoreReturnCode=False, std_out=record['stdout'], std_err=record['stderr'])
        record['return_code'] = code
        if code != 0:
            raise RuntimeError('{} 执行失败，返回码 {}。'.format(name, code))
        return Path(local)

    def prepare(self, case, run):
        text, grid = tgyro_input(run['input.gacode'], run['plan'])
        # Only numerical/model settings enter the seed. Geometry, species and
        # gradients are always obtained from this case's input.gacode by TGYRO.
        seed = {'USE_TRANSPORT_MODEL': True}
        run['input.tgyro'] = self.ascii_file('input.tgyro', fromString=text)
        run['seed.tglf'] = self.ascii_file('input.tglf', fromString=tglf_text(seed))
        inputs = [(run['input.gacode'], 'input.gacode'), (run['input.tgyro'], 'input.tgyro')]
        inputs.extend((copy.deepcopy(run['seed.tglf']), 'TGLF{}/input.tglf'.format(i + 1)) for i in range(len(grid)))
        command = run['settings']['tgyro_command'].replace('{n_radii}', str(len(grid)))
        local = self.execute('TGYRO', run['settings'], run['id'] + '/prepare', inputs, command, run['preparation'])
        run['conversion_grid'] = grid
        for index, radius in enumerate(run['plan']['radii']):
            directory = 'TGLF{}'.format(grid.index(radius) + 1)
            path = local / directory / 'out.tglf.localdump'
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError('未生成 TGLF 本地输入：' + str(path))
            generated = self.gacode(str(path))
            for key in ('NS', 'RMIN_LOC', 'Q_LOC', 'RLTS_1'):
                if key not in generated:
                    raise RuntimeError('TGYRO localdump 缺少字段：' + key)
            # Preserve the exact dump separately from explicit user overrides.
            point = self.factory()
            point.update(radius=radius, status='ready', attempts=self.factory())
            point['localdump'] = copy.deepcopy(generated)
            point['input.tglf'] = copy.deepcopy(generated)
            for key, value in run['plan']['parameters'].items():
                if key not in generated:
                    raise ValueError('当前 TGLF 版本的 localdump 不包含参数：' + key)
                point['input.tglf'][key] = value
            run['points']['r{:03d}'.format(index)] = point

    def calculate(self, run, point, point_id, settings=None):
        settings = copy.deepcopy(dict(settings or run['settings']))
        attempt_id = 'attempt_' + stamp()
        attempt = self.factory()
        attempt.update(status='running', created=datetime.now(timezone.utc).isoformat())
        attempt['settings'] = settings
        attempt['input.tglf'] = copy.deepcopy(point['input.tglf'])
        point['attempts'][attempt_id] = attempt
        point['selected_attempt'] = attempt_id
        try:
            local = self.execute('TGLF', settings, run['id'] + '/' + point_id + '/' + attempt_id,
                                 [(attempt['input.tglf'], 'input.tglf')], settings['tglf_command'], attempt)
            result = self.tglf(str(local))
            validate_result(result)
            attempt['result'] = result
            attempt['status'] = 'complete'
        except BaseException as exc:
            attempt.update(status='cancelled' if isinstance(exc, KeyboardInterrupt) else 'failed', error=str(exc))
            raise
        return attempt


def validate_result(result):
    import numpy as np
    if 'eigenvalue_spectrum' not in result or 'gbflux' not in result:
        raise ValueError('TGLF 输出不完整：需要增长率/频率谱和 gbflux。')
    spectrum = result['eigenvalue_spectrum']
    ky = np.asarray(spectrum['ky'], dtype=float)
    if not len(ky) or not np.all(np.isfinite(ky)):
        raise ValueError('TGLF ky 网格无效。')
    for name in ('gamma', 'freq'):
        values = np.asarray(spectrum[name], dtype=float)
        if values.ndim != 2 or values.shape[1] != len(ky) or not np.all(np.isfinite(values)):
            raise ValueError('TGLF 谱数据无效：' + name)
    data = result['gbflux']['data']
    if not len(data):
        raise ValueError('TGLF gbflux 为空。')
    for row in data:
        if not all(np.isfinite(float(value)) for value in list(row)[1:]):
            raise ValueError('TGLF gbflux 包含无效数值。')


def run_selected(root, runner, action='all', factory=dict, progress=None):
    settings, cases = initialize(root, factory)
    if action not in ('all', 'prepare', 'run'):
        raise ValueError('未知运行操作。')
    selected = [(key, case) for key, case in cases.items() if case['enabled']]
    if not selected:
        raise ValueError('请先导入并勾选案例。')
    # Validate all selections before starting any external calculation.
    plans = {key: case_plan(settings, case) for key, case in selected}
    digests = {key: profile_digest(case['input.gacode']) for key, case in selected}
    runner.preflight(settings)
    if action == 'run':
        for key, case in selected:
            previous = case['runs'].get(case['selected_run'])
            if previous is None or previous['status'] in ('preparing', 'prepare_failed', 'cancelled'):
                raise ValueError(case['label'] + '：请先生成输入。')
            if previous['plan'] != plans[key]:
                raise ValueError(case['label'] + '：计算设置已变化，请重新生成输入。')
            if previous['profile_digest'] != digests[key]:
                raise ValueError(case['label'] + '：剖面已变化，请重新生成输入。')
    total_failed = 0
    for key, case in selected:
        if action != 'run':
            run_id = 'run_' + stamp()
            run = factory()
            run.update(id=run_id, label=case['label'], created=datetime.now(timezone.utc).isoformat(),
                       source=case['source'], sha256=case['sha256'], plan=plans[key], profile_digest=digests[key],
                       settings=copy.deepcopy(dict(settings)), status='preparing', points=factory(), preparation=factory())
            run['input.gacode'] = copy.deepcopy(case['input.gacode'])
            case['runs'][run_id] = run
            case['selected_run'] = run_id
        else:
            run = case['runs'][case['selected_run']]
        try:
            if action != 'run':
                settings['status'] = '正在生成输入：' + case['label']
                if progress:
                    progress(settings['status'])
                try:
                    runner.prepare(case, run)
                    run['status'] = 'ready'
                except Exception as exc:
                    run.update(status='prepare_failed', error=str(exc))
                    raise
            if action != 'prepare':
                for point_id, point in run['points'].items():
                    if point['status'] == 'complete':
                        continue
                    point['status'] = 'running'
                    settings['status'] = '{} / {}={}: 正在运行 TGLF'.format(run['label'], run['plan']['coordinate'], point['radius'])
                    if progress:
                        progress(settings['status'])
                    try:
                        runner.calculate(run, point, point_id, settings=settings)
                        point['status'] = 'complete'
                    except Exception as exc:
                        point.update(status='failed', error=str(exc))
                        if not settings['continue_on_error']:
                            run['status'] = 'partial'
                            raise
                run['status'] = 'complete' if all(p['status'] == 'complete' for p in run['points'].values()) else 'partial'
                if run['status'] == 'partial':
                    total_failed += 1
        except KeyboardInterrupt:
            run['status'] = 'cancelled'
            for point in run['points'].values():
                if point['status'] == 'running':
                    point['status'] = 'cancelled'
            settings['status'] = '运行已中止；已有输入、结果和日志保留。'
            raise
        except Exception as exc:
            total_failed += 1
            run['error'] = str(exc)
            if not settings['continue_on_error']:
                settings['status'] = case['label'] + '：' + str(exc)
                raise
    settings['status'] = '{} 个案例处理完毕；{} 个案例有失败项。详情见运行记录。'.format(len(selected), total_failed)
    return {'cases': len(selected), 'failed': total_failed}
