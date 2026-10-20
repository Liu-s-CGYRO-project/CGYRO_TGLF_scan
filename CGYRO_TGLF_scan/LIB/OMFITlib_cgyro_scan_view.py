"""Read-only comparison slices for indexed multi-axis CGYRO archives.

The saved task table owns coordinates and physical paths. Virtual 1D slices
contain references to those results, never copies, averages or archive edits.
One varying axis and fixed remaining coordinates keep every ky grid separate.
"""
from builtins import (KeyError, TypeError, ValueError, all, dict, float, hasattr,
                      len, list, set, sorted, str, tuple)
from collections import OrderedDict
import json
import math
from OMFITlib_cgyro_archive import case_scans, scan_branch
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


def multiaxis_scans(case):
    """Inspect metadata only; linked parameters are not independent axes."""
    scans = OrderedDict()
    for key, info, tasks in case_scans(case):
        axes = [axis for axis in info.get('scan_axes', []) if not axis.get('fixed', False)]
        if len(axes) > 1:
            scans[key] = dict(axes=axes, tasks=tasks, branch=scan_branch(case, info, tasks))
    return scans


def axis_values(scan):
    """Include the planned grid so an entirely missing row stays a gap."""
    values = OrderedDict()
    for axis in scan['axes']:
        name = str(axis['name'])
        raw = list(axis.get('values', []))
        raw.extend(row.get('values', {}).get(name, None) for row in scan['tasks'].values())
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
    if coordinates:
        return ', '.join('{}={:.7g}'.format(name, coordinates[name])
                         for name in metadata['coordinate_names'] if name in coordinates)
    return '{}={}'.format(parameter, value)


def slice_caption(metadata, parameter):
    fixed = ', '.join('{}={:.7g}'.format(name, value) for name, value in metadata.get('fixed', {}).items())
    return metadata.get('axis', parameter) + (' [' + fixed + ']' if fixed else '')


def comparison_case_view(case, selected, config=None):
    """Expand selected 2D/3D scans into exact-coordinate, non-averaged slices.

    Only indexed multi-axis branches are adapted. Legacy / ordinary 1D nodes
    retain their original keys and objects. Empty axis selections mean empty,
    and absent physical results are diagnostics rather than fabricated data.
    """
    config = {} if config is None else config
    scans = multiaxis_scans(case)
    view = {key: case[key] for key in case.keys() if not str(key).startswith('__')}
    selections, metadata, diagnostics = OrderedDict(), {}, []
    for parameter, chosen in selected.items():
        scan_key = str(parameter)
        if scan_key not in scans:
            selections[parameter] = chosen
            continue
        scan = scans[scan_key]
        available = axis_values(scan)
        names = list(available)
        cfg = config.get(scan_key, {})
        axis = str(cfg.get('axis', names[0]))
        if axis not in names:
            raise ValueError('Choose a varying axis from {} for {}'.format(', '.join(names), scan_key))
        filters = {}
        for name in names:
            default = chosen if name == names[0] else available[name]
            try:
                filters[name] = parse_float_list_text(cfg.get('values', {}).get(name, default))
            except ValueError as exc:
                raise ValueError('{} / {}: {}'.format(scan_key, name, exc)) from exc
        if not all(filters.values()):
            continue
        coordinate_names = [str(item['name']) for item in scan['axes']]
        coordinate_names.extend(str(link['name']) for item in scan['axes'] for link in item.get('linked', []))
        view.pop(scan['branch'], None)
        count = 0
        for point, row in scan['tasks'].items():
            values = row.get('values', {})
            try:
                coordinates = {name: float(values[name]) for name in coordinate_names}
                if not all(math.isfinite(value) for value in coordinates.values()):
                    raise ValueError('Non-finite archived coordinates')
                if not all(coordinates[name] in filters[name] for name in names):
                    continue
                path = list(row['result_path'])
                if len(path) != 2 * len(names) + 2 or path[-2] != 'lin':
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
                view[token] = {}
                selections[token] = list(filters[axis])
            value = coordinates[axis]
            linear = view[token].setdefault(value, {}).setdefault('lin', {})
            if path[-1] in linear:
                raise ValueError('Duplicate ky at one complete parameter coordinate: ' + str(path))
            linear[path[-1]] = node
            previous = metadata[token]['coordinates'].get(value, None)
            if previous is not None and previous != coordinates:
                raise ValueError('Linked coordinates disagree within one saved spectrum')
            metadata[token]['coordinates'][value] = coordinates
            count += 1
        if not count:
            diagnostics.append(scan_key + ': no saved points match all selected axis values')
    return view, selections, metadata, diagnostics
