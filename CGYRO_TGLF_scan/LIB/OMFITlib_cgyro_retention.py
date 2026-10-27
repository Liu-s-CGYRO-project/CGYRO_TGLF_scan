"""Retire superseded run payloads, while preserving their small audit records.

This is deliberately separate from byte deduplication. A failed attempt differs
from a successful result, so hashing alone can never release its old checkpoint.
Only the explicit compaction/publication boundary may call this planner. GUI
rendering and scheduler polling must not prune or read solver directories.

Retirement is per frozen coordinate, never by a point ID shared between jobs.
Coverage uses run/case/scan/full coordinate (including signed ky). Uncertain
metadata, uncollected jobs and live continuation sources survive.
"""
from builtins import (BaseException, KeyError, OSError, TypeError, ValueError, any, bool, dict,
                      float, getattr, isinstance, len, list, open, set, sorted, str, tuple)
from copy import deepcopy
import json
import math
import re

from OMFITlib_cgyro_archive import (canonical_case_key, case_scans, catalog_runs,
                                   clean_run_id, full_point_coordinate, output_final_time, result_file, scan_key)
from OMFITlib_cgyro_db import metadata_value, result_pool, run_records, storage_state
from OMFITlib_cgyro_storage_files import FILE_STORE, file_reference_id, native_kind
from OMFITlib_cgyro_run_state import collection_recorded, point_complete, run_settled


def _at(node, path):
    for part in path:
        node = metadata_value(node)[part]
    return node


def _identity(manifest):
    run = clean_run_id(manifest.get('runid', ''))
    case = canonical_case_key(manifest.get('case_id', ''), manifest)
    scan = scan_key(manifest)
    if not run or not case or not scan:
        raise ValueError('Missing run/case/scan identity')
    return run, case, scan


def _collected(manifest):
    # A scheduler failure alone says nothing about successful download. Missing
    # collection state must keep the frozen inputs available for recollection.
    return collection_recorded(manifest)


def _settled(manifest):
    """Collection and scheduler state must independently permit retirement.

    Synchronizing a requeued allocation may mark an old partial run submitted
    without clearing its collection status. Neither that stale status nor an
    unknown imported state can authorize discarding its frozen inputs.
    """
    return run_settled(manifest)


def _public_coverage(module):
    """Index exact coordinates and visible scan anchors without changing them."""
    public, ambiguous, public_anchors = {}, set(), set()
    for rid, cases in catalog_runs(module).items():
        for cid, case in cases.items():
            for name, info, tasks in case_scans(case):
                # The result dialog identifies a whole scan by this header,
                # while individual points may retain earlier run tokens after
                # an unadvanced continuation. Keep the dialog's frozen source
                # until a later publication replaces this scan header too.
                anchor = str(info.get('run_token', '') or '')
                if anchor:
                    public_anchors.add(anchor)
                identity = (clean_run_id(rid), canonical_case_key(cid, info), scan_key(info, name))
                for source in tasks.values():
                    row = metadata_value(source)
                    coordinate = identity + (full_point_coordinate(info, row),)
                    if coordinate in public:
                        ambiguous.add(coordinate)
                    public[coordinate] = (row, _at(case, row['result_path']))

    return public, ambiguous, public_anchors


def _frozen_points(entry, manifest):
    """Reject unknown payload shapes before planning selective removals."""
    table = metadata_value(manifest.get('point_table', {}))
    expected = set(manifest.get('points', []))
    cases = metadata_value(entry.get('cases', {}))
    if not expected or expected - set(table):
        raise ValueError('Incomplete frozen point table')
    # Unknown extra payloads must not be discarded with a known point
    # map. Native submission scripts are retained in inputs by freeze.
    if set(cases) - expected:
        raise ValueError('Unclassified entries in frozen point map')
    inputs = metadata_value(entry.get('inputs', {}))
    for name, value in inputs.items():
        value = metadata_value(value)
        if name in expected:
            if set(value) != {'zip'} or file_reference_id(value['zip']) is None:
                raise ValueError('Unclassified frozen point input')
        elif name != 'scan.pbs' or not (file_reference_id(value) is not None or
                native_kind(value, 'OMFITascii') or native_kind(value, 'OMFITpath')):
            raise ValueError('Unclassified entry in frozen inputs')
    retired = set(metadata_value(entry.get('retired_points', {})))
    if retired - expected or retired & (set(cases) | set(inputs)):
        raise ValueError('Inconsistent retired point metadata')
    return table, cases, expected - retired


