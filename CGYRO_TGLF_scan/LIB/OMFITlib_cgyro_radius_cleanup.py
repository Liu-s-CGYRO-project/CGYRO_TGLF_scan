"""Explicit deletion of one run/radius from this project, never remote files.

Use metadata identities, not substring matches or the current input editor.
Plan shallow reference removals first; keep original owners until pruning and
all metadata writes succeed so OMFIT Abort can restore the complete selection.
"""
from builtins import (BaseException, TypeError, ValueError, any, dict, float, hasattr, id, len,
                      list, object, reversed, set, sorted, str, tuple)
from copy import deepcopy
import math
from OMFITlib_cgyro_archive import canonical_case_key, case_parts, case_sources, clean_run_id
from OMFITlib_cgyro_db import (PENDING, ensure_layout, metadata_value, result_pool,
                              rollback_actions, run_records, storage_state)
from OMFITlib_cgyro_storage import prune_storage
from OMFITlib_cgyro_reference import is_native_file
from OMFITlib_cgyro_storage_files import FILE_STORE


def _case_info(case):
    # A raw OMFITcgyro also exposes mapping methods; do not read result arrays
    # merely to populate a deletion selector or inspect an old archive key.
    return {} if is_native_file(case) or not hasattr(case, 'get') else case.get('__INFO__', {})


def _identity(info, runid='', case_id=''):
    info = metadata_value(info)
    if not hasattr(info, 'get'):
        return None
    known_run = clean_run_id(info.get('runid', ''))
    runid = clean_run_id(runid or known_run)
    if known_run and runid != known_run:
        return None
    parts = case_parts(canonical_case_key(case_id or info.get('case_id', ''), info))
    nr, rho = ((parts[0], parts[1]) if parts is not None else
               (info.get('source_nr', info.get('nr', '')), info.get('rho', None)))
    try:
        rho = float(rho)
    except (ValueError, TypeError):
        return None
    if not runid or not str(nr) or not math.isfinite(rho):
        return None
    try:
        explicit_rho = float(info.get('rho', rho))
        if math.isfinite(explicit_rho) and not math.isclose(rho, explicit_rho, rel_tol=0, abs_tol=1e-12):
            return None
    except (ValueError, TypeError):
        pass  # Unknown metadata does not contradict a complete canonical key.
    return runid, str(nr), rho


def radius_choices(module):
    """Small metadata-only selector, including history with no archived result."""
    found = set()
    for runid, cases in case_sources(module).items():
        for case_id, case, path in cases:
            identity = _identity(_case_info(case), runid, case_id)
            if identity is not None:
                found.add(identity)
    for entry in list(module.get('RUN_HISTORY', {}).values()) + list(run_records(module).values()):
        identity = _identity(entry.get('manifest', {}))
        if identity is not None:
            found.add(identity)
    identity = _identity(module.get('RUN_MANIFEST', {}))
    if identity is not None:
        found.add(identity)
    return {'{} | nr={} | ρ={:.8g}'.format(*item): dict(runid=item[0], nr=item[1], rho=item[2])
            for item in sorted(found)}


def _matches(identity, target):
    return (identity is not None and identity[0] == target[0]
            and (target[1] is None or identity[1] == target[1])
            and math.isclose(identity[2], target[2], rel_tol=0, abs_tol=1e-12))


def _plan(module, runid, rho, nr):
    try:
        rho = float(rho)
    except (ValueError, TypeError):
        raise ValueError('Specify a finite radius explicitly.')
    runid = str(runid).strip()
    if not runid or runid.startswith('__') or clean_run_id(runid) != runid or not math.isfinite(rho):
        raise ValueError('Specify an exact run name and finite radius.')
    target = runid, None if nr in (None, '') else str(nr), rho
    db = module.get('RUN_DB', {})
    removals, seen, tokens, job_ids = [], set(), set(), set()
    def drop(mapping, key):
        stamp = id(mapping), key
        if key in mapping and stamp not in seen:
            seen.add(stamp)
            removals.append((mapping, key, mapping[key]))
    public = []
    for rid, cases in case_sources(module).items():
        for case_id, case, path in cases:
            info = _case_info(case)
            identity = _identity(info, rid, case_id)
            if identity is None and _matches(_identity({}, rid, case_id), target):
                raise ValueError('Selected archive has conflicting radius metadata: ' + str(case_id))
            if _matches(identity, target):
                # One selection covers BASE and all isotope/parameter children.
                drop(db[rid], path[0])
                public.append(str(rid) + '/' + str(path[0]))
    manifests, dependencies = {}, []
    for entries in (module.get('RUN_HISTORY', {}), run_records(module)):
        for token, entry in entries.items():
            manifest = metadata_value(entry.get('manifest', {}))
            if str(token) in manifests:
                previous = _identity(manifests[str(token)])
                incoming = _identity(manifest)
                if (previous is not None and incoming is not None and previous != incoming
                        and (_matches(previous, target) or _matches(incoming, target))):
                    raise ValueError('Conflicting history and RUN_DB identity for ' + str(token))
            manifests[str(token)] = manifest
            dependencies.append((str(token), manifest))
            if _matches(_identity(manifest), target):
                if manifest.get('status', '') in ('preparing', 'uploading', 'submitting', 'running', 'cancel_requested'):
                    raise ValueError('This radius has an operation in progress; finish that operation before deletion.')
                tokens.add(str(token))
                if manifest.get('job_id', ''):
                    job_ids.add(str(manifest['job_id']))
    current = module.get('RUN_MANIFEST', {})
    if _matches(_identity(current), target) and current.get('run_token', ''):
        if current.get('status', '') in ('preparing', 'uploading', 'submitting', 'running', 'cancel_requested'):
            raise ValueError('This radius has an operation in progress; finish that operation before deletion.')
        tokens.add(str(current['run_token']))
        if current.get('job_id', ''):
            job_ids.add(str(current['job_id']))
    if current.get('run_token', ''):
        dependencies.append((str(current['run_token']), current))
    # A different radius may still need a frozen checkpoint ancestor. Shared
    # physical result owners are handled by prune_storage's reachability pass.
    for token, manifest in dependencies:
        parent = str(manifest.get('continuation', {}).get('source_token', '') or '')
        if token not in tokens and parent in tokens:
            raise ValueError('Another retained run depends on this radius: ' + token)
    for entries in (module.get('RUN_HISTORY', {}), run_records(module)):
        for token in tokens:
            drop(entries, token)
    pending = metadata_value(db.get(PENDING, {}))
    for key, value in list(pending.items()):
        value = metadata_value(value)
        info = _case_info(value)
        if _matches(_identity(info), target):
            drop(pending, key)
    return dict(runid=runid, nr=target[1], rho=rho, tokens=sorted(tokens), jobs=sorted(job_ids),
                archives=sorted(set(public)), removals=removals)


