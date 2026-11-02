"""Generate ordinary one-axis scans from one common convergence baseline.

Plans contain small parameter dictionaries only. They never own result files,
consult job ancestry, or perform storage maintenance.
"""
from builtins import (BaseException, KeyError, TypeError, ValueError, all, any, bool, dict, enumerate, float, int, isinstance, len, list,
                      max, reversed, round, set, sorted, str, tuple)
from collections import OrderedDict
from copy import deepcopy
import math
import re
from OMFITlib_cgyro_parameters import FIELDS, constant_parameters, managed_parameter, numeric_source, parameter_value
from OMFITlib_cgyro_scan_values import MAX_VALUES, ky_values, value_list
from OMFITlib_cgyro_archive import (RUN_CONTROL_PARAMETERS, catalog_runs, canonical_case_key, case_destination,
                                   case_scans, case_sources, clean_run_id, point_values, result_identity, scan_key, store_scan)
from OMFITlib_cgyro_reference import REF, is_native_file, make_reference, metadata_value, validate_reference
from OMFITlib_cgyro_db import rollback_actions

CONTENTS = OrderedDict([('只扫 ky', 0), ('ky + 1 个参数', 1), ('ky + 2 个参数', 2),
                        ('ky + 3 个参数', 3), ('单变量收敛扫描', 'convergence')])
DIRECTIONS = OrderedDict([('N_ENERGY', '能量分辨率'), ('N_XI', '俯仰角分辨率'),
    ('N_RADIAL', 'ballooning 区间'), ('N_THETA', '沿场分辨率'), ('E_MAX', '能量上限'),
    ('ERROR_TOL', '时间步精度')])
BASELINE = OrderedDict([('N_ENERGY', 32), ('N_XI', 48), ('N_RADIAL', 32),
                        ('N_THETA', 32), ('E_MAX', 8)])
PARAMETER_RTOL, PARAMETER_ATOL = 1e-9, 1e-12


def same_value(first, second):
    """Use the collected-input tolerance, without rounding stored coordinates."""
    first, second = float(first), float(second)
    return (math.isfinite(first) and math.isfinite(second) and
            math.isclose(first, second, rel_tol=PARAMETER_RTOL, abs_tol=PARAMETER_ATOL))


def same_parameters(first, second):
    """Complete numeric identity; even tiny opposite signed KY stay distinct."""
    return (first.keys() == second.keys() and all(same_value(first[name], value) and
        (name != 'KY' or (float(first[name]) > 0, float(first[name]) < 0) ==
                        (float(value) > 0, float(value) < 0)) for name, value in second.items()))


def active(physics):
    return physics.get('scan_mode', 'regular') == 'convergence'


def default_values(name, center):
    """Seed one direction from its center; no inputs/results are opened."""
    center = parameter_value(name, center)
    if name == 'N_ENERGY':
        step = max(1, round(float(center) / 4))
        values = [max(1, center - step), center, center + step]
    elif name == 'N_XI':
        values = [max(2, round(float(center) / 3) * 2), center,
                  max(2, round(float(center) * 2 / 3) * 2)]
    elif name in ('N_RADIAL', 'N_THETA'):
        values = [max(2, round(float(center) * .75 / 2) * 2), center,
                  max(2, round(float(center) * 1.5 / 2) * 2)]
    elif name == 'E_MAX':
        values = [center, float(center) * 1.25, float(center) * 1.5]
    else:
        values = [center, float(center) / 10]
    return list(dict.fromkeys(parameter_value(name, value) for value in values))


def sync_values(physics, name, source=None):
    """Explicit baseline/auto-mode edit; touch only this direction's values."""
    config = physics['convergence']
    baseline = config['baseline']
    fixed = physics.get('fixed_parameters', {}).get(name, {})
    if name in baseline:
        center = baseline[name]
    else:
        center = fixed.get('value', 1e-4) if fixed.get('enabled', False) else (source or {}).get(name, 1e-4)
    center = parameter_value(name, center)
    group = config['groups'][name]
    if group.get('auto_values', True):
        values = default_values(name, center)
        group['values'] = values
    if name in baseline:
        baseline[name] = center
    return group.get('auto_values', True)


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
        group.setdefault('auto_values', True)
        if 'fixed' not in group:
            group['fixed'] = {'N_ENERGY': max(64, int(float(baseline['N_ENERGY'])))} if name == 'E_MAX' else {}
        if 'values' in group:
            continue
        center = baseline.get(name, fixed.get(name, {}).get('value', (source or {}).get(name, 1e-4)))
        group['values'] = default_values(name, center)
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
        # A formatted copy of the center must not create a second physical
        # configuration before jobs() gives its ownership to Base case.
        extra = {key: effective[key] if key in effective and same_value(value, effective[key]) else value
                 for key, value in extra.items()}
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
            if not any(same_value(number, previous) for previous in requested):
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


