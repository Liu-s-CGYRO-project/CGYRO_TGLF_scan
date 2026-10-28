"""Lightweight run summaries and references to native TGLF result branches."""
from builtins import dict, hasattr, len, list, set, str, tuple
from collections import ChainMap
import copy
from datetime import datetime, timezone


def run_records(module):
    # Existing projects keep their old payloads. No migration, parsing or copy
    # is performed by a selector; new submissions only write _workbench_runs.
    return ChainMap(module.get('_workbench_runs', {}), module.get('RUN_DB', {}))


def at(module, path, default=None):
    for key in path:
        if not hasattr(module, 'get'):
            return default
        module = module.get(key, default)
    return module


def native_destination(source, mode, parameters):
    """Match native single-file/radial shapes, including outer-to-inner axes.

    Transfer inputs carry explicit radii and use the outer radial branches.
    Single-file inputs use the native child module, without a custom result root.
    """
    group = source.get('group', 'current')
    radial_source = group in ('radial', 'transfer')
    if radial_source and source.get('rho', None) is None:
        raise ValueError('输入缺少已确认半径，无法写入原生 TGLF 扫描：' + source.get('label', source.get('key', '输入')))
    prefix = [] if radial_source else ['TGLF']
    radial = [source['rho']] if radial_source else []
    if mode == 'single':
        return prefix, (['Experimental_fluxes'] + radial if radial else []), (
            ['Experimental_spectra'] + radial if radial else ['FILES'])
    names = list(parameters)
    if mode == 'uq':
        key = 'UQResults'
        coordinates = ['_'.join(names), '_'.join(str(parameters[name]) for name in names)]
    else:
        key = {'1d': 'scanResults', '2d': 'scanResults2D', '3d': 'scanResults3D'}[mode]
        names = names[::-1]  # Native 2D: param2+param / value2 / value1.
        coordinates = ['+'.join(names)] + [parameters[name] for name in names]
    return prefix, [key] + radial + coordinates, [key + '_spectra'] + radial + coordinates


def _put(module, path, value, factory):
    for key in path[:-1]:
        module = module.setdefault(key, factory())
    module[path[-1]] = value


def _forget_native_cache(scope, source, mode, flux_path):
    # Native provenance describes a complete scan group, not individual points.
    # Replacing a point through the workbench makes that group's digest stale.
    radial = source.get('group', 'current') in ('radial', 'transfer')
    if mode == 'single':
        if radial:
            scope.get('_radial_cache_provenance', {}).pop(source['rho'], None)
        return
    records = scope.get('_scan_cache_provenance', {})
    if radial:
        records = records.get(source['rho'], {})
    branch = flux_path[0]
    if mode == 'uq':
        records.pop(branch, None)
    else:
        group = flux_path[2 if radial else 1]
        records = records.get(branch, {})
        records.pop(group, None)
        records.pop(group + '_rows', None)


def publish_point(module, record, point_id, source, result, factory=dict, baseline=None):
    """Publish an already validated point; the run retains only its summary."""
    point = record['points'][point_id]
    prefix, flux_path, result_path = native_destination(source, record['mode'], point['parameters'])
    scope = module
    for key in prefix:
        scope = scope.setdefault(key, factory())
    if 'input.tglf' not in result and 'input' in point:
        result['input.tglf'] = point['input']
    if flux_path:
        data = result['gbflux'] if record['mode'] == 'single' else result['gbflux']['data']
        _put(scope, flux_path, data, factory)
    _put(scope, result_path, result, factory)
    if source.get('group', None) == 'transfer' and baseline is not None:
        # Native radial plots also read input.tglf[rho]. Keep this source's
        # frozen baseline, not the final point's scanned parameter values.
        module.setdefault('input.tglf', factory())[source['rho']] = baseline
    _forget_native_cache(scope, source, record['mode'], flux_path)
    owner = record['id'] + ':' + point_id
    # Plain metadata mapping: no physical result objects or array copies.
    scope.setdefault('_workbench_index', {})[tuple(result_path)] = owner
    point.update(dict(result_path=prefix + result_path, owner_path=prefix + ['_workbench_index'],
                      owner_key=result_path, owner=owner))
    point.pop('input', None)
    point.pop('result', None)


def result_location(point):
    """Exact saved tree path from metadata; never resolve the physical result."""
    path = point.get('result_path', None)
    if path is None:
        return '旧运行记录内的结果（兼容读取）'
    return 'TGLF_scan' + ''.join('[{!r}]'.format(key) for key in path)