def _linear_state(result):
    """Use solver termination messages, never a small numerical fluctuation."""
    state = 'unknown'
    with open(result_file(result, 'out.cgyro.info'), encoding='utf-8', errors='replace') as stream:
        for line in stream:
            if 'Linear converged' in line:
                state = 'converged'
            elif 'Linear terminated at max time' in line:
                state = 'max_time'
            elif 'Integration error exceeded limit' in line or line.lstrip().startswith('ERROR:'):
                state = 'failed'
    return state


def _physical_input(result):
    """Time/output limits can differ; a different physical input is a new case.

    Require identical input keys as well as values. This intentionally refuses
    to guess equivalence between missing defaults or different solver versions.
    """
    values = {}
    with open(result_file(result, 'input.cgyro'), encoding='utf-8') as stream:
        for line in stream:
            text = line.split('#', 1)[0].split('!', 1)[0].strip()
            if not text:
                continue
            match = re.fullmatch(r'([A-Z][A-Z_0-9]*)\s*=\s*(.+)', text)
            if match is None or match[1] in values:
                raise ValueError('Ambiguous archived physical input')
            values[match[1]] = match[2].strip()
    for key in ('MAX_TIME', 'PRINT_STEP'):
        values.pop(key, None)
    if not values or values.get('NONLINEAR_FLAG', '0') != '0':
        raise ValueError('Convergence retirement requires a linear physical input')
    return values


def _point_evidence(token, point, table, cases, identity, public, ambiguous,
                    final_time, has_checkpoint, reference, converged_replacement):
    coordinate = identity + (full_point_coordinate({}, table[point]),)
    if coordinate in ambiguous or coordinate not in public:
        raise ValueError('Not every original coordinate is archived')
    row, new_node = public[coordinate]
    owner = str(row.get('run_token', ''))
    if not owner or not point_complete(row):
        raise ValueError('Replacement is unfinished or has unknown provenance')
    if owner == token:
        raise ValueError('No newer run covers this coordinate')
    new_key = reference(new_node)
    if new_key is None:
        raise ValueError('Replacement has not been indexed')
    new_time = final_time(new_node, new_key)
    if new_time is None or not math.isfinite(float(new_time)):
        raise ValueError('Replacement has no validated final sample')
    old_node = cases.get(point, None)
    old_key = reference(old_node) if old_node is not None else None
    if old_node is not None and old_key is None:
        raise ValueError('Frozen point is not an indexed result')
    reason = 'covered_by_current_archive'
    if old_key is not None and old_key != new_key:
        old_time = final_time(old_node, old_key)
        if old_time is None or not math.isfinite(float(old_time)):
            raise ValueError('Original result has no validated final sample')
        if float(new_time) < float(old_time):
            if not converged_replacement(old_node, old_key, new_node, new_key):
                raise ValueError('Replacement would lose sampled time')
            reason = 'converged_linear_replacement'
        old_restart, new_restart = has_checkpoint(old_key), has_checkpoint(new_key)
        if old_restart is None or old_restart and new_restart is not True:
            raise ValueError('Replacement would lose a checkpoint fallback')
    return dict(run_token=owner, task_id=row.get('task_id', ''), result=new_key, reason=reason)


def retention_plan(module, resolve, reference):
    """Read-only plan; validate every replacement before removing any payload.

    Callers supply the storage resolver to avoid an import cycle. Time and
    checkpoint probes are cached only for this call; no persistent cache can
    hide an edited archive. Unknown branches are left for normal reachability
    pruning, which must still traverse them before removing any physical owner.
    """
    records = run_records(module)
    current = str(module.get('RUN_MANIFEST', {}).get('run_token', ''))
    public, ambiguous, public_anchors = _public_coverage(module)

    times, solver_states, physical_inputs = {}, {}, {}
    checkpoints = storage_state(module).get('checkpoints', {})

    def final_time(node, key):
        if key not in times:
            times[key] = output_final_time(resolve(module, node))
        return times[key]

    def has_checkpoint(key):
        report = metadata_value(checkpoints.get(key, None))
        if report is None:
            return None  # Legacy unknowns cannot prove a fallback redundant.
        if isinstance(report, str):
            report = json.loads(report)
        return bool(report.get('resume_ready', False))

    def converged_replacement(old, old_key, new, new_key):
        # A longer failed linear iteration is not necessarily a better result.
        # Only actual convergence with the same frozen physics can supersede it;
        # scheduler COMPLETED, small fluctuations and elapsed age cannot.
        for node, key in ((old, old_key), (new, new_key)):
            if key not in solver_states:
                result = resolve(module, node)
                solver_states[key] = _linear_state(result)
                physical_inputs[key] = _physical_input(result)
        return (solver_states[new_key] == 'converged' and
                solver_states[old_key] in ('max_time', 'failed') and
                physical_inputs[old_key] == physical_inputs[new_key])

    candidates, partial, kept = {}, {}, {}
    for token, entry in records.items():
        token, entry = str(token), metadata_value(entry)
        if entry.get('payload_retired', None) or not any(key in entry for key in ('cases', 'inputs')):
            continue
        manifest = metadata_value(entry.get('manifest', {}))
        if token in public_anchors:
            kept[token] = 'current public scan anchor'
            continue
        if token == current or not _collected(manifest) or manifest.get('submission_uncertain', False):
            kept[token] = 'current or uncollected run'
            continue
        if not _settled(manifest):
            kept[token] = 'active, unknown or inconsistent run state'
            continue
        try:
            table, cases, remaining = _frozen_points(entry, manifest)
            identity = _identity(manifest)
        except (KeyError, TypeError, ValueError) as exc:
            kept[token] = str(exc)
            continue
        covered, uncovered = {}, {}
        for point in sorted(remaining):
            try:
                covered[point] = _point_evidence(token, point, table, cases, identity,
                    public, ambiguous, final_time, has_checkpoint, reference, converged_replacement)
            except (KeyError, OSError, TypeError, ValueError) as exc:
                uncovered[point] = str(exc)
        if not uncovered:
            points = dict(metadata_value(entry.get('retired_points', {})))
            points.update(covered)
            candidates[token] = dict(reason='covered_by_current_archive', points=points)
        else:
            kept[token] = '; '.join(sorted(set(uncovered.values())))
            if covered:
                partial[token] = dict(points=covered, retained=uncovered)

    # Results are self-contained. Parent/child job links do not retain payloads.
    return dict(retire=candidates, partial=partial, retained=kept)


