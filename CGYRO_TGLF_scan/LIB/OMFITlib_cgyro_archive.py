"""Stable case identities and independent parameter scans within each case."""
from builtins import (OSError, TypeError, ValueError, all, any, bool, dict, enumerate, float, getattr,
                      hasattr, int, isinstance, len, list, max, open, range, reversed, set, sorted, str, tuple, type, zip)
from collections import OrderedDict
from copy import deepcopy
import math
import os
import re
from OMFITlib_cgyro_db import legacy_branch, metadata_value
from OMFITlib_cgyro_reference import copy_result_tree
from OMFITlib_cgyro_run_state import point_complete


def clean_run_id(value):
    """Strip only generated legacy suffixes; job state is never a directory."""
    return re.sub(r'(?: \[(?:partial [0-9a-f]+|recovered [^\]]+|legacy revision [0-9]+)\])+$', '', str(value)).strip()


def grouped_case_path(value, info=None):
    """Ordinary original-species scans live directly under their radius.

    BASE is a storage child only for a fixed-input, ky-only reference run.
    Logical case IDs retain ion=BASE so old job identities remain usable.
    """
    info = {} if info is None else info
    parts = case_parts(canonical_case_key(value, info))
    if parts is None:
        nr = info.get('source_nr', info.get('nr', ''))
        ion = str(info.get('ion_case', info.get('mass', '')))
        rho = info.get('rho', 'unknown')
        if not str(nr) or not ion:
            raise ValueError('Missing archived radius/isotope identity')
        try:
            rho = '{:.8g}'.format(float(rho)) if math.isfinite(float(rho)) else 'unknown'
        except (TypeError, ValueError):
            rho = 'unknown'
        parts = str(nr), str(rho), ion
    nr, rho, ion = parts
    if any('/' in str(part) or str(part).startswith('__') for part in parts):
        raise ValueError('Unsafe archived radius/isotope identity')
    path = ['nr={}_rho={}'.format(nr, rho)]
    fallback = (list(info.get('parameters', [])) or [''])[0]
    if ion != 'BASE' or scan_key(info, fallback) == 'KY_ONLY':
        path.append(ion)
    return path


def case_sources(module):
    """Enumerate physical case nodes, keeping old BASE and direct scans apart.

    Recovery validates every source independently before moving any branch.
    Views here contain references to existing indexes, never result copies.
    """
    runs = OrderedDict()
    for rid, source in module.get('RUN_DB', {}).items():
        if str(rid).startswith('__'):
            continue
        entries = runs.setdefault(rid, [])
        source = metadata_value(source)
        if any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(source).__mro__) or not hasattr(source, 'items'):
            continue
        for key, node in source.items():
            if str(key).startswith('__'):
                continue
            node = metadata_value(node)
            radial = re.fullmatch(r'nr=(.+)_rho=([^_/]+)', str(key))
            mapping = (not any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad')
                               for base in type(node).__mro__) and hasattr(node, 'items'))
            if radial is None or not mapping:
                entries.append((key, node, [key]))
                continue
            records = case_scans(node)
            owned = {scan_branch(node, info, tasks) for _, info, tasks in records}
            if records:
                direct = OrderedDict((name, child) for name, child in node.items()
                                     if name in owned or name in ('__INFO__', '__SCANS__', '__TASKS__'))
                cid = 'nr={}__rho={}__ion=BASE'.format(*radial.groups())
                entries.append((cid, direct, [key]))
            for ion, case in node.items():
                if not str(ion).startswith('__') and ion not in owned:
                    cid = 'nr={}__rho={}__ion={}'.format(*radial.groups(), ion)
                    entries.append((cid, case, [key, ion]))
    return runs


