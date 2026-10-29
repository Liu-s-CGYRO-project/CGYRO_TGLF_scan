"""Generate ordinary one-axis scans from one common convergence baseline.

Plans contain small parameter dictionaries only. They never own result files,
consult job ancestry, or perform storage maintenance.
"""
from builtins import (KeyError, TypeError, ValueError, bool, dict, float, int, isinstance, len, list,
                      max, round, set, sorted, str, tuple)
from collections import OrderedDict
from copy import deepcopy
import re
from OMFITlib_cgyro_parameters import FIELDS, constant_parameters, managed_parameter, numeric_source, parameter_value
from OMFITlib_cgyro_scan_values import MAX_VALUES, ky_values, value_list
from OMFITlib_cgyro_archive import (catalog_runs, canonical_case_key, case_scans, result_identity)
from OMFITlib_cgyro_reference import REF, is_native_file, metadata_value, validate_reference

CONTENTS = OrderedDict([('只扫 ky', 0), ('ky + 1 个参数', 1), ('ky + 2 个参数', 2),
                        ('ky + 3 个参数', 3), ('单变量收敛扫描', 'convergence')])
DIRECTIONS = OrderedDict([('N_ENERGY', '能量分辨率'), ('N_XI', '俯仰角分辨率'),
    ('N_RADIAL', 'ballooning 区间'), ('N_THETA', '沿场分辨率'), ('E_MAX', '能量上限'),
    ('ERROR_TOL', '时间步精度')])
BASELINE = OrderedDict([('N_ENERGY', 32), ('N_XI', 48), ('N_RADIAL', 32),
                        ('N_THETA', 32), ('E_MAX', 8)])


def active(physics):
    return physics.get('scan_mode', 'regular') == 'convergence'


def initialize(physics, source=None, factory=dict):
    config = physics.setdefault('convergence', factory())
    config.setdefault('reuse_results', True)
    baseline = config.setdefault('baseline', factory())
    fixed = physics.get('fixed_parameters', {})
    for name, default in BASELINE.items():
        item = fixed.get(name, {})
        baseline.setdefault(name, item.get('value', default) if item.get('enabled', False)
                            else (source or {}).get(name, default))
    groups = config.setdefault('groups', factory())
    for name in DIRECTIONS:
        group = groups.setdefault(name, factory())
        group.setdefault('enabled', name != 'ERROR_TOL')
        if 'fixed' not in group:
            group['fixed'] = {'N_ENERGY': max(64, int(float(baseline['N_ENERGY'])))} if name == 'E_MAX' else {}
        if 'values' in group:
            continue
        center = baseline.get(name, fixed.get(name, {}).get('value', (source or {}).get(name, 1e-4)))
        if name == 'N_ENERGY':
            values = [center, max(1, round(float(center) * 1.5)), max(1, round(float(center) * 2))]
        elif name == 'N_XI':
            values = [max(2, round(float(center) / 3) * 2), center,
                      max(2, round(float(center) * 2 / 3) * 2)]
        elif name in ('N_RADIAL', 'N_THETA'):
            values = [max(1, round(float(center) * .75)), center, max(1, round(float(center) * 1.5))]
        elif name == 'E_MAX':
            values = [center, float(center) * 1.25, float(center) * 1.5]
        else:
            values = [center, float(center) / 10]
        group['values'] = values
    return config


def load_baseline(physics, source, factory=dict):
    """Explicit user action: replace this small baseline and regenerate bounds."""
    physics.pop('convergence', None)
    return initialize(physics, source, factory)


def _numbers(values, source, caption):
    if not hasattr(values, 'items'):
        raise ValueError(caption + ' 请填写参数字典，例如 {\'N_ENERGY\': 64}。')
    result = {}
    for name, value in values.items():
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', name)
                or name == 'KY' or managed_parameter(name) or name not in FIELDS and name not in source):
            raise ValueError(caption + ' 参数无效：' + str(name))
        if isinstance(value, bool):
            raise ValueError(name + ' 请填写数值。')
        result[name] = parameter_value(name, value)
    return result


