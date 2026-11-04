"""Read-only comparison spectra for indexed CGYRO archives.

The saved task table owns coordinates and physical paths. Virtual 1D slices
contain references to those results, never copies, averages or archive edits.
One varying axis and fixed remaining coordinates keep every ky grid separate.
"""
from builtins import (KeyError, TypeError, ValueError, all, any, dict, float, hasattr,
                      len, list, set, sorted, str, tuple)
from collections import OrderedDict
import json
import math
from OMFITlib_cgyro_archive import case_scans, coordinate_path, point_values, scan_branch
from OMFITlib_compare_options import parse_float_list_text


def _key(mapping, wanted):
    if not hasattr(mapping, 'keys'):
        return None
    if wanted in mapping:
        return wanted
    textual = [key for key in mapping.keys() if str(key) == str(wanted)]
    if len(textual) == 1:
        return textual[0]
    try:
        number = float(wanted)
    except (TypeError, ValueError):
        return None
    numeric = []
    for key in mapping.keys():
        try:
            if math.isfinite(number) and float(key) == number:
                numeric.append(key)
        except (TypeError, ValueError):
            continue
    if len(numeric) > 1:
        raise ValueError('Ambiguous archived coordinate: ' + str(wanted))
    return numeric[0] if numeric else None


def multiaxis_scans(case, selected=None):
    """Describe selected indexed scans using cached input summaries only."""
    scans = OrderedDict()
    wanted = None if selected is None else {str(name) for name in selected}
    for key, info, tasks in case_scans(case):
        if wanted is not None and key not in wanted:
            continue
        axes = [dict(axis) for axis in info.get('scan_axes', []) if not axis.get('fixed', False)]
        if key == 'KY_ONLY' or axes:
            scans[key] = _indexed_scan(case, info, tasks, [] if key == 'KY_ONLY' else axes, key == 'KY_ONLY')
    return scans


def _cached_configurations(info, tasks):
    """Undo documented ky scaling for grouping, leaving stored inputs intact."""
    points, choices, errors = {}, OrderedDict(), []
    for point, row in tasks.items():
        try:
            values = dict(point_values(info, row, include_input=True))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append('{}: {}'.format(point, exc))
            continue
        context = dict(info, **dict(row.get('result_info', {})))
        ky = values.pop('KY')
        values.pop('KY_ONLY', None)  # Old archives can use this placeholder axis.
        if 'DELTA_T' in values:
            values['scale_time_with_ky'] = float(context.get('scale_time_with_ky', False))
        if context.get('scale_time_with_ky', False) and ky > 1 and 'DELTA_T' in values:
            # values without an effective input/time summary already hold the
            # unscaled requested step; do not multiply those legacy rows twice.
            if 'DELTA_T' in row.get('input_parameters', {}) or 'DELTA_T' in row.get('effective_time', {}):
                values['DELTA_T'] *= ky
                requested = row.get('values', {}).get('DELTA_T', None)
                if requested is not None and math.isclose(float(requested), values['DELTA_T'], rel_tol=1e-14, abs_tol=0.):
                    values['DELTA_T'] = float(requested)
        for name, value in values.items():
            known = choices.setdefault(name, [])
            # Only undo roundoff introduced by dt / ky * ky. In particular,
            # nearby saved physics coordinates must not be merged by isclose.
            if name == 'DELTA_T' and context.get('scale_time_with_ky', False):
                matches = [saved for saved in known if math.isclose(saved, value, rel_tol=1e-14, abs_tol=0.)]
                if matches:
                    value = values[name] = matches[0]
            if value not in known:
                known.append(value)
        points[point] = values
    return points, choices, errors


def _linked_to_axes(points, name, axes):
    """A declared linkage is not a choice unless retained inputs disagree."""
    seen = {}
    for values in points.values():
        if name not in values or any(axis not in values for axis in axes):
            return False
        coordinate = tuple(values[axis] for axis in axes)
        if coordinate in seen and seen[coordinate] != values[name]:
            return False
        seen[coordinate] = values[name]
    return True