def archive_runid(value):
    """Keep convergence results separate without stacking generated suffixes."""
    value = str(value)
    return value if value.endswith('_convergence') else value + '_convergence'


def jobs(physics, source, dimensions, batch_key):
    if not active(physics):
        return [dict(physics=physics, dimensions=dimensions, batch_key=batch_key)]
    plans = groups(physics, source)
    baseline = plans[0]['baseline']
    controls = deepcopy(dict(physics))
    controls.pop('convergence', None)
    controls['scan_mode'] = 'regular'
    for name, value in baseline.items():
        controls.setdefault('fixed_parameters', {})[name] = dict(enabled=True, value=value)
    effective = numeric_source(source)
    effective.update({name: parameter_value(name, item['value'])
                      for name, item in controls.get('fixed_parameters', {}).items() if item.get('enabled', False)})
    effective.update(constant_parameters(controls))
    name = plans[0]['parameter']
    center = parameter_value(name, effective.get(name, FIELDS[name][2]))
    controls['1d'] = dict(Para=name, Range=[center])
    base = dict(parameter=name, baseline=deepcopy(baseline), requested=[center], shared=[], fixed={},
                role='baseline', storage_branch='Base case')
    result = [dict(physics=controls, dimensions=1,
                   batch_key=str(batch_key) + ':convergence:Base case', convergence_group=base)]
    for group in plans:
        name = group['parameter']
        center = parameter_value(name, effective.get(name, FIELDS[name][2]))
        # The common baseline is submitted and owned once. An E_MAX group
        # with NE=64 instead uses the NE=64 direction result as its reference.
        if all(same_value(effective.get(key, float('nan')), value)
               for key, value in group['fixed'].items()):
            group['values'] = [value for value in group['values'] if not same_value(value, center)]
            group['physics']['1d']['Range'] = list(group['values'])
            group['shared'] = [item for item in group['shared'] if not same_value(item['value'], center)]
            group['shared'].append(dict(value=center, group='Base case'))
        if group['values']:
            metadata = dict(context(group), role='direction', storage_branch=name)
            result.append(dict(physics=group['physics'], dimensions=1,
                               batch_key=str(batch_key) + ':convergence:' + name,
                               convergence_group=metadata))
    return result


def _cached_parameters_match(info, row, requested):
    """Use the collection-time tolerance without opening generated input again."""
    cached = row.get('input_parameters', None)
    if not cached:
        return False
    cached = {name: float(value) for name, value in cached.items()}
    if not all(math.isfinite(value) for value in cached.values()):
        return False
    coordinate = dict(point_values(info, row))
    coordinate.update(row.get('effective_time', {}))
    for expected in (requested, coordinate):
        if not all(name in cached and same_value(value, cached[name])
                   for name, value in expected.items() if name not in RUN_CONTROL_PARAMETERS):
            return False
    return True


def reusable_points(module, runid, caseid, source, physics, parameter, enabled=True, capture=False):
    """Explicit preview/submission: inspect this run/radius's lightweight index.

    Reuse requires the verified explicit input cached at collection, a retained
    owner and sufficient completed data. Missing old metadata schedules a new
    point; querying an index never backfills it by opening input/result files.
    """
    wanted = [(value, ky) for value in physics['1d']['Range'] for ky in ky_values(physics)]
    pending, coordinates, matches, candidates = set(wanted), [], [], {}
    if not enabled or float(source.get('PROFILE_MODEL', 1)) == 2:
        result = dict(submit_coordinates=[list(pair) for pair in wanted], reused_points=0,
                      reused_scope=dict(coordinates=[], unknown=[], issues=[]))
        if capture:
            result['_matches'] = []
        return result
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
            for row in rows.values():
                try:
                    requested = row.get('input_requested_parameters', None)
                    summary = row.get('result_summary', {})
                    if not requested or row.get('input_parameter_source', '') != 'input.cgyro.gen':
                        continue
                    pair = (requested.get(parameter, None), requested.get('KY', None))
                    if pair not in pending or summary.get('sample_count', 0) < 2 or summary.get('version', 0) != 1:
                        continue
                    if not _cached_parameters_match(info, row, requested):
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
                    if identity['runid'] != clean_run_id(runid) or identity['case_id'] != canonical_case_key(caseid):
                        continue
                    if not all(math.isclose(identity['values'][name], float(number), rel_tol=1e-9, abs_tol=1e-12)
                               for name, number in ((parameter, value), ('KY', ky))):
                        continue
                except (KeyError, TypeError, ValueError):
                    continue
                match = dict(info=info, row=row, owner=owner, value=value, ky=ky)
                if pair not in candidates:
                    candidates[pair] = (identity, match)
                elif candidates[pair] is not None and candidates[pair][1]['owner'] != owner:
                    candidates[pair] = None  # Conflicting current owners cannot prove safe reuse.
    for pair, candidate in candidates.items():
        if candidate is not None:
            identity, match = candidate
            coordinates.append(identity)
            if capture:
                matches.append(match)
            pending.remove(pair)
    result = dict(submit_coordinates=[list(pair) for pair in wanted if pair in pending],
                  reused_points=len(wanted) - len(pending),
                  reused_scope=dict(coordinates=coordinates, unknown=[], issues=[]))
    if capture:
        result['_matches'] = matches  # Transient metadata only; never persisted in a manifest.
    return result