def retire_superseded(module, resolve, reference, prune=None):
    """Commit only payload links, retaining original manifests and provenance.

    Actual owner removal belongs to prune_storage, after it validates references
    from *all* branches. Roll back these edits on Abort or assignment failure.
    No original solver directory or project ZIP is ever unlinked here.
    """
    plan = retention_plan(module, resolve, reference)
    records, original = run_records(module), {}
    # The pool journal extends through the *outer* transaction. An Abort after
    # prune returns but before we return must not restore links to lost owners.
    # These are shallow object references only: no file/array copying occurs.
    journal = []
    changes = dict(plan['retire'])
    changes.update(plan['partial'])
    fields = ('cases', 'inputs', 'payload_retired', 'retired_points')
    if prune is not None and changes:
        pool, state = result_pool(module), storage_state(module)
        journal = [(mapping, dict(mapping.items())) for mapping in
                   (pool, pool.get(FILE_STORE, {}), state.get('bytes', {}),
                    state.get('checkpoints', {}), state.get('file_bytes', {}))]
    try:
        for token, evidence in changes.items():
            entry = records[token]
            original[token] = {key: entry[key] for key in fields if key in entry}
            if token in plan['retire']:
                entry['payload_retired'] = deepcopy(evidence)
                entry.pop('cases', None)
                entry.pop('inputs', None)
                entry.pop('retired_points', None)
            else:
                # Replace small containers, not their native file owners. Keep
                # originals alive until prune commits, for Abort/rollback.
                points = dict(metadata_value(entry.get('retired_points', {})))
                points.update(evidence['points'])
                entry['retired_points'] = points
                for field in ('cases', 'inputs'):
                    if field in entry:
                        entry[field] = {key: value for key, value in metadata_value(entry[field]).items()
                                        if key not in evidence['points']}
        if prune is not None:
            # The supplied pruner must itself roll back pool edits on failure.
            # Keep the old links alive until that reachability pass succeeds.
            plan['unreferenced_results'] = prune(module)
    except BaseException as original_error:
        errors = []
        for mapping, previous in journal:
            for key, value in previous.items():
                try:
                    mapping[key] = value
                except BaseException as rollback_error:
                    errors.append('owner ' + str(key) + ': ' + str(rollback_error))
        for token, values in original.items():
            try:
                entry = records[token]
            except BaseException as rollback_error:
                errors.append('run ' + str(token) + ': ' + str(rollback_error))
                continue
            # Restore independently: one rejected native assignment must not
            # prevent another run's links or this run's other fields returning.
            for key in fields:
                try:
                    if key in values:
                        entry[key] = values[key]
                    else:
                        entry.pop(key, None)
                except BaseException as rollback_error:
                    errors.append('run ' + str(token) + '/' + key + ': ' + str(rollback_error))
        if errors:
            try:
                original_error.cgyro_rollback_errors = list(getattr(original_error, 'cgyro_rollback_errors', [])) + errors
            except BaseException:
                pass  # Keep the original Abort and any inner prune diagnostics.
        raise
    return plan