def _case_union(first, second):
    """Combine disjoint scan indexes for a temporary logical case view."""
    for source in (first, second):
        if (any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(source).__mro__)
                or not hasattr(source, 'items')):
            raise ValueError('Ambiguous original case requires archive consolidation')
    view = OrderedDict(first.items())
    for key, child in second.items():
        if not str(key).startswith('__'):
            if key in view:
                raise ValueError('Overlapping original scans require archive consolidation: ' + str(key))
            view[key] = child
    records = OrderedDict()
    for source in (first, second):
        for key, info, tasks in case_scans(source):
            if key in records:
                raise ValueError('Overlapping original scan indexes require archive consolidation: ' + str(key))
            records[key] = dict(info=info, tasks=tasks)
    if records:
        view['__SCANS__'] = records
        last = list(records.values())[-1]
        view['__INFO__'], view['__TASKS__'] = last['info'], last['tasks']
    return view


def catalog_runs(module):
    """Unsaved flat adapter for radius scans, references and isotope cases.

    The logical case ID stays stable for job manifests and saved GUI choices.
    Values are existing nodes, not copied result payloads or a saved cache.
    """
    runs = OrderedDict()
    for rid, sources in case_sources(module).items():
        run = OrderedDict()
        for key, node, _ in sources:
            run[key] = _case_union(run[key], node) if key in run else node
        runs[rid] = run
    return runs


def case_destination(module, runid, caseid, info=None):
    """Resolve a read path during both old and grouped-format operation."""
    run = module.get('RUN_DB', {}).get(runid, {})
    if caseid in run:
        return [runid, caseid]
    path = grouped_case_path(caseid, info)
    radial = metadata_value(run.get(path[0], {}))
    # Pre-change projects keep all original scans under radius/BASE. Prefer
    # the actual indexed scan location while they await explicit migration.
    parts = case_parts(canonical_case_key(caseid, info))
    if parts is not None and parts[2] == 'BASE':
        info = {} if info is None else info
        branch = scan_key(info, (list(info.get('parameters', [])) or [''])[0])
        radial_scans = {scan_key(saved, key) for key, saved, _ in case_scans(radial)}
        if not branch and radial_scans:
            return [runid, path[0]]
        if branch and (branch in radial or branch in radial_scans):
            return [runid, path[0]]
        old = metadata_value(radial.get('BASE', {}))
        old_scans = {scan_key(saved, key) for key, saved, _ in case_scans(old)}
        if 'BASE' in radial and (not branch or branch in old or branch in old_scans):
            return [runid, path[0], 'BASE']
    return [runid] + path


def output_final_time(result):
    """Read only the last time row; no solver arrays or restart payload load."""
    try:
        with open(os.path.join(result.filename, 'out.cgyro.time'), 'rb') as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 16384))
            lines = handle.read().splitlines()
        for line in reversed(lines):
            fields = line.split()
            if fields:
                value = float(fields[0].replace(b'D', b'E').replace(b'd', b'e'))
                return value if math.isfinite(value) else None
    except (OSError, TypeError, ValueError):
        pass
    return None


def scan_key(info, fallback=''):
    """Identify the ordered axes, not their values, ky grid or run UUID.

    Results within this axis combination merge by full parameter coordinates
    and ky. Other combinations stay independent, including 1D versus 2D with
    the same first axis, linked axes and the ky-only fixed reference coordinate.
    """
    axes = info.get('scan_axes', [])
    if info.get('scan_dimensions', None) == 0 or (axes and all(axis.get('fixed', False) for axis in axes)):
        return 'KY_ONLY'
    if axes:
        return '__'.join(str(axis['name']) + ''.join('+' + str(link['name'])
            for link in axis.get('linked', [])) for axis in axes)
    return str(info.get('scan_key', '') or fallback)


def case_scans(case):
    """Read new per-scan indexes and the former single-record case schema."""
    case = metadata_value(case)
    if '__SCANS__' in case:
        return [(str(key), metadata_value(record['info']), metadata_value(record['tasks']))
                for key, record in metadata_value(case['__SCANS__']).items()]
    info, tasks = metadata_value(case.get('__INFO__', None)), metadata_value(case.get('__TASKS__', None))
    if info is None or tasks is None:
        return []
    parameters = info.get('parameters', [])
    return [(scan_key(info, parameters[0] if parameters else ''), info, tasks)]


