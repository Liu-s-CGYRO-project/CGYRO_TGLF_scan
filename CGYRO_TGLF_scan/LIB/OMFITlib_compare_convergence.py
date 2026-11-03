"""One-variable convergence views over existing RUN_DB point references.

Only the selected case's lightweight indexes are inspected. Shared baselines
are joined by the complete cached generated input, never by task number, job
ancestry, a Cartesian axis product, or a reader's science arrays.
"""
from builtins import (KeyError, TypeError, ValueError, abs, all, any, dict, float, format, iter, len, list,
                      max, next, set, sorted, str, tuple)
from bisect import bisect_left, bisect_right
from collections import OrderedDict
import hashlib
import json
import math
from OMFITlib_cgyro_archive import RUN_CONTROL_PARAMETERS, case_scans, point_values, result_identity, scan_branch
from OMFITlib_cgyro_convergence import DIRECTIONS, PARAMETER_RTOL, PARAMETER_ATOL, same_parameters, same_value
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


def ordinary_case_view(case):
    """Exclude indexed convergence points from ordinary scan selectors/readers.

    Most branches are either ordinary or convergence scans. Only a legacy
    mixed branch needs a shallow path view of its ordinary rows. Owners and
    immutable row summaries are reused; no reader, file or archive is changed.
    Untagged legacy scans remain ordinary instead of guessing from their names.
    """
    view, records = None, OrderedDict()
    for name, info, rows in case_scans(case):
        ordinary = {key: row for key, row in rows.items() if not _context(info, row)}
        changed = len(ordinary) != len(rows) or (not rows and info.get('convergence_group', {}))
        if changed:
            if view is None:
                view = OrderedDict((key, case[key]) for key in case.keys() if not str(key).startswith('__'))
            branch = scan_branch(case, info, rows)
            view.pop(branch, None)
            if not ordinary:
                continue
            # The latest header may belong to a convergence submission. Restore
            # the ordinary input/axes from its own row, keeping exact file paths.
            info = dict(info, **dict(next(iter(ordinary.values())).get('result_info', {})))
            info.pop('convergence_group', None)
            coordinates = [point_values(info, row) for row in ordinary.values()]
            info['scan_axes'] = [dict(axis, values=sorted({values[axis['name']] for values in coordinates
                                                        if axis['name'] in values}))
                                 for axis in info.get('scan_axes', [])]
            tree = view[branch] = {}
            for row in ordinary.values():
                path = row['result_path'][1:]
                source, target = case[branch], tree
                for key in path[:-1]:
                    source = metadata_value(source)[key]
                    target = target.setdefault(key, {})
                target[path[-1]] = metadata_value(source)[path[-1]]
        records[name] = dict(info=info, tasks=ordinary if changed else rows)
    if view is None:
        return case
    view['__SCANS__'] = records
    if records:
        latest = list(records.values())[-1]
        view['__INFO__'], view['__TASKS__'] = latest['info'], latest['tasks']
    return view


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
        if name not in RUN_CONTROL_PARAMETERS and (name not in values or not same_value(values[name], value)):
            raise ValueError('生成输入摘要与结果坐标不一致：' + name)
        if name == 'KY' and not same_parameters({'KY': values[name]}, {'KY': float(value)}):
            raise ValueError('生成输入摘要与结果坐标不一致：带符号 KY')
    identity = result_identity(info, row)
    return values, (identity['runid'], identity['case_id'])


def _coordinate(identity, values):
    return identity, tuple(sorted(values.items()))


def _coordinate_bucket(key):
    values = dict(key[1])
    ky = values['KY']
    return key[0], tuple(values), (ky > 0, ky < 0)


def _coordinate_index(wanted):
    """Bound tolerant lookups by physical case, field names and signed KY."""
    buckets = {}
    for key in wanted:
        buckets.setdefault(_coordinate_bucket(key), []).append((dict(key[1])['KY'], key))
    return {bucket: ([item[0] for item in rows], [item[1] for item in rows])
            for bucket, entries in buckets.items() for rows in [sorted(entries)]}


