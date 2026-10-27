"""Stable case identities and independent parameter scans within each case."""
from builtins import (AttributeError, OSError, TypeError, ValueError, all, any, bool, dict, enumerate, float, format, frozenset, getattr,
                      hasattr, int, isinstance, len, list, max, object, open, range, reversed, set, sorted, str, tuple, type, zip)
from collections import OrderedDict
from copy import deepcopy
import json
import math
import os
import re
from OMFITlib_cgyro_db import legacy_branch, metadata_value
from OMFITlib_cgyro_reference import copy_result_tree, same_result_reference
from OMFITlib_cgyro_run_state import point_complete


# Shared coordinate metadata stays below readers/recovery in the import graph.
# OMFIT removes its project importer after rendering a GUI; callbacks
# must use these already-bound definitions, never re-import a LIB.
# Runtime/output controls are excluded; DELTA_T and tolerances remain.
RUN_CONTROL_PARAMETERS = frozenset(('MAX_TIME', 'PRINT_STEP', 'RESTART_STEP',
    'RESTART_PRESERVATION_MODE', 'SILENT_FLAG', 'MPI_RANK_ORDER', 'TOROIDALS_PER_PROC',
    'MPIIO_STRIPE_FACTOR', 'MPIIO_SMALL_STRIPE_FACTOR', 'THETA_PLOT',
    'H_PRINT_FLAG', 'MOMENT_PRINT_FLAG', 'GFLUX_PRINT_FLAG', 'FIELD_PRINT_FLAG',
    'TRIAD_PRINT_FLAG', 'FULL_T_PRINT_FLAG', 'FULL_T_ASYM_PRINT_FLAG',
    'FULL_T_REAL_ONLY', 'FULL_T_DEBUG_PRINT_FLAG', 'FULL_T_KX0'))


RESULT_INFO_FIELDS = ('runid', 'case_id', 'source_nr', 'rho', 'ion_case', 'scan_axes', 'dimensions',
                      'scan_dimensions', 'fixed_parameters', 'numeric_parameters', 'scale_time_with_ky',
                      'runtime', 'server', 'case_tag', 'run_token')


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


def case_sources(module, runid=None, caseid=None):
    """Enumerate physical case nodes, keeping old BASE and direct scans apart.

    Recovery validates every source independently before moving any branch.
    Views here contain references to existing indexes, never result copies.
    """
    runs = OrderedDict()
    db = module.get('RUN_DB', {})
    sources = db.items() if runid is None else [(runid, db.get(runid, {}))]
    wanted = case_parts(caseid) if caseid else None
    for rid, source in sources:
        if str(rid).startswith('__'):
            continue
        entries = runs.setdefault(rid, [])
        source = metadata_value(source)
        if any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(source).__mro__) or not hasattr(source, 'items'):
            continue
        for key, node in source.items():
            if str(key).startswith('__'):
                continue
            if wanted:
                radial_key = 'nr={}_rho={}'.format(wanted[0], wanted[1])
                if (str(key) != radial_key and canonical_case_key(key) != caseid
                        and str(key) not in ('nr=' + wanted[0], 'nr={}__ion={}'.format(wanted[0], wanted[2]))):
                    continue
            node = metadata_value(node)
            radial = re.fullmatch(r'nr=(.+)_rho=([^_/]+)', str(key))
            mapping = (not any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad')
                               for base in type(node).__mro__) and hasattr(node, 'items'))
            if radial is None or not mapping:
                if wanted and canonical_case_key(key, node.get('__INFO__', {}) if mapping else {}) != caseid:
                    continue
                entries.append((key, node, [key]))
                continue
            if wanted and wanted[2] != 'BASE':
                if wanted[2] in node:
                    entries.append((caseid, node[wanted[2]], [key, wanted[2]]))
                continue
            records = case_scans(node)
            owned = {scan_branch(node, info, tasks) for _, info, tasks in records}
            if records:
                direct = OrderedDict((name, child) for name, child in node.items()
                                     if name in owned or name in ('__INFO__', '__SCANS__', '__TASKS__'))
                cid = 'nr={}__rho={}__ion=BASE'.format(*radial.groups())
                entries.append((cid, direct, [key]))
            for ion, case in node.items():
                if not str(ion).startswith('__') and ion not in owned and (wanted is None or ion == wanted[2]):
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