def preview_radius(module, runid, rho, nr=None):
    plan = _plan(module, runid, rho, nr)
    return {key: value for key, value in plan.items() if key != 'removals'}


def _pool_journal(module):
    """Keep owners alive across an Abort immediately after pruning returns."""
    pool, state = result_pool(module), storage_state(module)
    mappings = [pool, pool.get(FILE_STORE, {})]
    mappings.extend(state.get(key, {}) for key in ('bytes', 'checkpoints', 'file_bytes'))
    return [(mapping, dict(mapping.items())) for mapping in mappings]


def _restore_pool(mapping, original):
    for key, value in original.items():
        if key not in mapping:
            mapping[key] = value


def remove_radius(module, runid, rho, nr=None, factory=dict, expected=None):
    """Delete the explicitly selected radius; caller confirms project data loss.

    No scheduler/SSH calls or filesystem deletions occur. Unsynchronized job
    metadata can be forgotten deliberately; a remote calculation still exists
    independently. Original inputs/prepared input cases are not result records.
    """
    ensure_layout(module, factory)
    plan = _plan(module, runid, rho, nr)
    report = {key: value for key, value in plan.items() if key != 'removals'}
    if expected is not None and report != expected:
        raise ValueError('The selected radius changed; review the deletion again.')
    removals, tokens = plan['removals'], set(plan['tokens'])
    if not removals:
        return report
    missing, journal, pool_journal = object(), [], []
    def assign(mapping, key, value):
        journal.append((mapping, key, mapping.get(key, missing)))
        mapping[key] = value
    batch = module.get('RUN_BATCH', {})
    current = module.get('RUN_MANIFEST', {})
    kept = [token for token in batch.get('tokens', []) if token not in tokens]
    try:
        for mapping, key, old in removals:
            journal.append((mapping, key, old))
            mapping.pop(key)
        if str(current.get('run_token', '')) in tokens or _matches(_identity(current),
                (plan['runid'], plan['nr'], plan['rho'])):
            assign(module, 'RUN_MANIFEST', factory())
        if batch.get('focus_token', '') in tokens or not kept:
            assign(module, 'RUN_BATCH', factory())
        elif len(kept) != len(batch.get('tokens', [])):
            changed = deepcopy(dict(batch))
            changed['tokens'] = kept
            changed['case_ids'] = [module['RUN_HISTORY'][token]['manifest'].get('case_id', token)
                                   for token in kept if token in module.get('RUN_HISTORY', {})]
            changed['completed'] = [case for case in changed.get('completed', []) if case in changed['case_ids']]
            changed['errors'] = []
            assign(module, 'RUN_BATCH', changed)
        # Drop an empty public run only after its selected children are removed.
        db = module['RUN_DB']
        for rid in list(db.keys()):
            if not str(rid).startswith('__') and clean_run_id(rid) == plan['runid'] and not db[rid]:
                journal.append((db, rid, db[rid]))
                db.pop(rid)
        pool_journal = _pool_journal(module)
        prune_storage(module)
    except BaseException as error:
        def restore(mapping, key, old):
            if old is missing:
                mapping.pop(key, None)
            else:
                mapping[key] = old
        rollback_actions(error, [('radius owner pool', lambda m=mapping, v=old: _restore_pool(m, v))
            for mapping, old in pool_journal] + [('radius cleanup ' + str(key),
            lambda m=mapping, k=key, v=old: restore(m, k, v))
            for mapping, key, old in reversed(journal)])
        raise
    return report