def latest_output(module):
    """Read the latest indexed slice for old plotting entries, only in RUN_DB."""
    current = str(module.get('RUN_MANIFEST', {}).get('run_token', ''))
    candidates = []
    for runid, run in catalog_runs(module).items():
        if str(runid).startswith('__'):
            continue
        for key, case in run.items():
            if str(key).startswith('__') or not hasattr(case, 'get'):
                continue
            for _, info, tasks in case_scans(case):
                branch = scan_branch(case, info, tasks)
                candidates.append((str(info.get('run_token', '')) == current,
                    str(info.get('published_at', '')), len(candidates), branch, case[branch]))
    if candidates:
        _, _, _, branch, payload = max(candidates, key=lambda row: row[:3])
        return {branch: payload}
    old = legacy_branch(module, 'OUTPUTScan')
    if old:
        return old
    raise ValueError('No archived CGYRO scan in RUN_DB; collect or consolidate results first')


def scan_branch(data, info, tasks):
    """Find the one public root owned by a scan, including old isotope suffixes."""
    roots = {str(row['result_path'][0]) for row in tasks.values() if row.get('result_path', [])}
    if not roots:
        roots = set(str(key) for key in info.get('parameters', []))
    if len(roots) != 1:
        raise ValueError('Cannot identify the archived scan branch; existing results are preserved')
    original = list(roots)[0]
    if original in data:
        return original
    legacy = original + '_' + str(info.get('ion_case', ''))
    if legacy in data:
        return legacy
    raise ValueError('Missing archived scan branch: ' + original)


def point_coordinate(row):
    """A point is its complete stored parameter coordinate and signed ky.

    Numeric spelling (16 / 16.00000) and reused Slurm point IDs do not define
    identity. Never identify an entire spectrum by its first parameter alone.
    """
    path = list(metadata_value(row).get('result_path', []))
    if len(path) not in (4, 6, 8) or path[-2] != 'lin':
        raise ValueError('Invalid archived parameter/ky path')
    values = tuple(float(path[index]) for index in list(range(1, len(path) - 2, 2)) + [len(path) - 1])
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Non-finite archived parameter/ky coordinate')
    return tuple(str(path[index]) for index in range(2, len(path) - 2, 2)), values


def _at(data, path):
    for part in path:
        data = metadata_value(data)[part]
    return data


def _finite_final_time(row):
    """Unknown time is allowed; non-finite metadata cannot prove progress.

    In particular, every comparison with NaN is false, which would otherwise
    let a partial recollection bypass the guard protecting a completed point.
    Validate before changing any public scan or replacing its task index.
    """
    value = row.get('final_time', None)
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Non-finite archived final time; existing results are preserved')
    return value


def _install_point(payload, path, result, factory):
    """Reuse existing numeric keys so mixed float spelling cannot split curves."""
    node, actual = payload, []
    for index, part in enumerate(path):
        key = part
        if index % 2 or index == len(path) - 1:
            matches = []
            for candidate in node:
                try:
                    if float(candidate) == float(part):
                        matches.append(candidate)
                except (TypeError, ValueError):
                    pass
            if len(matches) > 1:
                raise ValueError('Ambiguous numeric archive key: ' + str(part))
            if matches:
                key = matches[0]
        actual.append(key)
        if index == len(path) - 1:
            node[key] = copy_result_tree(result, factory)
        else:
            node = node.setdefault(key, factory())
    return actual


