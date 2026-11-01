"""One-variable convergence views over existing RUN_DB point references.

Only the selected case's lightweight indexes are inspected. Shared baselines
are joined by the complete cached generated input, never by task number, job
ancestry, a Cartesian axis product, or a reader's science arrays.
"""
from builtins import (KeyError, TypeError, ValueError, all, dict, float, format, len, list,
                      set, sorted, str, tuple)
from collections import OrderedDict
import hashlib
import json
import math
from OMFITlib_cgyro_archive import RUN_CONTROL_PARAMETERS, case_scans, point_values, result_identity
from OMFITlib_cgyro_convergence import DIRECTIONS
from OMFITlib_cgyro_reference import metadata_value, same_result_reference
from OMFITlib_compare_options import parse_float_list_text


def _context(info, row):
    own = row.get('result_info', {})
    if 'convergence_group' in own:
        return own['convergence_group'] or {}
    # Old merged rows lack their own convergence context. A newer submission's
    # header cannot turn unrelated retained rows into that convergence test.
    token = row.get('run_token', own.get('run_token', ''))
    if token and info.get('run_token', '') and token != info['run_token']:
        return {}
    return info.get('convergence_group', {})


def _parameters(info, row):
    """A generated-input summary is the proof required for baseline sharing."""
    source = row.get('input_parameters', None)
    if source is None or row.get('input_parameter_source', '') != 'input.cgyro.gen':
        raise ValueError('缺少已收集的 input.cgyro.gen 参数摘要，不能确定基准匹配')
    values = {str(name): float(value) for name, value in source.items() if name not in RUN_CONTROL_PARAMETERS}
    if 'KY' not in values or not all(math.isfinite(value) for value in values.values()):
        raise ValueError('生成输入摘要缺少有限的带符号 KY 或包含无效数值')
    expected = point_values(info, row)
    # The point's collected time settings contain the actual ky-scaled step;
    # the scan header retains the user's unscaled reference value.
    expected.update(row.get('effective_time', {}))
    for name, value in expected.items():
        if name not in RUN_CONTROL_PARAMETERS and (name not in values or not math.isclose(
                values[name], float(value), rel_tol=1e-9, abs_tol=1e-12)):
            raise ValueError('生成输入摘要与结果坐标不一致：' + name)
    identity = result_identity(info, row)
    return values, (identity['runid'], identity['case_id'])


def _coordinate(identity, values):
    return identity, tuple(sorted(values.items()))


def _family(info, row, values, identity, axis, center):
    fixed = dict(values)
    fixed.pop('KY')
    fixed.pop(axis)
    own = dict(info, **dict(row.get('result_info', {})))
    if own.get('scale_time_with_ky', False) and values['KY'] > 1 and 'DELTA_T' in fixed:
        fixed['DELTA_T'] *= values['KY']
    return identity, axis, center, tuple(sorted(fixed.items()))