def _matching_coordinates(index, key):
    values = dict(key[1])
    ky = values['KY']
    ky_values, keys = index.get(_coordinate_bucket(key), ([], []))
    margin = max(abs(ky) * PARAMETER_RTOL, PARAMETER_ATOL) / (1 - PARAMETER_RTOL)
    for candidate in keys[bisect_left(ky_values, ky - margin):bisect_right(ky_values, ky + margin)]:
        if same_parameters(values, dict(candidate[1])):
            yield candidate


def _family(info, row, values, identity, axis, center):
    fixed = dict(values)
    fixed.pop('KY')
    fixed.pop(axis)
    own = dict(info, **dict(row.get('result_info', {})))
    if own.get('scale_time_with_ky', False) and values['KY'] > 1 and 'DELTA_T' in fixed:
        fixed['DELTA_T'] *= values['KY']
    return identity, axis, center, tuple(sorted(fixed.items()))


def _same_family(first, second):
    return (first[:2] == second[:2] and same_value(first[2], second[2])
            and same_parameters(dict(first[3]), dict(second[3])))


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
                if axis not in values or not any(same_value(values[axis], value) for value in requested):
                    raise ValueError('扫描值不在请求列表：{}={}，请求 {}'.format(axis, values.get(axis, '缺失'), requested))
                mismatched = [name for name, number in fixed.items()
                              if name not in values or not same_value(number, values[name])]
                if mismatched:
                    raise ValueError('固定参数与收敛基准不一致：' + ', '.join(
                        '{}={}，预期 {}'.format(name, values.get(name, '缺失'), fixed[name]) for name in mismatched))
                family = _family(info, row, values, identity, axis, center)
                family = next((old for old in groups if old[0] != 'unverified' and _same_family(old, family)), family)
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
                if not any(same_value(value, previous) for previous in group['values']):
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


def available_convergence_groups(case):
    """Offer only directions/values with resolved references in this case.

    Reuse the plot resolver's metadata rules, so a requested-but-uncollected
    direction is not a checkbox. Diagnostics remain available to explicit
    checks; determining availability never opens a result reader or file.
    """
    groups = convergence_groups(case)
    if not groups:
        return groups
    view, _, _, _ = convergence_case_view(case, groups=groups)
    result = OrderedDict()
    for token, group in groups.items():
        values = [value for value, tree in view[token].items() if tree['lin']]
        # A shared baseline alone cannot make an uncollected/invalid direction
        # look available. At least one retained varied value must resolve.
        if any(not same_value(value, group['baseline_value']) for value in values):
            result[token] = dict(group, values=values)
    return result


def convergence_case_view(case, selected=None, *, groups=None):
    """Return (virtual view, selections, metadata, diagnostics).

    None selects every saved direction, {} none. For every selected direction
    the baseline value is included even if omitted from the requested list.
    Full-input matching never changes the archive or opens payload files. A
    conflicting owner or unavailable baseline leaves a gap and a diagnostic.
    """
    groups = convergence_groups(case) if groups is None else groups
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
            if not any(same_value(value, previous) for previous in values):
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
    # resolution below is restricted to verified requested coordinates.
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
                if (axis in parameters and same_value(parameters[axis], center) and group['_frozen']
                        and _same_family(_family(info, row, parameters, identity, axis, center), group['_family'])):
                    _request(wanted, token, axis, values, parameters, identity)
    coordinate_index = _coordinate_index(wanted)
    for scan, point, row, key in indexed:
        matches = list(_matching_coordinates(coordinate_index, key))
        if not matches:
            continue
        try:
            node = _point_reference(case, row)
            for match in matches:
                previous = candidates.setdefault(match, [])
                if not any(same_result_reference(saved, node) for saved in previous):
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
