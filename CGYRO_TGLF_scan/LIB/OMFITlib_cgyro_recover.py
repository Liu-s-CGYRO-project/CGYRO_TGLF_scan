"""Restore provable legacy scans into RUN_DB without guessing from GUI state.

Uncertain sources remain under RUN_DB/__UNCLASSIFIED__. A complete metadata
index and every physical point must validate before the original is removed.
Different parameter axes and ky merge into one radius/isotope hierarchy.
"""
from builtins import (BaseException, KeyError, TypeError, ValueError, any, dict, enumerate,
                      float, hasattr, len, list, object, set, sorted, str, type, vars)
from copy import deepcopy
import math
import re
from OMFITlib_cgyro_archive import (canonical_case_key, case_scans, catalog_runs, clean_run_id,
                                   grouped_case_path, output_final_time, scan_branch, store_scan)
from OMFITlib_cgyro_db import PENDING, STATE, ensure_layout, metadata_value, run_records


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


def _retain_pending(pending, label, source):
    """Preserve ambiguous sources without overwriting an older retained name."""
    base, number = str(label).replace('/', '%2F'), 1
    label = base
    while label in pending and pending[label] is not source:
        number += 1
        label = '{} [{}]'.format(base, number)
    pending[label] = source


def _retain_private(pending, label, source, known=()):
    """Unrecognized private metadata can own payloads too; never drop it."""
    source = metadata_value(source)
    if (any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(source).__mro__)
            or not hasattr(source, 'items')):
        return
    if '__RESULT_REF__' in source or '__FILE_REF__' in source:
        return  # An opaque owner index is not a container of legacy metadata.
    for key, value in source.items():
        if str(key).startswith('__') and key not in known:
            _retain_pending(pending, str(label) + ' / ' + str(key), value)


def _indexed_case(case, resolve, module, factory):
    case = metadata_value(case)
    if (any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(case).__mro__)
            or not hasattr(case, 'get')):
        raise ValueError('A raw result has no complete case index')
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
            row.setdefault('status', 'partial' if info.get('collection_status', '') == 'partial' else 'loaded')
            row.setdefault('resume_pending', row['status'] != 'loaded')
            row['final_time'] = output_final_time(result)
            tasks[point] = row
        if not tasks:
            raise ValueError('Empty archived scan')
        info.update(dict(dimensions=len(names), scan_dimensions=info.get('scan_dimensions', len(names))))
        store_scan(normalized, {branch: case[branch]}, info, tasks, factory)
    if {key for key in case if not str(key).startswith('__')} - owned:
        raise ValueError('Additional unindexed branches require separate verification')
    return normalized


def recover_archives(module, resolve, factory=dict, exclude_token=''):
    """Consolidate all proven results into run / radius / isotope / scans.

    State and provenance stay in task metadata. No public partial, recovered or
    revision folders are created. The complete replacement is validated before
    touching the installed catalog; unknown sources remain inside RUN_DB.
    """
    db = ensure_layout(module, factory)
    pending = dict(metadata_value(db.get(PENDING, {})))
    grouped_before = db.get(STATE, {}).get('case_layout', '') == 'radius-ion'
    candidates = []
    public = [key for key in db if not str(key).startswith('__')]
    for rid, run in catalog_runs(module).items():
        _retain_private(pending, rid, db[rid])
        source = metadata_value(db[rid])
        if not any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(source).__mro__) and hasattr(source, 'items'):
            for key, value in source.items():
                if re.fullmatch(r'nr=.+_rho=[^_/]+', str(key)):
                    _retain_private(pending, str(rid) + ' / ' + str(key), value,
                                    ('__INFO__', '__SCANS__', '__TASKS__'))
        for cid, case in run.items():
            candidates.append((str(rid) + ' / ' + str(cid), case, False, str(rid), str(cid)))
        if not run:
            source = db[rid]
            # A malformed or unindexed root is preserved internally, never
            # guessed into the visible Jet hierarchy.
            if any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(source).__mro__) or not hasattr(source, 'items') or list(source):
                _retain_pending(pending, rid, source)
    candidates.extend((str(label), source, True, '', '') for label, source in list(pending.items()))
    for token, record in run_records(module).items():
        if str(token) == str(exclude_token):
            continue
        manifest, points = record.get('manifest', {}), record.get('cases', {})
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
                             collection_status='complete' if complete else 'partial'))
            payload['__INFO__'], payload['__TASKS__'] = info, tasks
            candidates.append(('run ' + str(token), payload, False, '', ''))
    validated, issues, recovered = [], [], []
    for order, (label, source, remove_source, rid_hint, cid_hint) in enumerate(candidates):
        try:
            normalized = _indexed_case(source, resolve, module, factory)
            _retain_private(pending, label, source, ('__INFO__', '__SCANS__', '__TASKS__'))
            for key, source_info, tasks in case_scans(normalized):
                info = deepcopy(dict(source_info))
                original_rid = str(info.get('source_runid', '') or info.get('runid', '') or rid_hint)
                rid = clean_run_id(original_rid)
                cid = canonical_case_key(info.get('case_id', '') or cid_hint, info)
                if not rid or rid.startswith(('__', 'Legacy ')) or not cid or '/' in rid or '/' in cid:
                    raise ValueError('Missing original run/case identity')
                radial, ion = grouped_case_path(cid, info)
                info.update(dict(runid=rid, case_id=cid, source_runid=rid, case_path=[radial, ion]))
                for row in tasks.values():
                    row.update(dict(runid=rid, case_id=cid))
                preference = 2 if rid_hint and clean_run_id(rid_hint) == rid_hint else 1 if rid_hint else 0
                validated.append((str(info.get('published_at', '') or ''), preference, order,
                                  rid, cid, radial, ion, normalized, info, tasks))
            if remove_source:
                pending.pop(label, None)
                recovered.append(label)
        except (KeyError, TypeError, ValueError) as exc:
            if rid_hint:
                _retain_pending(pending, label, source)
            issues.append(dict(source=label, reason=str(exc)))
    plans = {}
    for stamp, _, _, rid, cid, radial, ion, source, info, tasks in sorted(validated, key=lambda item: item[:3]):
        run = plans.setdefault(rid, factory())
        group = run.setdefault(radial, factory())
        destination = group.setdefault(ion, factory())
        store_scan(destination, source, info, tasks, factory, prefer_progress=not stamp)
    # All source records and references validated above. Installation never
    # renames physical files and can roll back even after OMFIT Abort.
    missing = object()
    original = {key: db[key] for key in public}
    old_pending, old_state = db.get(PENDING, missing), db.get(STATE, missing)
    try:
        for key in public:
            del db[key]
        for key, run in plans.items():
            db[key] = run
        retained = factory()
        retained.update(pending)
        db[PENDING] = retained
        state = factory()
        state.update(dict({} if old_state is missing else old_state))
        state.update(dict(version=5, case_layout='radius-ion'))
        db[STATE] = state
    except BaseException:
        for key in plans:
            db.pop(key, None)
        for key, value in original.items():
            db[key] = value
        for key, value in ((PENDING, old_pending), (STATE, old_state)):
            if value is missing:
                db.pop(key, None)
            else:
                db[key] = value
        raise
    return dict(recovered=recovered, unresolved=issues,
                grouped_cases=len(validated) if not grouped_before else 0)