def catalog_runs(module, runid=None, caseid=None):
    """Unsaved flat adapter for radius scans, references and isotope cases.

    The logical case ID stays stable for job manifests and saved GUI choices.
    Values are existing nodes, not copied result payloads or a saved cache.
    """
    runs = OrderedDict()
    for rid, sources in case_sources(module, runid, caseid).items():
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


def result_file(result, name):
    """Read a small stored file without expanding a packed restart directory."""
    try:
        lookup = object.__getattribute__(result, '_payload_file')
    except AttributeError:
        return os.path.join(result.filename, name)
    return lookup(name)


def output_final_time(result):
    """Read only the last time row; no solver arrays or restart payload load."""
    try:
        with open(result_file(result, 'out.cgyro.time'), 'rb') as handle:
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


def solver_state(result):
    """Read a bounded solver log tail; scheduler completion is not convergence."""
    state = 'unknown'
    try:
        with open(result_file(result, 'out.cgyro.info'), 'rb') as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 32768))
            for line in handle.read().decode('utf-8', errors='replace').splitlines():
                if 'Linear converged' in line:
                    state = 'converged'
                elif 'Linear terminated at max time' in line:
                    state = 'max_time'
                elif 'Integration error exceeded limit' in line or line.lstrip().startswith('ERROR:'):
                    state = 'failed'
    except (OSError, AttributeError, ValueError):
        pass
    return state


def cache_merge_status(case, info, tasks, resolve):
    """Backfill old metadata only for coordinates this continuation competes with.

    Ordinary index queries never call this. Missing old caches require at most
    small log/time tails of the matching points, not solver arrays or binaries.
    """
    incoming = {full_point_coordinate(info, row) for row in tasks.values()}
    for key, saved, rows in case_scans(case):
        for row in rows.values():
            if key != scan_key(info) and row.get('input_parameters', None) is None:
                continue
            if full_point_coordinate(saved, row) not in incoming:
                continue
            if 'solver_status' not in row or row.get('final_time', None) is None:
                result = resolve(_at(case, row['result_path']))
                row.setdefault('solver_status', solver_state(result))
                if row.get('final_time', None) is None:
                    row['final_time'] = output_final_time(result)


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


def coordinate_path(row):
    """Axes/ky path, separate from a disambiguated physical leaf location."""
    row = metadata_value(row)
    return list(row.get('coordinate_path', row.get('result_path', [])))


def point_coordinate(row):
    """Read primary axes and signed ky from the saved coordinate path.

    Numeric spelling (16 / 16.00000) and reused Slurm point IDs do not define
    identity. Never identify an entire spectrum by its first parameter alone.
    """
    path = coordinate_path(row)
    if len(path) not in (4, 6, 8) or path[-2] != 'lin':
        raise ValueError('Invalid archived parameter/ky path')
    values = tuple(float(path[index]) for index in list(range(1, len(path) - 2, 2)) + [len(path) - 1])
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Non-finite archived parameter/ky coordinate')
    return tuple(str(path[index]) for index in range(2, len(path) - 2, 2)), values


def coordinate_matches(value, label):
    """Old tree labels round to five decimals; preserve the precise row value."""
    value, number = float(value), float(label)
    if not math.isfinite(value) or not math.isfinite(number):
        return False
    if math.isclose(value, number, rel_tol=1e-10, abs_tol=1e-12):
        return True
    text = str(label)
    if '.' in text and 'e' not in text.lower():
        return float(format(value, '.' + str(len(text.split('.')[1])) + 'f')) == number
    return False