def store_scan(destination, data, info, tasks, factory=dict, prefer_progress=False):
    """Upsert points off-tree: replace matching coordinates, retain other ky.

    Keep incoming point IDs for its job/continuation records. Reassign only
    colliding retained IDs, recording source_point_id and each row's run_token.
    File payloads remain references to the sole physical owner in RUN_DB.
    """
    original = scan_branch(data, info, tasks)
    key = scan_key(info, original)
    if not key or key.startswith('__'):
        raise ValueError('Invalid archived scan identity')
    saved_info, saved_tasks = factory(), factory()
    saved_info.update(deepcopy(dict(info)))
    existing = {name: (old_info, old_tasks) for name, old_info, old_tasks in case_scans(destination)}
    points, incoming = OrderedDict(), set()
    if key in existing:
        old_info, old_tasks = existing[key]
        for point, source in old_tasks.items():
            row = deepcopy(dict(metadata_value(source)))
            _finite_final_time(row)
            row.setdefault('run_token', old_info.get('run_token', ''))
            coordinate = point_coordinate(row)
            if coordinate in points:
                raise ValueError('Duplicate coordinate in existing scan')
            points[coordinate] = (str(point), row, _at(destination, row['result_path']), False)
        axes = deepcopy(list(info.get('scan_axes', [])))
        for axis, old_axis in zip(axes, old_info.get('scan_axes', [])):
            axis['values'] = sorted(set(list(axis.get('values', [])) + list(old_axis.get('values', []))), key=float)
        saved_info['scan_axes'] = axes
    for point, source in metadata_value(tasks).items():
        row = deepcopy(dict(metadata_value(source)))
        _finite_final_time(row)
        coordinate = point_coordinate(row)
        if coordinate in incoming:
            raise ValueError('Duplicate coordinate in incoming scan')
        incoming.add(coordinate)
        row.setdefault('run_token', info.get('run_token', ''))
        path = list(row['result_path'])
        path[0] = original
        result = _at(data, path)
        if coordinate in points:
            old_point, old_row, old_result, _ = points[coordinate]
            old_complete = point_complete(old_row, legacy_default=True)
            new_complete = point_complete(row, legacy_default=True)
            old_time, new_time = _finite_final_time(old_row), _finite_final_time(row)
            if ((old_complete and not new_complete and
                    (old_time is None or new_time is None or float(new_time) <= float(old_time))) or
                    (not old_complete and not new_complete and old_time is not None
                     and (new_time is None or float(new_time) < float(old_time))) or
                    (prefer_progress and old_time is not None and new_time is not None
                     and float(new_time) < float(old_time))):
                # Incomplete recollection must not replace a useful completed
                # result, or roll a checkpoint back to an earlier saved time.
                row, result = deepcopy(old_row), old_result
                if str(point) != old_point:
                    row.setdefault('source_point_id', old_point)
        points[coordinate] = (str(point), row, result, True)
    reserved = {point for point, _, _, fresh in points.values() if fresh}
    reserved.update(str(point) for point in info.get('planned_points', []))
    used, payload = set(), factory()
    number = max([int(point[1:]) for point, _, _, _ in points.values()
                  if re.fullmatch(r'p[0-9]{6,}', point)] + [0])
    for point, source, result, fresh in points.values():
        assigned = point
        while assigned in used or not fresh and assigned in reserved:
            number += 1
            assigned = 'p{:06d}'.format(number)
        used.add(assigned)
        row = factory()
        row.update(source)
        if assigned != point:
            row.setdefault('source_point_id', point)
        row['task_id'] = assigned
        path = [key] + list(row['result_path'])[1:]
        row['result_path'] = _install_point(payload, path, result, factory)
        saved_tasks[assigned] = row
    saved_info.update(dict(scan_key=key, parameters=[key]))
    saved_info['points'] = len(saved_tasks)
    saved_info['merged_run_tokens'] = list(dict.fromkeys(str(row.get('run_token', '')) for row in saved_tasks.values()))
    record = factory()
    record.update(dict(info=saved_info, tasks=saved_tasks))
    destination[key] = payload[key]
    destination.setdefault('__SCANS__', factory())[key] = record
    # Compatibility views describe the most recently published scan only.
    # New readers use __SCANS__ to offer every retained parameter scan.
    destination['__INFO__'], destination['__TASKS__'] = saved_info, saved_tasks


