"""Restore provable legacy scans into RUN_DB without guessing from GUI state.

Uncertain sources remain under RUN_DB/__UNCLASSIFIED__. A complete metadata
index and every physical point must validate before the original is removed.
Different parameter axes merge; conflicting historical versions stay separate.
"""
from builtins import (KeyError, TypeError, ValueError, all, any, dict, enumerate,
                      hasattr, len, list, set, str, tuple, type, vars)
from copy import deepcopy
import math
import re
from OMFITlib_cgyro_archive import (canonical_case_key, case_scans, combine_cases,
                                   scan_branch, scan_key, store_scan)
from OMFITlib_cgyro_db import PENDING, ensure_layout, metadata_value, run_records


def _point(case, path):
    node = case
    for part in path:
        node = metadata_value(node)[part]
    return node


def _reference(node):
    node = metadata_value(node)
    if any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(node).__mro__):
        return None
    if hasattr(node, 'get'):
        return node.get('__RESULT_REF__', None)
    return None


def _indexed_case(case, resolve, module, factory):
    case = metadata_value(case)
    records = case_scans(case)
    if not records:
        raise ValueError('No complete scan index')
    normalized, owned = factory(), set()
    for key, source_info, source_tasks in records:
        info = deepcopy(dict(metadata_value(source_info)))
        axes = list(info.get('scan_axes', []))
        names = [str(axis['name']) for axis in axes]
        if (not 1 <= len(names) <= 3 or len(set(names)) != len(names)
                or any('__' in name or re.fullmatch(r'[A-Z][A-Z0-9_]*', name) is None for name in names)):
            raise ValueError('Missing or ambiguous archived scan axes')
        branch = scan_branch(case, info, source_tasks)
        owned.add(branch)
        tasks = factory()
        for point, source_row in metadata_value(source_tasks).items():
            row = deepcopy(dict(metadata_value(source_row)))
            path = list(row.get('result_path', []))
            if len(path) != 2 * len(names) + 2 or path[-2] != 'lin':
                raise ValueError('Invalid point path: ' + str(point))
            actual_path = [branch] + path[1:]
            result = resolve(module, _point(case, actual_path))
            if not (any(base.__name__ == 'OMFITcgyro' for base in type(result).__mro__) or
                    any(base.__name__ == 'OMFITlazyLoad' for base in type(result).__mro__)
                    and vars(result).get('tp', '') == 'OMFITcgyro'):
                raise ValueError('Point has no verified CGYRO output: ' + str(point))
            values = dict(metadata_value(row.get('values', {})))
            for index, name in enumerate(names):
                if index and str(path[2 * index]) != name:
                    raise ValueError('Scan axis conflicts with stored point path')
                number = float(path[2 * index + 1])
                if not math.isfinite(number) or (name in values and not math.isclose(float(values[name]), number, rel_tol=1e-8, abs_tol=1e-10)):
                    raise ValueError('Conflicting archived coordinate: ' + name)
                values[name] = number
            ky = float(path[-1])
            if not math.isfinite(ky) or ('KY' in values and not math.isclose(float(values['KY']), ky, rel_tol=1e-8, abs_tol=1e-10)):
                raise ValueError('Conflicting archived ky')
            row.update(dict(task_id=str(point), values=dict(values, KY=ky), result_path=actual_path))
            tasks[point] = row
        if not tasks:
            raise ValueError('Empty archived scan')
        info.update(dict(dimensions=len(names), scan_dimensions=info.get('scan_dimensions', len(names))))
        store_scan(normalized, {branch: case[branch]}, info, tasks, factory)
    if {key for key in case if not str(key).startswith('__')} - owned:
        raise ValueError('Additional unindexed branches require separate verification')
    return normalized


def _same_scan(first, second, key):
    a = {scan_key(info, name): (info, tasks) for name, info, tasks in case_scans(first)}
    b = {scan_key(info, name): (info, tasks) for name, info, tasks in case_scans(second)}
    if key not in a or key not in b:
        return False
    info_a, tasks_a = a[key]
    info_b, tasks_b = b[key]
    if str(info_a.get('run_token', '')) != str(info_b.get('run_token', '')) or set(tasks_a) != set(tasks_b):
        return False
    return all(_reference(_point(first, tasks_a[p]['result_path'])) is not None and
               _reference(_point(first, tasks_a[p]['result_path'])) ==
               _reference(_point(second, tasks_b[p]['result_path'])) for p in tasks_a)