def point_values(info, row, include_input=False):
    """Complete numeric coordinate, including fixed and linked parameters.

    A primary-axis tree path alone cannot distinguish two linked scans with
    different link values. The existing task table carries those coordinates;
    no result file, job record, or mutable GUI setting is needed here.
    """
    row = metadata_value(row)
    info = dict(info, **dict(row.get('result_info', {})))
    secondary, numbers = point_coordinate(row)
    axes = list(info.get('scan_axes', []))
    primary = [str(axis['name']) for axis in axes]
    if not primary:
        primary = [str(coordinate_path(row)[0]).split('__')[0].split('+')[0]] + list(secondary)
    if len(primary) != len(numbers) - 1 or tuple(primary[1:]) != secondary:
        raise ValueError('Result axis metadata disagrees with its coordinate')
    values = dict(info.get('fixed_parameters', {}))
    values.update(row.get('values', {}))
    labels = coordinate_path(row)
    labels = [labels[index] for index in list(range(1, len(labels) - 2, 2)) + [len(labels) - 1]]
    for name, value, label in zip(primary + ['KY'], numbers, labels):
        if name in values and not coordinate_matches(values[name], label):
            raise ValueError('Result coordinate disagrees with stored ' + name)
        values.setdefault(name, value)
    for axis in axes:
        for link in axis.get('linked', []):
            if link['name'] not in values:
                raise ValueError('Missing linked scan coordinate: ' + str(link['name']))
    values = {str(name): float(value) for name, value in values.items()}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError('Non-finite result coordinate')
    if include_input:
        # Generated values include solver defaults and actual ky-scaled DELTA_T.
        # Their consistency is checked when caching/continuing this point.
        values.update(row.get('effective_time', {}))
        values.update(row.get('input_parameters', {}))
        values = {name: value for name, value in values.items() if name not in RUN_CONTROL_PARAMETERS}
    return values


def full_point_coordinate(info, row):
    return tuple(sorted(point_values(info, row, include_input=True).items()))


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


def _prefer_old_result(old_row, new_row):
    old_time, new_time = _finite_final_time(old_row), _finite_final_time(new_row)
    old_converged = old_row.get('solver_status', '') == 'converged'
    new_converged = new_row.get('solver_status', '') == 'converged'
    # A failed continuation remains task data, not a replacement for a usable
    # public result. Fresh scans do not call this policy.
    if continuation_failed(new_row) and old_row.get('solver_status', '') in ('converged', 'max_time'):
        return True
    return (old_converged and not new_converged or
            old_converged == new_converged and old_time is not None and
            (new_time is None or new_time < old_time))


def continuation_failed(row):
    return (row.get('solver_status', '') == 'failed' or
            row.get('scheduler_state', '') in ('FAILED', 'OUT_OF_MEMORY', 'NODE_FAIL', 'TIMEOUT', 'CANCELLED', 'PREEMPTED'))


def summarize_tasks(info, tasks):
    """Update small header counts at mutation time, never in a list render."""
    counts = {}
    for row in tasks.values():
        token = str(row.get('run_token', info.get('run_token', '')))
        counts[token] = counts.get(token, 0) + 1
    info.update(dict(task_counts=counts, merged_run_tokens=list(counts), points=len(tasks)))


def share_matching_inputs(case, info, tasks, factory=dict, prefer_progress=False):
    """Unify proven equal-input references across existing scan views, off-tree.

    No branch or point index is removed. Only coordinates touched by this
    publication can change, and each must have expanded input metadata on both
    sides. The caller validates all other coordinates before committing.
    """
    wanted = {full_point_coordinate(info, row) for row in tasks.values()
              if row.get('input_parameters', None) is not None}
    groups = {}
    for key, saved, rows in case_scans(case):
        for point, row in rows.items():
            coordinate = full_point_coordinate(saved, row)
            if row.get('input_parameters', None) is not None and coordinate in wanted:
                groups.setdefault(coordinate, []).append((key, saved, rows, point, row))
    for matches in groups.values():
        current = [item for item in matches if item[0] == scan_key(info)]
        if not current or len(matches) < 2:
            continue
        winner = current[0][4]
        if prefer_progress:
            for _, _, _, _, candidate in matches:
                if _prefer_old_result(candidate, winner):
                    winner = candidate
        result = _at(case, winner['result_path'])
        for _, saved, rows, point, target in matches:
            row = factory()
            row.update(deepcopy(dict(winner)))
            row.update(dict(task_id=point, values=deepcopy(target.get('values', {})), result_path=list(target['result_path'])))
            row.pop('coordinate_path', None)
            if target.get('coordinate_path', None):
                row['coordinate_path'] = list(target['coordinate_path'])
            row.setdefault('result_info', {})
            for name in ('scan_axes', 'dimensions', 'scan_dimensions', 'fixed_parameters'):
                if name in saved:
                    row['result_info'][name] = deepcopy(saved[name])
            _at(case, row['result_path'][:-1])[row['result_path'][-1]] = copy_result_tree(result, factory)
            rows[point] = row
    for _, saved, rows in case_scans(case):
        summarize_tasks(saved, rows)