def _indexed_scan(case, info, tasks, axes, ky_only):
    points, choices, errors = _cached_configurations(info, tasks)
    declared = [axis['name'] for axis in axes]
    linked = {link['name'] for axis in axes for link in axis.get('linked', [])}
    for name in sorted(set(choices) - set(declared)):
        if name in linked and _linked_to_axes(points, name, declared):
            continue
        if len(choices[name]) > 1 or any(name not in values for values in points.values()):
            axes.append(dict(name=name, values=sorted(choices[name])))
    return dict(ky_only=ky_only, axes=axes, tasks=tasks, info=info, point_values=points,
                declared_axes=declared, diagnostics=errors,
                path_dimensions=len(info.get('scan_axes', [])), branch=scan_branch(case, info, tasks))


def axis_values(scan):
    """Include the planned grid so an entirely missing row stays a gap."""
    values = OrderedDict()
    for axis in scan['axes']:
        name = str(axis['name'])
        raw = list(axis.get('values', []))
        if not scan.get('ky_only', False):
            raw.extend(row.get(name, None) for row in scan['point_values'].values())
        numbers = set()
        for value in raw:
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                numbers.add(value)
        values[name] = sorted(numbers)
    return values


def view_config(state, nr):
    if state.get('force_read_all_nr_items', False):
        return state.get('cgyro_multi_by_nr', {}).get(str(nr), {})
    return state.get('cgyro_multi', {})


def linear_node(case, para, value):
    """Resolve a legacy spectrum or a virtual slice with the same interface."""
    node = case
    for wanted in (para, value, 'lin'):
        key = _key(node, wanted)
        if key is None:
            return None
        node = node[key]
    return node if hasattr(node, 'keys') else None


def slice_coordinates(metadata, value):
    coordinates = metadata.get('coordinates', {})
    key = _key(coordinates, value)
    return {} if key is None else coordinates[key]


def coordinate_label(metadata, value, parameter=''):
    coordinates = slice_coordinates(metadata, value)
    if metadata.get('ky_only', False):
        details = ', '.join('{}={:.7g}'.format(name, coordinates[name])
                            for name in metadata['coordinate_names'] if name in coordinates)
        return 'KY_ONLY' + (' · ' + details if details else '')
    if coordinates:
        return ', '.join('{}={:.7g}'.format(name, coordinates[name])
                         for name in metadata['coordinate_names'] if name in coordinates)
    return '{}={}'.format(parameter, value)


def slice_caption(metadata, parameter):
    fixed = ', '.join('{}={:.7g}'.format(name, value) for name, value in metadata.get('fixed', {}).items())
    return metadata.get('axis', parameter) + (' [' + fixed + ']' if fixed else '')