def convergence_groups(case):
    """Return metadata-only direction groups; different frozen physics split.

    Mapping keys identify the frozen physical family and remain stable when
    other families arrive. ``values`` includes the required baseline;
    internal row references are metadata, not payload readers or file copies.
    Untagged scans and dedicated ``role=baseline`` branches are not directions.
    """
    groups = OrderedDict()
    for scan, info, tasks in case_scans(case):
        for point, row in tasks.items():
            context = _context(info, row)
            axis = context.get('parameter', '')
            if axis not in DIRECTIONS or context.get('role', '') == 'baseline':
                continue
            requested = parse_float_list_text(context.get('requested', []))
            if not requested:
                continue
            baseline = dict(context.get('baseline', {}))
            center = float(baseline.get(axis, requested[0]))
            fixed = dict(baseline, **dict(context.get('fixed', {})))
            fixed.pop(axis, None)
            problem = ''
            try:
                values, identity = _parameters(info, row)
                if axis not in values or values[axis] not in requested:
                    continue
                if not all(name in values and float(number) == values[name] for name, number in fixed.items()):
                    continue
                family = _family(info, row, values, identity, axis, center)
            except (KeyError, TypeError, ValueError) as error:
                # An identified direction stays visible with a point-specific
                # diagnostic, but cannot silently borrow an unproven baseline.
                values, identity = None, None
                problem = '{} / {}: {}'.format(scan, point, error)
                family = ('unverified', scan, axis, center, tuple(sorted(fixed.items())))
            if family not in groups:
                groups[family] = dict(convergence=True, axis=axis, label=DIRECTIONS[axis],
                    baseline_value=center, fixed=fixed, values=[center], scan_key=scan,
                    coordinate_names=[axis], coordinates={}, _rows=[], diagnostics=[],
                    _family=family, _frozen=dict(family[-1]) if values is not None else {},
                    _extra_fixed=dict(context.get('fixed', {})))
            group = groups[family]
            for value in requested:
                if value not in group['values']:
                    group['values'].append(value)
            if problem:
                group['diagnostics'].append(problem)
            else:
                group['_rows'].append((info, row, values, identity))
    counts = {}
    for group in groups.values():
        axis = group['axis']
        counts[axis] = counts.get(axis, 0) + 1
    result = OrderedDict()
    for family, group in groups.items():
        axis = group['axis']
        digest = hashlib.sha256(json.dumps(family, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        token = '@convergence:' + axis + ':' + digest
        details = dict(group['_extra_fixed'])
        if counts[axis] > 1:
            peers = [item['_frozen'] for item in groups.values() if item['axis'] == axis and item['_frozen']]
            names = {name for fixed in peers for name in fixed}
            varying = [name for name in sorted(names) if len({fixed.get(name, None) for fixed in peers}) > 1]
            details.update({name: group['_frozen'][name] for name in varying if name in group['_frozen']})
            group['fixed'].update(details)
        if details:
            group['label'] += '（' + ', '.join(name + '=' + format(float(value), '.8g')
                                              for name, value in sorted(details.items())) + '）'
        if not group['_frozen']:
            group['label'] += '（参数摘要不可用）'
        group['token'] = token
        result[token] = group
    return result


def _point_reference(case, row):
    node = case
    for part in row['result_path']:
        node = metadata_value(node)[part]
    return node


def _request(wanted, token, axis, values, parameters, identity):
    for value in values:
        expected = dict(parameters, **{axis: value})
        address = (token, value, expected['KY'])
        wanted.setdefault(_coordinate(identity, expected), set()).add(address)


def convergence_case_view(case, selected=None):
    """Return (virtual view, selections, metadata, diagnostics).

    None selects every saved direction, {} none. For every selected direction
    the baseline value is included even if omitted from the requested list.
    Full-input matching never changes the archive or opens payload files. A
    conflicting owner or unavailable baseline leaves a gap and a diagnostic.
    """
    groups = convergence_groups(case)
    selected = {token: group['values'] for token, group in groups.items()} if selected is None else selected
    view, selections, metadata, diagnostics = {}, OrderedDict(), {}, []
    wanted = {}
    for token, chosen in selected.items():
        if token not in groups:
            diagnostics.append(str(token) + ': 所选收敛方向已不可用')
            continue
        group = groups[token]
        values = [group['baseline_value']]
        for value in parse_float_list_text(chosen):
            if value not in values:
                values.append(value)
        selections[token] = values
        metadata[token] = {key: value for key, value in group.items() if not key.startswith('_')}
        metadata[token]['values'] = values
        metadata[token]['coordinates'] = {value: {group['axis']: value} for value in values}
        diagnostics.extend(group['diagnostics'])
        view[token] = {value: {'lin': {}} for value in values}
        for _, _, parameters, identity in group['_rows']:
            _request(wanted, token, group['axis'], values, parameters, identity)
    if not wanted:
        return view, selections, metadata, diagnostics
    candidates, indexed = {}, []
    # Only this selected physical case's lightweight rows are searched. Reader
    # resolution below is restricted to exact requested coordinates.
    for scan, info, rows in case_scans(case):
        for point, row in rows.items():
            try:
                parameters, identity = _parameters(info, row)
                key = _coordinate(identity, parameters)
            except (KeyError, TypeError, ValueError):
                continue
            indexed.append((scan, point, row, key))
            # During partial collection a direction may have no variant at a
            # saved baseline's ky yet. Extend coverage from proven baselines,
            # preserving missing variant gaps instead of hiding that ky.
            for token, values in selections.items():
                group = groups[token]
                axis, center = group['axis'], group['baseline_value']
                if parameters.get(axis, None) == center and _family(
                        info, row, parameters, identity, axis, center) == group['_family']:
                    _request(wanted, token, axis, values, parameters, identity)
    for scan, point, row, key in indexed:
        if key not in wanted:
            continue
        try:
            node = _point_reference(case, row)
            previous = candidates.get(key, None)
            if previous is None:
                candidates[key] = [node]
            elif not same_result_reference(previous[0], node):
                previous.append(node)
        except (KeyError, TypeError, ValueError) as error:
            # Unselected records never abort selected valid curves.
            diagnostics.append('{} / {}: {}'.format(scan, point, error))
    for key, addresses in wanted.items():
        matches = candidates.get(key, [])
        for token, value, ky in addresses:
            if len(matches) == 1:
                view[token][value]['lin'][ky] = matches[0]
            else:
                reason = '同一完整参数坐标存在不同结果引用，未自动替换' if matches else '未找到完整参数一致的结果'
                role = '基准' if value == metadata[token]['baseline_value'] else '扫描'
                diagnostics.append('{} / {} {}={} / KY={}: {}'.format(
                    metadata[token]['label'], role, metadata[token]['axis'], value, ky, reason))
    return view, selections, metadata, diagnostics