def recover_archives(module, resolve, factory=dict, exclude_token=''):
    """Reindex validated cases and retained unfinished runs; never submit jobs."""
    db = ensure_layout(module, factory)
    pending = db.get(PENDING, {})
    candidates = [(str(label), source, True) for label, source in pending.items()]
    # A pre-archive interrupted run may hold the only surviving H/D/T points.
    for token, record in run_records(module).items():
        if str(token) == str(exclude_token):
            continue
        manifest = record.get('manifest', {})
        points = record.get('cases', {})
        tasks, payload = factory(), factory()
        for point, row in manifest.get('point_table', {}).items():
            if point not in points or _reference(points[point]) is None:
                continue
            path = list(row.get('result_path', []))
            if not path:
                continue
            saved_row = deepcopy(dict(row))
            loaded = point in manifest.get('loaded_points', []) and point not in manifest.get('partial_points', [])
            saved_row.update(dict(task_id=str(point), status='loaded' if loaded else 'partial',
                run_token=str(token), runid=manifest.get('runid', ''), case_id=manifest.get('case_id', ''),
                rho=manifest.get('rho', None), ion_case=manifest.get('mass', ''), source_nr=manifest.get('nr', ''),
                result_workDir=manifest.get('point_workdirs', {}).get(point, manifest.get('workDir', '')),
                resume_pending=not loaded,
                continuation_pending=manifest.get('continuation_pending', {}).get(point, ''),
                scheduler_state=manifest.get('point_states', {}).get(point, '')))
            tasks[point] = saved_row
            node = payload
            for part in path[:-1]:
                node = node.setdefault(part, factory())
            node[path[-1]] = points[point]
        if tasks:
            complete = (set(tasks) == set(manifest.get('points', [])) and
                        set(tasks) == set(manifest.get('loaded_points', [])) and
                        not manifest.get('partial_points', []) and not manifest.get('failed_points', []))
            info = deepcopy(dict(manifest))
            info.update(dict(ion_case=manifest.get('mass', ''), source_nr=manifest.get('nr', ''),
                             planned_points=list(manifest.get('points', [])),
                             collection_status='complete' if complete else 'partial', status='recovered'))
            if not complete:
                info['runid'] = str(manifest.get('runid', 'Recovered')) + ' [partial ' + str(token)[:8] + ']'
            payload['__INFO__'], payload['__TASKS__'] = info, tasks
            candidates.append(('run ' + str(token), payload, False))
    recovered, issues = [], []
    for label, source, remove_source in candidates:
        try:
            normalized = _indexed_case(source, resolve, module, factory)
            updates = {}
            for key, info, tasks in case_scans(normalized):
                rid = str(info.get('runid', '')).strip()
                cid = canonical_case_key(info.get('case_id', ''), info)
                if not rid or rid.startswith('__') or not cid or '/' in rid or '/' in cid:
                    raise ValueError('Missing or unsafe archived run/case identity')
                existing = updates.get((rid, cid), db.get(rid, {}).get(cid, {}))
                existing_keys = {scan_key(i, k) for k, i, _ in case_scans(existing)}
                if key in existing_keys and not _same_scan(existing, normalized, key):
                    # Ambiguous older revisions must not overwrite a current
                    # same-axis result. Their data remain directly selectable.
                    rid += ' [recovered ' + str(info.get('run_token', '') or label)[-8:] + ']'
                    existing = updates.get((rid, cid), db.get(rid, {}).get(cid, {}))
                    if key in {scan_key(i, k) for k, i, _ in case_scans(existing)} and not _same_scan(existing, normalized, key):
                        raise ValueError('A different recovered revision already uses this identity')
                destination = combine_cases([existing], factory)
                copied_info = deepcopy(dict(info))
                copied_info.update(dict(runid=rid, case_id=cid, recovery_source=label))
                store_scan(destination, normalized, copied_info, tasks, factory)
                updates[(rid, cid)] = destination
            originals, created = {}, []
            try:
                for (rid, cid), value in updates.items():
                    if rid not in db:
                        db[rid] = factory()
                        created.append(rid)
                    originals[(rid, cid)] = db[rid].get(cid, None)
                    db[rid][cid] = value
                if remove_source:
                    pending.pop(label)
            except BaseException:
                for (rid, cid), value in originals.items():
                    if value is None:
                        db[rid].pop(cid, None)
                    else:
                        db[rid][cid] = value
                for rid in created:
                    db.pop(rid, None)
                raise
            recovered.append(label)
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(dict(source=label, reason=str(exc)))
    return dict(recovered=recovered, unresolved=issues)