def combine_cases(cases, factory=dict):
    """Merge indexed points off-tree, retaining every different scan and ky."""
    destination = factory()
    for case in cases:
        records = case_scans(case)
        owned = {scan_branch(case, info, tasks) for _, info, tasks in records}
        for key in case:
            if not str(key).startswith('__') and key not in owned:
                # Unindexed legacy branches remain available to plot readers.
                destination[key] = copy_result_tree(case[key], factory)
        for _, info, tasks in records:
            store_scan(destination, case, info, tasks, factory)
    return destination


def install_case(run, caseid, case, factory=dict):
    """Install one logical case without replacing neighboring isotope scans.

    An original-species case can contain ordinary scans and a fixed-input
    reference together. Partition their indexes off-tree before installing
    the radial node once; payloads remain references to the RUN_DB owners.
    """
    records = case_scans(case)
    if not records:
        raise ValueError('Cannot install an unindexed CGYRO case')
    first_info = records[0][1]
    cid = canonical_case_key(caseid, first_info)
    parts = case_parts(cid)
    if parts is None:
        raise ValueError('Missing archived case identity')
    radial = grouped_case_path(cid, first_info)[0]
    existing = metadata_value(run.get(radial, {}))
    if (any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(existing).__mro__)
            or not hasattr(existing, 'items')):
        raise ValueError('Cannot replace an unclassified radial node')
    group = factory()
    group.update(dict(existing))
    if parts[2] != 'BASE':
        group[parts[2]] = case
        run[radial] = group
        return
    ordinary, reference = factory(), factory()
    owned = set()
    for _, info, tasks in records:
        owned.add(scan_branch(case, info, tasks))
        saved = deepcopy(dict(info))
        saved['case_path'] = grouped_case_path(cid, saved)
        destination = reference if len(saved['case_path']) == 2 else ordinary
        store_scan(destination, case, saved, tasks, factory)
    if any(not str(key).startswith('__') and key not in owned for key in case):
        raise ValueError('Unindexed original scans must be classified before installation')
    # Remove only the prior original-case scaffolding, keeping H/D/T nodes
    # and unrelated private metadata. Recovery preserves uncertain sources.
    for _, info, tasks in case_scans(existing):
        group.pop(scan_branch(existing, info, tasks), None)
    for key in ('__INFO__', '__SCANS__', '__TASKS__'):
        group.pop(key, None)
    if 'BASE' in group:
        old = metadata_value(group['BASE'])
        if (any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(old).__mro__)
                or not hasattr(old, 'items')):
            raise ValueError('Unclassified BASE contents are preserved; consolidate the archive first')
        old_owned = {scan_branch(old, info, tasks) for _, info, tasks in case_scans(old)}
        if any(key not in old_owned and key not in ('__INFO__', '__SCANS__', '__TASKS__') for key in old):
            raise ValueError('Unclassified BASE contents are preserved; consolidate the archive first')
        group.pop('BASE')
    if any(not str(key).startswith('__') and key in group for key in ordinary):
        raise ValueError('Original scan name conflicts with an isotope node')
    group.update(ordinary)
    if reference:
        group['BASE'] = reference
    run[radial] = group