def _at(node, path):
    for key in path:
        node = metadata_value(node)[key]
    return metadata_value(node)


def _adoption_destination(module, request, info):
    path = tuple(case_destination(module, request['runid'], request['case_id'], info))
    try:
        return path, _at(module['RUN_DB'], path)
    except KeyError:
        # Old projects may still use a short nr key. Use its verified physical
        # location rather than creating a second case or migrating other scans.
        sources = case_sources(module, request['runid'], request['case_id'])[request['runid']]
        matching = [parts for cid, case, parts in sources
                    if canonical_case_key(cid, case.get('__INFO__', {})) == request['case_id']]
        if len(matching) != 1:
            raise ValueError('Cannot locate one existing case for convergence result reuse') from None
        path = (request['runid'],) + tuple(matching[0])
        return path, _at(module['RUN_DB'], path)


def _adopted_scan(request, matches):
    """Rebind the selected plan's context while retaining each physical owner."""
    group = request['group']
    parameter, branch = group['parameter'], group['storage_branch']
    info = deepcopy(dict(matches[0]['info']))
    axes = deepcopy(request['scan_axes'])
    axes[0]['values'] = list(group['requested'])
    info.update(dict(convergence_group=deepcopy(group), scan_axes=axes, dimensions=1,
                     scan_dimensions=1, parameters=[branch], scan_key=branch,
                     fixed_parameters={name: item['value'] for name, item in
                         request['physics'].get('fixed_parameters', {}).items() if item.get('enabled', False)}))
    # The source job's planned task IDs/scope do not describe this new view.
    # Current job identities remain on the retained point rows and in history.
    info.pop('planned_points', None)
    info.pop('planned_coordinates', None)
    complete = len(matches) == len(group['requested']) * len(ky_values(request['physics']))
    info.update(dict(scan_complete=complete, collection_status='complete' if complete else 'partial'))
    data, tasks = {}, {}
    for index, match in enumerate(matches, 1):
        point = 'p{:06d}'.format(index)
        value, ky = match['value'], match['ky']
        row = deepcopy(dict(match['row']))
        row.update(dict(values={parameter: value, 'KY': ky},
                        result_path=[branch, str(value), 'lin', str(ky)]))
        row.pop('coordinate_path', None)
        own = row.setdefault('result_info', deepcopy(dict(match['info'])))
        for name in ('convergence_group', 'scan_axes', 'dimensions', 'scan_dimensions', 'fixed_parameters'):
            own[name] = deepcopy(info[name])
        data.setdefault(branch, {}).setdefault(str(value), {}).setdefault('lin', {})[str(ky)] = make_reference(match['owner'])
        tasks[point] = row
    return data, info, tasks


def adopt_reused_points(module, requests, factory=dict):
    """Explicit preparation adopts verified references into the selected plan.

    Build touched scan indexes off-tree, then commit only their branches and
    headers with rollback. Preview never calls this. Physical owners, other
    scans, and job history remain untouched; no file read or rehash is needed.
    """
    if not requests:
        return 0
    updates = {}
    for request in requests:
        controls = dict(request['physics'])
        group = request['group']
        # Include the shared baseline: an existing direction row at that
        # coordinate must also describe the newly selected center.
        controls['1d'] = dict(Para=group['parameter'], Range=list(group['requested']))
        matches = reusable_points(module, request['runid'], request['case_id'], request['source'],
                                  controls, group['parameter'], capture=True)['_matches']
        if not matches:
            continue
        data, info, tasks = _adopted_scan(request, matches)
        path, original = _adoption_destination(module, request, info)
        if path not in updates:
            case = dict(original.items())
            case['__SCANS__'] = {key: dict(info=saved, tasks=rows) for key, saved, rows in case_scans(original)}
            updates[path] = (original, case, set())
        original, case, branches = updates[path]
        store_scan(case, data, info, tasks, factory)
        branches.add(scan_key(info))
    rollback = []
    try:
        for original, case, branches in updates.values():
            for key in list(branches) + ['__SCANS__', '__INFO__', '__TASKS__']:
                if key in original:
                    old = original[key]
                    rollback.append((key, lambda node=original, key=key, old=old: node.__setitem__(key, old)))
                else:
                    rollback.append((key, lambda node=original, key=key: node.pop(key, None)))
                original[key] = case[key]
    except BaseException as error:
        rollback_actions(error, list(reversed(rollback)))
        raise
    return len(updates)