def comparison_case_view(case, selected, config=None):
    """Adapt indexed scans into exact-coordinate, non-averaged slices.

    Unindexed legacy nodes retain their original keys and objects.
    Empty axis selections mean empty,
    and absent physical results are diagnostics rather than fabricated data.
    """
    config = {} if config is None else config
    scans = multiaxis_scans(case, selected=selected)
    view = {key: case[key] for key in case.keys() if not str(key).startswith('__')}
    selections, metadata, diagnostics = OrderedDict(), {}, []
    for parameter, chosen in selected.items():
        scan_key = str(parameter)
        if scan_key not in scans:
            selections[parameter] = chosen
            continue
        scan = scans[scan_key]
        diagnostics.extend('{} / {}'.format(scan_key, error) for error in scan['diagnostics'])
        ky_only = scan.get('ky_only', False)
        available = axis_values(scan)
        cfg = config.get(scan_key, {})
        if ky_only and not cfg.get('ky_only', False):
            cfg = {}  # Discard the former dummy-value/derived-DELTA_T filters.
        # A common filter may vary in another selected case but be constant
        # here. Its visible scope is recorded by the selector, so obsolete
        # hidden filters from an older catalog cannot reappear.
        shared = cfg.get('active_axes', list(available)) if not ky_only else cfg.get('active_axes', list(cfg.get('values', {})))
        for name in shared:
            numbers = {values[name] for values in scan['point_values'].values() if name in values}
            if numbers and name not in available:
                available[name] = sorted(numbers)
        if ky_only and not available:
            # Runtime adapter only: all ky points form one curve. No numeric
            # KY_ONLY value is displayed, requested or read from GUI settings.
            available['KY_ONLY'] = [0.]
        names = list(available)
        axis = names[0] if ky_only else str(cfg.get('axis', names[0]))
        if axis not in names:
            raise ValueError('Choose a varying axis from {} for {}'.format(', '.join(names), scan_key))
        filters = {}
        for name in names:
            default = chosen if name == names[0] and not ky_only else available[name]
            try:
                filters[name] = parse_float_list_text(cfg.get('values', {}).get(name, default))
            except ValueError as exc:
                raise ValueError('{} / {}: {}'.format(scan_key, name, exc)) from exc
        if not all(filters.values()):
            continue
        coordinate_names = [str(item['name']) for item in scan['axes']]
        coordinate_names.extend(name for name in names if name not in coordinate_names)
        coordinate_names.extend(str(link['name']) for item in scan['axes'] for link in item.get('linked', [])
                                if str(link['name']) not in coordinate_names)
        if ky_only:
            coordinate_names = [name for name in names if name != 'KY_ONLY']
        view.pop(scan['branch'], None)
        count = 0
        for point, row in scan['tasks'].items():
            if point not in scan['point_values']:
                continue  # Already reported by the metadata-only check above.
            try:
                values = dict(scan['point_values'][point], KY_ONLY=0.) if ky_only else scan['point_values'][point]
                coordinates = {name: float(values[name]) for name in coordinate_names}
                if ky_only and axis == 'KY_ONLY':
                    coordinates['KY_ONLY'] = 0.
                if not all(math.isfinite(value) for value in coordinates.values()):
                    raise ValueError('Non-finite archived coordinates')
                if not all(coordinates[name] in filters[name] for name in names):
                    continue
                path = list(row['result_path'])
                coordinate = coordinate_path(row)
                if (not ky_only and len(coordinate) != 2 * scan['path_dimensions'] + 2) or coordinate[-2] != 'lin':
                    raise ValueError('Invalid archived multi-axis result path')
                path[0] = scan['branch']
                node = case
                for wanted in path:
                    key = _key(node, wanted)
                    if key is None:
                        raise KeyError(wanted)
                    node = node[key]
            except (KeyError, TypeError, ValueError) as exc:
                diagnostics.append('{} / {}: {}'.format(scan_key, point, exc))
                continue
            fixed = OrderedDict((name, coordinates[name]) for name in names if name != axis)
            token = '@scan:' + json.dumps([scan_key, axis, list(fixed.items())], separators=(',', ':'))
            if token not in metadata:
                if token in view:
                    raise ValueError('Virtual scan identity collides with an archived branch')
                metadata[token] = dict(scan_key=scan_key, axis=axis, fixed=fixed,
                                       coordinate_names=coordinate_names, coordinates={}, values=list(filters[axis]))
                if ky_only:
                    metadata[token]['ky_only'] = True
                view[token] = {}
                selections[token] = list(filters[axis])
            value = coordinates[axis]
            linear = view[token].setdefault(value, {}).setdefault('lin', {})
            ky = coordinate[-1]
            if _key(linear, ky) is not None:
                raise ValueError('Duplicate ky at one complete parameter coordinate: ' + str(path))
            linear[ky] = node
            previous = metadata[token]['coordinates'].get(value, None)
            if previous is not None and previous != coordinates:
                raise ValueError('Linked coordinates disagree within one saved spectrum')
            metadata[token]['coordinates'][value] = coordinates
            count += 1
        if not count:
            diagnostics.append(scan_key + ': no saved points match all selected axis values')
    return view, selections, metadata, diagnostics