def groups(physics, source):
    """Deduplicate complete configurations, then retain native scan axes.

    Shared baseline configurations belong to the first enabled direction that
    requests them. The later direction records that provenance, not a second
    submission or a copied result. All directions use the same KY list.
    """
    config = initialize(physics, source)
    baseline = _numbers(config['baseline'], source, '基准参数')
    controls = deepcopy(dict(physics))
    controls.pop('convergence', None)
    controls['scan_mode'] = 'regular'
    fixed = controls.setdefault('fixed_parameters', {})
    for name, value in baseline.items():
        fixed[name] = dict(enabled=True, value=value)
    effective = numeric_source(source)
    effective.update({name: parameter_value(name, item['value']) for name, item in fixed.items()
                      if item.get('enabled', False)})
    effective.update(constant_parameters(controls))
    seen, plans = {}, []
    count = 0
    for name, caption in DIRECTIONS.items():
        group = config['groups'].get(name, {})
        if not group.get('enabled', False):
            continue
        extra = _numbers(group.get('fixed', {}), source, caption + ' 额外固定项')
        if name in extra:
            raise ValueError(caption + ' 不能同时扫描并固定 ' + name)
        if physics.get('constant_parameter', '') == name:
            raise ValueError('constant 参数 ' + name + ' 不能同时作为收敛扫描轴。')
        center = parameter_value(name, effective.get(name, FIELDS[name][2]))
        requested = []
        for value in [center] + value_list(group.get('values', []), name):
            if isinstance(value, bool):
                raise ValueError(name + ' 请填写数值。')
            number = parameter_value(name, value)
            if number not in requested:
                requested.append(number)
        own, shared = [], []
        for number in requested:
            values = dict(effective, **extra)
            values[name] = number
            identity = tuple(sorted((key, float(value)) for key, value in values.items()))
            if identity in seen:
                shared.append(dict(value=number, group=seen[identity]))
            else:
                seen[identity] = name
                own.append(number)
        group_physics = deepcopy(controls)
        for key, value in extra.items():
            group_physics['fixed_parameters'][key] = dict(enabled=True, value=value)
        group_physics['1d'] = dict(Para=name, Range=own)
        count += len(own)
        plans.append(dict(parameter=name, label=caption, values=own,
                          requested=requested, shared=shared, fixed=extra,
                          baseline=dict(baseline), physics=group_physics))
    if not plans:
        raise ValueError('至少勾选一个收敛检查方向。')
    if count * len(ky_values(physics)) > MAX_VALUES:
        raise ValueError('单个输入组合的收敛计划超过 10000 点，请缩小取值范围。')
    return plans


def context(group):
    return {key: deepcopy(group[key]) for key in
            ('parameter', 'baseline', 'requested', 'shared', 'fixed')}


def jobs(physics, source, dimensions, batch_key):
    if not active(physics):
        return [dict(physics=physics, dimensions=dimensions, batch_key=batch_key)]
    return [dict(physics=group['physics'], dimensions=1,
                 batch_key=str(batch_key) + ':convergence:' + group['parameter'],
                 convergence_group=context(group))
            for group in groups(physics, source) if group['values']]


def reusable_points(module, runid, caseid, source, physics, parameter, enabled=True):
    """Explicit preview/submission: inspect only this run/radius/axis index.

    Reuse requires the verified explicit input cached at collection, a retained
    owner and sufficient completed data. Missing old metadata schedules a new
    point; querying an index never backfills it by opening input/result files.
    """
    wanted = [(value, ky) for value in physics['1d']['Range'] for ky in ky_values(physics)]
    pending, coordinates = set(wanted), []
    if not enabled or float(source.get('PROFILE_MODEL', 1)) == 2:
        return dict(submit_coordinates=[list(pair) for pair in wanted], reused_points=0,
                    reused_scope=dict(coordinates=[], unknown=[], issues=[]))
    runtime = {'MAX_TIME', 'RESTART_STEP', 'MPI_RANK_ORDER', 'TOROIDALS_PER_PROC',
               'MPIIO_STRIPE_FACTOR', 'MPIIO_SMALL_STRIPE_FACTOR'}
    base = {str(name): float(source[name]) for name in source.keys()
            if re.fullmatch(r'[A-Z][A-Z0-9_]*', str(name))}
    pool = module.get('RUN_DB', {}).get('__STORE__', {})
    cases = catalog_runs(module, runid, caseid).get(runid, {})
    for cid, case in cases.items():
        if canonical_case_key(cid, case.get('__INFO__', {})) != caseid:
            continue
        for key, info, rows in case_scans(case):
            if key != parameter:
                continue
            for row in rows.values():
                try:
                    requested = row.get('input_requested_parameters', None)
                    summary = row.get('result_summary', {})
                    if not requested or row.get('input_parameter_source', '') != 'input.cgyro.gen':
                        continue
                    pair = (requested.get(parameter, None), requested.get('KY', None))
                    if pair not in pending or summary.get('sample_count', 0) < 2 or summary.get('version', 0) != 1:
                        continue
                    value, ky = pair
                    card = dict(base, **{parameter: float(value), 'KY': float(ky), 'NONLINEAR_FLAG': 0.})
                    if physics.get('scale_time_with_ky', False) and ky > 1:
                        for name in ('DELTA_T', 'MAX_TIME'):
                            card[name] /= ky
                    if ({name: float(number) for name, number in requested.items() if name not in runtime}
                            != {name: number for name, number in card.items() if name not in runtime}):
                        continue
                    status = summary.get('solver_status', '')
                    if status != 'converged' and (status != 'max_time' or
                            not float(summary['final_time']) >= card.get('MAX_TIME', float('inf'))):
                        continue
                    node = case
                    for part in row['result_path']:
                        node = metadata_value(node)[part]
                    if is_native_file(node) or REF not in node:
                        continue
                    owner = metadata_value(node[REF])
                    if owner not in pool or summary.get('result_id', None) != owner:
                        continue
                    validate_reference(node, owner)
                    identity = result_identity(info, row)
                except (KeyError, TypeError, ValueError):
                    continue
                coordinates.append(identity)
                pending.remove(pair)
    return dict(submit_coordinates=[list(pair) for pair in wanted if pair in pending],
                reused_points=len(wanted) - len(pending),
                reused_scope=dict(coordinates=coordinates, unknown=[], issues=[]))