def validate_preserved_scans(cases, destination, replaced_scan, incoming_tasks=None):
    """Refuse publication if merging would lose any different parameter scan.

    Only exact incoming parameter/ky coordinates are replaceable. Validate
    retained coordinates and result references before removing old aliases.
    """
    expected, unindexed, retained_points = {}, set(), {}
    changed = set() if incoming_tasks is None else {point_coordinate(row) for row in incoming_tasks.values()}
    for case in cases:
        records = case_scans(case)
        owned = {scan_branch(case, info, tasks) for _, info, tasks in records}
        unindexed.update(key for key in case if not str(key).startswith('__') and key not in owned)
        for key, info, tasks in records:
            key = scan_key(info, key)
            if key != replaced_scan:
                expected[key] = (info, tasks)
            else:
                for row in tasks.values():
                    coordinate = point_coordinate(row)
                    if coordinate not in changed:
                        retained_points[coordinate] = _at(case, row['result_path'])
    actual = {scan_key(info, key): (info, tasks) for key, info, tasks in case_scans(destination)}
    missing = (set(expected) | (unindexed - {replaced_scan})) - set(destination)
    if missing:
        raise ValueError('Archive retention check failed; previous scans are preserved: ' + ', '.join(sorted(missing)))
    retained_tasks = actual.get(replaced_scan, ({}, {}))[1]
    retained = {point_coordinate(row): _at(destination, row['result_path']) for row in retained_tasks.values()}
    for coordinate, result in retained_points.items():
        if coordinate not in retained or retained[coordinate] != result:
            raise ValueError('Archive retention check failed for prior parameter/ky coordinate: ' + str(coordinate))
    for key, (info, tasks) in expected.items():
        saved_info, saved_tasks = actual.get(key, ({}, {}))
        if (set(tasks) != set(saved_tasks) or
                str(info.get('run_token', '')) != str(saved_info.get('run_token', ''))):
            raise ValueError('Archive retention check failed for scan: ' + key)
        for point, row in tasks.items():
            path = list(row['result_path'])
            path[0] = key
            if path != list(saved_tasks[point]['result_path']):
                raise ValueError('Archive point path changed in retained scan: ' + key)
            node = destination
            for part in path:
                if part not in node:
                    raise ValueError('Archive point missing in retained scan: ' + key + ' / ' + str(point))
                node = node[part]


def matching_cases(module, runid, identity):
    """Return old case keys oldest-first, with the visible revision last."""
    run = catalog_runs(module).get(runid, {})
    _, aliases = latest_cases(module, runid)
    keys = [key for key in run if not str(key).startswith('__') and hasattr(run[key], 'get')
            and canonical_case_key(key, run[key].get('__INFO__', {})) == identity]
    # __INFO__ carries the publication timestamp for old and new records.
    return sorted(keys, key=lambda key: (key == aliases.get(identity, None),
        str(run[key].get('__INFO__', {}).get('published_at', '') or '')))


def canonical_case_key(value, info=None):
    """Strip only the UUID suffix formerly generated by the publisher."""
    text = re.sub(r'(?:__run=[0-9a-fA-F]{8})+$', '', str(value))
    match = re.fullmatch(r'nr=(.+?)__rho=([^_]+)__ion=([^_]+)', text)
    if match:
        nr, rho, ion = match.groups()
        try:
            rho = '{:.8g}'.format(float(rho)) if math.isfinite(float(rho)) else 'unknown'
        except ValueError:
            pass
        return 'nr={}__rho={}__ion={}'.format(nr, rho, ion)
    # Give old nr-only records an isotope identity when their metadata has it.
    match = re.fullmatch(r'nr=(.+?)(?:__ion=([^_]+))?', text)
    if match is not None and info is not None:
        nr, ion = match.groups()
        ion = ion or str(info.get('ion_case', info.get('mass', '')) or '')
        if ion:
            rho = info.get('rho', None)
            try:
                rho = '{:.8g}'.format(float(rho)) if math.isfinite(float(rho)) else 'unknown'
            except (TypeError, ValueError):
                rho = 'unknown'
            return 'nr={}__rho={}__ion={}'.format(nr, rho, ion)
    return text


def case_parts(value):
    text = canonical_case_key(value)
    match = re.fullmatch(r'nr=(.+?)__rho=([^_]+)__ion=([^_]+)', text)
    if match is not None:
        return match.groups()
    match = re.fullmatch(r'nr=(.+?)__ion=([^_]+)', text)
    return None if match is None else (match.group(1), 'unknown', match.group(2))


