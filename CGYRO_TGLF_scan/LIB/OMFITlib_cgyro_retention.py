"""Retire superseded run payloads, while preserving their small audit records.

This is deliberately separate from byte deduplication. A failed attempt differs
from a successful result, so hashing alone can never release its old checkpoint.
Only the explicit compaction/publication boundary may call this planner. GUI
rendering and scheduler polling must not prune or read solver directories.

The unit of retirement is a whole frozen run, not a point ID: p000001 is local
to one submission. Coverage uses run/case/scan/full coordinate (including signed
ky). Uncertain metadata, uncollected jobs and live continuation sources survive.
"""
from builtins import (BaseException, KeyError, TypeError, ValueError, any, bool, dict,
                      float, getattr, isinstance, len, list, set, sorted, str, tuple)
from copy import deepcopy
import json
import math

from OMFITlib_cgyro_archive import (canonical_case_key, case_scans, catalog_runs,
                                   clean_run_id, output_final_time, point_coordinate, scan_key)
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


def _cyclic_ancestry(manifests):
    """Find cycles and descendants that cannot prove a valid frozen ancestry.

    Each run has at most one continuation source, so memoizing finished paths
    keeps this linear in the number of records. A cycle consisting entirely of
    otherwise replaceable candidates must not disappear simply because the
    retained-child protection pass below would skip all of its members.
    """
    resolved = {}
    for token in manifests:
        path, positions, source = [], {}, token
        while source in manifests and source not in resolved and source not in positions:
            positions[source] = len(path)
            path.append(source)
            source = str(manifests[source].get('continuation', {}).get('source_token', '') or '')
        cyclic = source in positions or resolved.get(source, False)
        for visited in path:
            resolved[visited] = cyclic
    return {token for token, cyclic in resolved.items() if cyclic}


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
                    coordinate = identity + (point_coordinate(row),)
                    if coordinate in public:
                        ambiguous.add(coordinate)
                    public[coordinate] = (row, _at(case, row['result_path']))

    return public, ambiguous, public_anchors


def _replacement_evidence(token, entry, manifest, public, ambiguous, final_time, has_checkpoint, reference):
    """Prove replacement of one whole run; uncertain fields reject retirement.

    This function validates content coverage only. The caller separately keeps
    active runs, public anchors and ancestors required by surviving children.
    """
    identity = _identity(manifest)
    table = metadata_value(manifest.get('point_table', {}))
    expected = set(manifest.get('points', []))
    cases = metadata_value(entry.get('cases', {}))
    if not expected or expected - set(table):
        raise ValueError('Incomplete frozen point table')
    # Unknown extra payloads must not be discarded with a known point
    # map. Native submission scripts are retained in inputs by freeze.
    if set(cases) - expected:
        raise ValueError('Unclassified entries in frozen point map')
    for name, value in metadata_value(entry.get('inputs', {})).items():
        value = metadata_value(value)
        if name in expected:
            if set(value) != {'zip'} or file_reference_id(value['zip']) is None:
                raise ValueError('Unclassified frozen point input')
        elif name != 'scan.pbs' or not (file_reference_id(value) is not None or
                native_kind(value, 'OMFITascii') or native_kind(value, 'OMFITpath')):
            raise ValueError('Unclassified entry in frozen inputs')
    replacements, changed = {}, False
    for point in sorted(expected):
        coordinate = identity + (point_coordinate(table[point]),)
        if coordinate in ambiguous or coordinate not in public:
            raise ValueError('Not every original coordinate is archived')
        row, new_node = public[coordinate]
        owner = str(row.get('run_token', ''))
        if not owner or not point_complete(row):
            raise ValueError('Replacement is unfinished or has unknown provenance')
        new_key = reference(new_node)
        if new_key is None:
            raise ValueError('Replacement has not been indexed')
        new_time = final_time(new_node, new_key)
        if new_time is None or not math.isfinite(float(new_time)):
            raise ValueError('Replacement has no validated final sample')
        old_node = cases.get(point, None)
        old_key = reference(old_node) if old_node is not None else None
        if old_node is not None and old_key is None:
            # A never-started point still owns its frozen ZIP. Complete
            # public coverage alone does not prove this input identical.
            raise ValueError('Frozen point is not an indexed result')
        if old_key is not None and old_key != new_key:
            old_time = final_time(old_node, old_key)
            if old_time is None or float(new_time) < float(old_time):
                raise ValueError('Replacement would lose sampled time')
            old_restart, new_restart = has_checkpoint(old_key), has_checkpoint(new_key)
            if old_restart is None or old_restart and new_restart is not True:
                raise ValueError('Replacement would lose a checkpoint fallback')
        if old_key is None and owner == token:
            raise ValueError('Missing original payload is not a newer replacement')
        changed = changed or owner != token
        replacements[point] = dict(run_token=owner, task_id=row.get('task_id', ''), result=new_key)
    if not changed:
        raise ValueError('No newer run covers this snapshot')
    return dict(reason='covered_by_current_archive', points=replacements)


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

    times, checkpoints = {}, storage_state(module).get('checkpoints', {})

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

    candidates, kept = {}, {}
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
            candidates[token] = _replacement_evidence(
                token, entry, manifest, public, ambiguous, final_time, has_checkpoint, reference)
        except (KeyError, TypeError, ValueError) as exc:
            kept[token] = str(exc)

    # Fixed point: an unretired partial child needs its ancestors, including an
    # otherwise replaceable parent. Complete published children use the public
    # archive directly and do not require stopped_context's ancestry traversal.
    manifests = {str(token): metadata_value(entry.get('manifest', {})) for token, entry in records.items()}
    active = module.get('RUN_MANIFEST', {})
    if current:
        manifests[current] = active
    for token in _cyclic_ancestry(manifests):
        if token in candidates:
            candidates.pop(token)
            kept[token] = 'cyclic continuation ancestry'
    for token, manifest in manifests.items():
        if token in candidates or manifest.get('status', '') == 'published' and _settled(manifest):
            continue
        if records.get(token, {}).get('payload_retired', None):
            continue
        seen, source = set(), str(manifest.get('continuation', {}).get('source_token', '') or '')
        while source and source not in seen:
            seen.add(source)
            if source in candidates:
                candidates.pop(source)
                kept[source] = 'required by retained continuation ' + token
            parent = manifests.get(source, {})
            source = str(parent.get('continuation', {}).get('source_token', '') or '')
    return dict(retire=candidates, retained=kept)


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
    if prune is not None and plan['retire']:
        pool, state = result_pool(module), storage_state(module)
        journal = [(mapping, dict(mapping.items())) for mapping in
                   (pool, pool.get(FILE_STORE, {}), state.get('bytes', {}),
                    state.get('checkpoints', {}), state.get('file_bytes', {}))]
    try:
        for token, evidence in plan['retire'].items():
            entry = records[token]
            original[token] = {key: entry[key] for key in ('cases', 'inputs', 'payload_retired') if key in entry}
            entry['payload_retired'] = deepcopy(evidence)
            entry.pop('cases', None)
            entry.pop('inputs', None)
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
            for key in ('cases', 'inputs', 'payload_retired'):
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