def restore_native_results(module, record, factory=dict):
    """Move this record's retained custom-scope points into native empty slots.

    No global traversal, result parsing or history reconstruction. Existing
    target results are never replaced by an older record's repair operation.
    """
    sources = {tuple(source['path']): source for source in record.get('plan', {}).get('sources', [])}
    report = dict(moved=0, conflicts=[], unavailable=[])
    restored_radii = set()
    for key, point in record.get('points', {}).items():
        old_path = point.get('result_path', [])
        if not old_path or old_path[0] != 'sourceResults' or not point_current(module, point):
            continue
        source = sources.get(tuple(point.get('source', [])), None)
        if source is None or source.get('group', None) not in ('current', 'local', 'transfer', 'radial'):
            report['unavailable'].append(key + '：原记录没有精确输入来源')
            continue
        try:
            prefix, flux_path, result_path = native_destination(source, record['mode'], point['parameters'])
        except ValueError as exc:
            report['unavailable'].append(key + '：' + str(exc))
            continue
        if at(module, prefix + result_path) is not None or (flux_path and at(module, prefix + flux_path) is not None):
            report['conflicts'].append(key + '：目标已有结果，保留原位置 ' + result_location(point))
            continue
        result = point_result(module, point)
        input_file = result.get('input.tglf', None)
        if source.get('group', None) == 'transfer' and input_file is None:
            report['unavailable'].append(key + '：原结果没有保存 input.tglf，保留原位置')
            continue
        baseline = None
        if source.get('group', None) == 'transfer' and source['rho'] not in restored_radii:
            # Old records did not retain the pre-scan baseline. Use this exact
            # archived point as the native plot's reference input, once/radius.
            baseline = input_file.duplicate() if hasattr(input_file, 'duplicate') else copy.deepcopy(input_file)
        old_owner_path, old_owner_key = point['owner_path'], tuple(point['owner_key'])
        # Old custom scopes have no radius level. Derive the matching flux
        # coordinate from the exact selected result path, never point number.
        old_flux = old_path[:2] + [flux_path[0]] + old_path[3:] if flux_path else []
        publish_point(module, record, key, source, result, factory, baseline=baseline)
        if baseline is not None:
            restored_radii.add(source['rho'])
        at(module, old_path[:-1], {}).pop(old_path[-1], None)
        if old_flux:
            at(module, old_flux[:-1], {}).pop(old_flux[-1], None)
        at(module, old_owner_path, {}).pop(old_owner_key, None)
        report['moved'] += 1
    return report


def point_current(module, point):
    if point.get('status', None) != 'complete':
        return False
    if 'result_path' not in point:
        return True  # Read-only compatibility with pre-native workbench runs.
    return at(module, point['owner_path'], {}).get(tuple(point['owner_key']), None) == point['owner']


def point_result(module, point):
    """Resolve only the explicitly selected point, never another run's payload."""
    if not point_current(module, point):
        raise ValueError('该 TGLF 点已被替换或重置，请选择当前原生扫描结果。')
    result = at(module, point['result_path']) if 'result_path' in point else point.get('result', None)
    if result is None:
        raise ValueError('所选 TGLF 点的原生结果已不存在。')
    return result


def record_summary(record, run_id):
    """Show local time and scan parameter names, without reading result data."""
    try:
        moment = datetime.fromisoformat(str(record.get('created', '')).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        try:
            moment = datetime.strptime(str(run_id).split('_')[0], '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
        except ValueError:
            moment = None
    if moment is None:
        when = '时间未知'
        source = record.get('migration_source', [])
        if source and str(source[0]).startswith('scanResults'):
            when = '旧版谱' if str(source[0]).endswith('_spectra') else '旧版通量'
    else:
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        moment = moment.astimezone()
        when = moment.strftime('%m-%d %H:%M:%S' if moment.year == datetime.now().year else '%Y-%m-%d %H:%M:%S')
    saved_plan = record.get('plan', {})
    mode = record.get('mode', saved_plan.get('mode', ''))
    axes = saved_plan.get('uq', []) if mode == 'uq' else saved_plan.get('axes', [])
    captions = []
    for axis in axes:
        name = str(axis.get('name', '')).strip()
        if name and name not in captions:
            captions.append(name)
    return '{} · {}'.format(when, ' + '.join(captions) or '原值')