def store_scan(destination, data, info, tasks, factory=dict, prefer_progress=False):
    """Upsert points off-tree: replace matching coordinates, retain other ky.

    Keep incoming point IDs for its job/continuation records. Reassign only
    colliding retained IDs, recording source_point_id and each row's run_token.
    Fresh scans always replace matching coordinates. Continuations compare
    actual solver convergence first, then elapsed simulation time (not DELTA_T).
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
            row.setdefault('result_info', {name: deepcopy(old_info[name]) for name in RESULT_INFO_FIELDS if name in old_info})
            _finite_final_time(row)
            row.setdefault('run_token', old_info.get('run_token', ''))
            coordinate = full_point_coordinate(old_info, row)
            if coordinate in points:
                raise ValueError('Duplicate coordinate in existing scan')
            points[coordinate] = (str(point), row, _at(destination, row['result_path']), False)
        axes = deepcopy(list(info.get('scan_axes', [])))
        for axis, old_axis in zip(axes, old_info.get('scan_axes', [])):
            axis['values'] = sorted(set(list(axis.get('values', [])) + list(old_axis.get('values', []))), key=float)
        saved_info['scan_axes'] = axes
    for point, source in metadata_value(tasks).items():
        row = deepcopy(dict(metadata_value(source)))
        row.setdefault('result_info', {name: deepcopy(info[name]) for name in RESULT_INFO_FIELDS if name in info})
        _finite_final_time(row)
        coordinate = full_point_coordinate(info, row)
        if coordinate in incoming:
            raise ValueError('Duplicate coordinate in incoming scan')
        incoming.add(coordinate)
        row.setdefault('run_token', info.get('run_token', ''))
        path = list(row['result_path'])
        path[0] = original
        result = _at(data, path)
        if coordinate in points:
            old_point, old_row, old_result, _ = points[coordinate]
            if prefer_progress and _prefer_old_result(old_row, row):
                row, result = deepcopy(old_row), old_result
                if str(point) != old_point:
                    row.setdefault('source_point_id', old_point)
        points[coordinate] = (str(point), row, result, True)
    reserved = {point for point, _, _, fresh in points.values() if fresh}
    reserved.update(str(point) for point in info.get('planned_points', []))
    used, payload = set(), factory()
    number = max([int(point[1:]) for point, _, _, _ in points.values()
                  if re.fullmatch(r'p[0-9]{6,}', point)] + [0])
    # Ordinary scans keep their familiar tree. Only genuinely different full
    # coordinates sharing a primary-axis/ky path need one readable extra level.
    # Both physical locations stay in the existing task index; no second store.
    path_values = {}
    for _, row, _, _ in points.values():
        coordinate = point_coordinate(row)
        path_values.setdefault(coordinate, []).append(point_values(info, row, include_input=True))
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
        path = [key] + coordinate_path(row)[1:]
        row['result_path'] = list(path)
        row.pop('coordinate_path', None)
        variants = path_values[point_coordinate(row)]
        if len(variants) > 1:
            row['coordinate_path'] = list(path)
            values = point_values(info, row, include_input=True)
            varied = {name for item in variants for name in item
                      if len({item.get(name, None) for item in variants}) > 1}
            label = ', '.join('{}={:.17g}'.format(name, value) for name, value in sorted(values.items()) if name in varied)
            path.append(label or 'original parameters')
        row['result_path'] = _install_point(payload, path, result, factory)
        saved_tasks[assigned] = row
    saved_info.update(dict(scan_key=key, parameters=[key]))
    summarize_tasks(saved_info, saved_tasks)
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
    changed = set() if incoming_tasks is None else {full_point_coordinate({}, row) for row in incoming_tasks.values()}
    effective_changed = set() if incoming_tasks is None else {
        full_point_coordinate({}, row) for row in incoming_tasks.values() if row.get('input_parameters', None) is not None}
    for case in cases:
        records = case_scans(case)
        owned = {scan_branch(case, info, tasks) for _, info, tasks in records}
        unindexed.update(key for key in case if not str(key).startswith('__') and key not in owned)
        for key, info, tasks in records:
            key = scan_key(info, key)
            if key != replaced_scan:
                expected[key] = (case, info, tasks)
            else:
                for row in tasks.values():
                    coordinate = full_point_coordinate(info, row)
                    if coordinate not in changed:
                        retained_points[coordinate] = _at(case, row['result_path'])
    actual = {scan_key(info, key): (info, tasks) for key, info, tasks in case_scans(destination)}
    missing = (set(expected) | (unindexed - {replaced_scan})) - set(destination)
    if missing:
        raise ValueError('Archive retention check failed; previous scans are preserved: ' + ', '.join(sorted(missing)))
    retained_tasks = actual.get(replaced_scan, ({}, {}))[1]
    retained = {full_point_coordinate(actual.get(replaced_scan, ({}, {}))[0], row): _at(destination, row['result_path'])
                for row in retained_tasks.values()}
    for coordinate, result in retained_points.items():
        if coordinate not in retained or not same_result_reference(retained[coordinate], result):
            raise ValueError('Archive retention check failed for prior parameter/ky coordinate: ' + str(coordinate))
    for key, (source_case, info, tasks) in expected.items():
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
            coordinate = full_point_coordinate(info, row)
            expected_node = (retained[coordinate] if row.get('input_parameters', None) is not None
                             and coordinate in effective_changed and coordinate in retained else
                             _at(source_case, row['result_path']))
            if not same_result_reference(node, expected_node):
                raise ValueError('Archive result changed in retained scan: ' + key + ' / ' + str(point))


def matching_cases(module, runid, identity):
    """Return old case keys oldest-first, with the visible revision last."""
    catalog = catalog_runs(module, runid, identity)
    run = catalog.get(runid, {})
    _, aliases = latest_cases(module, runid, catalog=catalog)
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

    Public timestamps and archive order belong to RUN_DB. Job history cannot
    determine which physical result a reader sees, nor is a UUID chronological.
    """
    # A caller rendering several selectors can reuse its current metadata view.
    # The optional snapshot must not outlive that render or be saved in RUN_DB.
    run = (catalog_runs(module) if catalog is None else catalog).get(runid, {})
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
        def rank(item):
            _, info, index = item
            token = str(info.get('run_token', ''))
            return (bool(current_token and token == current_token),
                    str(info.get('published_at', '') or ''), index)
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