def latest_cases(module, runid, catalog=None):
    """Return actual readable keys and alias lookup; never delete old results.

    Former publishers inserted RUN_HISTORY and RUN_DB entries in publication
    order. Use that recorded order, never the random UUID's lexical order.
    """
    # A caller rendering several selectors can reuse its current metadata view.
    # The optional snapshot must not outlive that render or be saved in RUN_DB.
    run = (catalog_runs(module) if catalog is None else catalog).get(runid, {})
    history = module.get('RUN_HISTORY', {})
    order = {str(token): index for index, token in enumerate(history.keys())}
    current = module.get('RUN_MANIFEST', {})
    current_token = str(current.get('run_token', '')) if current.get('status', '') == 'published' else ''
    groups = OrderedDict()
    for index, key in enumerate(run.keys()):
        if str(key).startswith('__'):
            continue
        if not hasattr(run[key], 'get'):
            continue
        info = run[key].get('__INFO__', {})
        if not hasattr(info, 'get'):
            info = {}
        identity = canonical_case_key(key, info)
        groups.setdefault(identity, []).append((key, info, index))
    visible, aliases = [], {}
    for identity, candidates in groups.items():
        tokens = [str(info.get('run_token', '')) for _, info, _ in candidates]
        have_history = not getattr(history, 'sorted', False) and all(token in order for token in tokens)
        def rank(item):
            _, info, index = item
            token = str(info.get('run_token', ''))
            return (bool(current_token and token == current_token),
                    str(info.get('published_at', '') or ''), order[token] if have_history else index)
        key, _, _ = max(candidates, key=rank)
        visible.append(key)
        aliases[identity] = key
        for original, info, _ in candidates:
            aliases[str(original)] = key
            for replaced in info.get('replaced_case_keys', []):
                aliases[str(replaced)] = key
    return visible, aliases


def remap_case(value, aliases):
    return aliases.get(str(value), aliases.get(canonical_case_key(value), value))


def _remap_flags(state, key, transform):
    history = state.get('_selector_keys', {})
    if key not in history:
        return
    old_tokens = history[key]
    old_flags = state.get(key, {})
    enabled = {str(transform(token)) for index, token in enumerate(old_tokens)
               if old_flags.get(index, old_flags.get(str(index), False))}
    tokens = list(dict.fromkeys(str(transform(token)) for token in old_tokens))
    history[key] = tokens
    state[key] = {index: token in enabled for index, token in enumerate(tokens)}


def remap_case_selection(state, aliases):
    """Keep previous choices when a former revision maps to the latest case."""
    transform = lambda value: remap_case(value, aliases)
    for key in ('nr_selected', 'nr_CGYRO'):
        if key in state:
            state[key] = list(dict.fromkeys(transform(value) for value in state[key]))
    _remap_flags(state, 'nr_flag', transform)
    def radius(value):
        text = str(value)
        if text.startswith('legacy:'):
            parts = case_parts(transform(text[7:]))
            if parts is not None:
                return 'nr={}__rho={}'.format(parts[0], parts[1])
        return value
    if 'cgyro_radius_selected' in state:
        state['cgyro_radius_selected'] = list(dict.fromkeys(radius(value) for value in state['cgyro_radius_selected']))
    _remap_flags(state, 'cgyro_radius_flag', radius)
    for field in ('selected_paras_by_nr', 'para_list_flag_by_nr', 'cgyro_multi_by_nr'):
        if field not in state:
            continue
        old, remapped = state[field], {}
        for key, values in old.items():
            target = str(transform(key))
            if target not in remapped or str(key) == target:
                remapped[target] = values
        state[field] = remapped


def remap_pair_flags(state, aliases):
    old = state.get('rho_pair_flags', None)
    if old is None:
        return
    remapped = {}
    for case, flags in old.items():
        target = str(remap_case(case, aliases))
        merged = remapped.setdefault(target, {})
        for rho, enabled in flags.items():
            merged[rho] = bool(merged.get(rho, False) or enabled)
    state['rho_pair_flags'] = remapped