def normalized_info(info, runid='', caseid=''):
    saved = dict(metadata_value(info))
    saved.setdefault('runid', runid)
    saved.setdefault('case_id', caseid)
    saved.setdefault('source_nr', saved.get('nr', ''))
    saved.setdefault('ion_case', saved.get('mass', ''))
    saved.setdefault('dimensions', max(1, len(saved.get('scan_axes', []))))
    return saved


def result_identity(info, row):
    """Coordinate identity includes the case, every axis/link and signed ky.

    Existing path coordinates provide legacy numeric spelling normalization.
    Stored values must agree; an inconsistent old index is a point-level error,
    never permission to search for a nearby coordinate or another owner.
    """
    row = metadata_value(row)
    info = normalized_info(dict(info, **dict(row.get('result_info', {}))))
    # A merged scan header may describe a later submission. Point metadata,
    # when present, always identifies this row's own radius and ion case.
    for name in ('runid', 'case_id', 'rho', 'ion_case', 'source_nr'):
        if name in row:
            info[name] = row[name]
    path = coordinate_path(row)
    numeric = point_values(info, row, include_input=True)
    case = canonical_case_key(info.get('case_id', ''), info)
    parts = case_parts(case)
    if parts is None or not info.get('runid', ''):
        raise ValueError('Missing result radius/ion or run identity')
    nr, rho, ion = parts
    if not math.isfinite(float(rho)):
        raise ValueError('Missing finite result radius')
    if info.get('rho', None) is not None and not math.isclose(float(rho), float(info['rho']), rel_tol=1e-7, abs_tol=1e-10):
        raise ValueError('Result radius disagrees with its case identity')
    if info.get('ion_case', '') and str(info['ion_case']) != ion:
        raise ValueError('Result ion configuration disagrees with its case identity')
    if info.get('source_nr', '') != '' and str(info['source_nr']) != nr:
        raise ValueError('Result radial index disagrees with its case identity')
    return dict(runid=clean_run_id(info['runid']), case_id=case,
                scan=scan_key(info, path[0]), values=numeric)


def identity_key(identity):
    return json.dumps(identity, sort_keys=True, separators=(',', ':'), allow_nan=False)
