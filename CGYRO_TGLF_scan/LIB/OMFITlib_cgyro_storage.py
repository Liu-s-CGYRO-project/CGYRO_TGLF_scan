"""One immutable physical owner for CGYRO results, with serializable indexes.

References are ordinary native trees with a controlled native browser lookup.
Legacy owners are native directories. Explicit maintenance replaces them with
file manifests, so identical files share one native owner in a saved project.
The visible ``data`` child saves only expression text; readers resolve it lazily.
"""
from builtins import (BaseException, OSError, RuntimeError, ValueError, any, bool, dict, float, getattr, hasattr,
                      int, isinstance, iter, len, list, max, open, set, sorted, str, sum, tuple, type)
from copy import copy, deepcopy
import hashlib
import json
import os
import re
from omfit_classes.omfit_gacode import OMFITcgyro
from OMFITlib_cgyro_archive import solver_state
from OMFITlib_cgyro_checkpoint import select_checkpoint
from OMFITlib_cgyro_db import (POOL, STATE, STORAGE_SCHEMA_VERSION, ensure_layout, metadata_value,
                              result_pool, rollback_actions, run_cases, run_records, storage_state)
from OMFITlib_cgyro_recover import recover_archives
from OMFITlib_cgyro_retention import retire_superseded
from OMFITlib_cgyro_scratch import clean_stage, ensure_capacity
from OMFITlib_cgyro_storage_files import (FILE_STORE, SubmissionFiles,
                                         file_reference_id, native_kind, resolve_file)
from OMFITlib_cgyro_reference import (BROWSE, REF, copy_result_tree, is_native_file, make_reference,
                                      browse_current, validate_reference)
from OMFITlib_cgyro_payload import (FilePlan, deferred_key, inventory as payload_inventory, is_packed,
                                    pack_results, resolve_owner, sources as payload_sources)

STORE = POOL
CHECKPOINT_POLICY_VERSION = 1  # One verified restart, with old-file fallback.


def is_result(node):
    # Derived diagnostic objects may carry extra in-memory state. Do not
    # collapse those merely because they originated from the same directory.
    return native_kind(node, 'OMFITcgyro')


def _file_node(node):
    return is_native_file(node)  # Compatibility name for existing storage callers.


def reference_id(node):
    node = metadata_value(node)
    if _file_node(node) or not hasattr(node, 'items') or REF not in node:
        return None
    key = metadata_value(node[REF])
    return validate_reference(node, key)


def resolve_result(module, node):
    """Accept both the former native object and the new on-disk index."""
    node = metadata_value(node)
    key = reference_id(node)
    if key is None:
        return node
    return resolve_owner(module, key)


def result_view(module, node):
    """Return plain runtime scaffolding; never attach this view to the tree."""
    node = metadata_value(node)
    if isinstance(node, (list, tuple)):
        values = [result_view(module, item) for item in node]
        return tuple(values) if isinstance(node, tuple) else values
    if file_reference_id(node) is not None:
        return resolve_file(module, node)
    key = reference_id(node)
    if key is not None:
        return resolve_result(module, node)
    if _file_node(node) or not hasattr(node, 'items'):
        return node
    values = {key: result_view(module, value) for key, value in node.items()}
    if (isinstance(node, dict) and type(node) is not dict and
            not any(base.__name__ in ('OMFITtree', 'OMFITmodule', 'SortedDict') for base in type(node).__mro__)):
        # Headless/custom result mappings may implement lazy diagnostic reads.
        # Keep their reader protocol, but give the view independent containers.
        result = copy(node)
        for key, value in values.items():
            result[key] = value
        return result
    return values


def submission_file(module, manifest, name, point=None, *, stored_only=False):
    """Find a frozen input even after reopening a project on another machine.

    Point ZIP names on disk may belong to another deduplicated point. Callers
    that upload them must deploy to the requested point basename explicitly.
    """
    token = manifest.get('run_token', '')
    record = run_records(module).get(str(token), {})
    candidates = [record.get('inputs', {}), record.get('cases', {}) if stored_only else run_cases(module, manifest)]
    for cases in candidates:
        node = cases.get(point, {}) if point is not None else cases
        if not _file_node(node) and hasattr(node, 'get'):
            value = node.get(name, None)
            if value is not None:
                value = resolve_file(module, value)
                path = getattr(value, 'filename', '')
                if path and os.path.isfile(path):
                    return path
    if stored_only:
        raise ValueError('Frozen CGYRO submission file is missing from RUN_DB: ' + str(point or name))
    original = manifest.get('source_local_workDir', manifest.get('local_workDir', ''))
    path = os.path.join(str(original), str(point) + '.zip' if point is not None else name)
    if not original or not os.path.isfile(path):
        raise ValueError('Frozen CGYRO submission file is missing: ' + path)
    return path


def content_key(files):
    """Hash names and complete retained bytes, including logs and inputs."""
    raw = json.dumps(sorted(files), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def directory_inventory(directory, omitted=()):
    """Reject changing/symlinked data instead of identifying it as a duplicate."""
    if not os.path.isdir(directory) or os.path.islink(directory):
        raise ValueError('Missing or linked CGYRO result directory: ' + str(directory))
    files = []
    for parent, directories, names in os.walk(directory):
        directories.sort()
        for name in directories + names:
            if os.path.islink(os.path.join(parent, name)):
                raise ValueError('Linked file in CGYRO result: ' + name)
        for name in sorted(names):
            path = os.path.join(parent, name)
            relative = os.path.relpath(path, directory).replace(os.sep, '/')
            if relative in omitted:
                continue
            before = os.stat(path)
            digest = hashlib.sha256()
            with open(path, 'rb') as handle:
                for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b''):
                    digest.update(chunk)
            after = os.stat(path)
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError('CGYRO result changed during storage: ' + path)
            files.append((relative, after.st_size, digest.hexdigest()))
    if not files:
        raise ValueError('Empty CGYRO result directory: ' + str(directory))
    return files


def archive_inventory(directory):
    """Validate before omitting a checkpoint, then hash all retained bytes."""
    sizes, stamps = {}, {}
    for name in ('bin.cgyro.restart', 'bin.cgyro.restart.old', 'input.cgyro', 'input.cgyro.gen', 'out.cgyro.tag', 'out.cgyro.time'):
        path = os.path.join(directory, name)
        if os.path.islink(path):
            raise ValueError('Linked checkpoint metadata: ' + path)
        if os.path.isfile(path):
            stat = os.stat(path)
            sizes[name], stamps[name] = stat.st_size, (stat.st_size, stat.st_mtime_ns)
    omitted, report = select_checkpoint(sizes, lambda name: open(os.path.join(directory, name), 'rb'))
    files = directory_inventory(directory, omitted)
    hashes = {row[0]: row[2] for row in files}
    for name, result in report['candidates'].items():
        # An omitted damaged current file can still have a structural hash.
        # Compare payloads we actually retain; stamps below cover both files.
        if name not in omitted and result.get('sha256', hashes.get(name, None)) != hashes.get(name, None):
            raise RuntimeError('Checkpoint changed during validation: ' + name)
    for name, stamp in stamps.items():
        stat = os.stat(os.path.join(directory, name))
        if (stat.st_size, stat.st_mtime_ns) != stamp:
            raise RuntimeError('Checkpoint metadata changed: ' + name)
    return files, report


def _physical_copy(result, files):
    """Create a native private directory; never unlink a source checkpoint.

    Native deepcopy may share a loaded object's directory. A new OMFITcgyro
    owns a fresh OMFIT working directory, and only retained bytes enter it.
    """
    properties = dict(getattr(result, 'OMFITproperties', {}))
    for name in ('modifyOriginal', 'readOnly', 'noCopyToCWD', 'server', 'tunnel', 'remote', 's3bucket', 'file_type'):
        properties.pop(name, None)
    properties.setdefault('test_mode', getattr(result, 'test_mode', False))
    owned = OMFITcgyro('', **properties)
    if os.path.realpath(owned.filename) == os.path.realpath(result.filename):
        raise RuntimeError('Native result copy unexpectedly shares its source directory')
    ensure_capacity(owned.filename, sum(row[1] for row in files))
    for relative, size, expected in files:
        source = os.path.join(result.filename, relative)
        target = os.path.join(owned.filename, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        digest, copied = hashlib.sha256(), 0
        with open(source, 'rb') as incoming, open(target, 'xb') as outgoing:
            for chunk in iter(lambda: incoming.read(4 * 1024 * 1024), b''):
                outgoing.write(chunk)
                digest.update(chunk)
                copied += len(chunk)
        if copied != size or digest.hexdigest() != expected:
            raise RuntimeError('CGYRO result changed while copying: ' + source)
    return owned


def _reference(key, factory):
    return make_reference(key, factory)


def _collection_summary(module, key, result, files):
    """Capture facts once, while this newly collected point is already open.

    Reuse the storage validator's checkpoint report and inventory. Lists never
    stat directories or hash files to regenerate this persisted row summary.
    Time-averaged values are deliberately absent: their window is user-selected.
    """
    state = storage_state(module)
    checkpoint = json.loads(state.get('checkpoints', {}).get(key, '{}'))
    tag = checkpoint.get('tag', {}) or {}
    times = result['t']
    summary = dict(version=1, result_id=key, solver_status=solver_state(result),
                   sample_count=int(result['n_time']), final_time=float(times[-1]),
                   checkpoint_available=bool(checkpoint.get('resume_ready', False)),
                   checkpoint_time=tag.get('time', None),
                   checkpoint_reason=checkpoint.get('warning', ''),
                   bytes=state.get('bytes', {}).get(key, None),
                   file_sizes={name: size for name, size, _ in files})
    return summary


def store_result(module, result, factory=dict, *, summary_row=None):
    """Freeze a verified downloaded point before installing any public view."""
    ensure_layout(module, factory)
    deferred = deferred_key(module, result)
    if deferred is not None:
        return _reference(deferred, factory)
    old = reference_id(result)
    if old is not None:
        resolve_result(module, result)
        return _reference(old, factory)
    if not is_result(result):
        raise ValueError('Only native CGYRO output objects enter result storage')
    pool = result_pool(module, factory)
    for key in pool:
        if pool[key] is result:
            return _reference(key, factory)
    files, checkpoint = archive_inventory(result.filename)
    key = content_key(files)
    if key not in pool:
        if storage_state(module).get('file_dedup_version', 0):
            plan = FilePlan(module, factory)
            plan.add(key, result, files)
            plan.commit()
        else:
            pool[key] = _physical_copy(result, files)
    if not is_result(pool[key]) and not is_packed(pool[key]):
        raise ValueError('Invalid physical CGYRO result: ' + key)
    state = storage_state(module, factory)
    state.update(dict(version=max(STORAGE_SCHEMA_VERSION, state.get('version', 0)),
                      checkpoint_policy=CHECKPOINT_POLICY_VERSION))
    state.setdefault('bytes', factory())[key] = sum(row[1] for row in files)
    state.setdefault('checkpoints', factory())[key] = json.dumps(checkpoint, sort_keys=True)
    if summary_row is not None:
        summary = _collection_summary(module, key, result, files)
        summary_row['result_summary'] = summary
        summary_row.update(dict((name, summary[name]) for name in ('solver_status', 'final_time', 'checkpoint_time')))
    return _reference(key, factory)


def _storage_totals(pool, result_sizes, file_sizes, checkpoints):
    """Count only currently owned payloads, including after retirement.

    Compaction has an off-tree plan while consolidation observes the committed
    pool. Passing their explicit indexes keeps both reports on one definition
    without causing metadata writes or rereading solver directories.
    """
    reports = [json.loads(value) for key, value in checkpoints.items() if key in pool]
    result_files = {row[2] for key, owner in pool.items() if key != FILE_STORE and is_packed(owner)
                    for row in payload_inventory(owner, key)}
    logical_bytes = sum(result_sizes.get(key, 0) for key in pool if key != FILE_STORE)
    physical_bytes = (sum(result_sizes.get(key, 0) for key, owner in pool.items()
                          if key != FILE_STORE and not is_packed(owner)) +
                      sum(file_sizes.get(key, 0) for key in result_files))
    return dict(physical_results=len(pool) - int(FILE_STORE in pool),
                physical_bytes=physical_bytes, logical_result_bytes=logical_bytes,
                file_dedup_bytes=max(0, logical_bytes - physical_bytes),
                input_zip_bytes=sum(file_sizes.get(key, 0) for key in pool.get(FILE_STORE, {}) if key not in result_files),
                checkpoint_warnings=sum(1 for report in reports if report.get('warning', '')),
                backup_checkpoints=sum(1 for report in reports if report.get('selected', '') == 'bin.cgyro.restart.old'))


def compact_storage(module, factory=dict, browse=False, *, run_token=None):
    """Plan all replacements before committing; retain every unique result.

    In particular, partial/unpublished history is not a disposable cache. It
    receives the same references as published scans and remains restartable.
    No solver directory or prior project ZIP is deleted by this operation.
    Normal submission/queue callers pass the current token. Only explicit
    maintenance may migrate/hash unrelated legacy results across the project.
    """
    db = ensure_layout(module, factory, audit_history=run_token is None)
    pool = result_pool(module)
    previous_state = storage_state(module)
    sizes = dict(previous_state.get('bytes', {}))
    checkpoints = dict(previous_state.get('checkpoints', {}))
    additions, plans, paths, remapped = {}, {}, {}, {}
    submissions = SubmissionFiles(module, factory)
    raw_bytes, raw_copies = 0, 0

    def plan_result(node):
        directory = os.path.abspath(node.filename)
        if directory not in paths:
            files, checkpoint = archive_inventory(directory)
            paths[directory] = content_key(files), files, checkpoint
        key, files, checkpoint = paths[directory]
        sizes[key] = sum(row[1] for row in files)
        checkpoints[key] = json.dumps(checkpoint, sort_keys=True)
        if key not in pool and key not in additions:
            additions[key] = _physical_copy(node, files)
        return key

    # Also accept an earlier indexed project: install new owners first, then
    # redirect its public indexes. Unreferenced old owners are pruned later.
    if run_token is None and previous_state.get('checkpoint_policy', 0) != CHECKPOINT_POLICY_VERSION:
        for old, node in pool.items():
            if old != FILE_STORE:
                remapped[old] = plan_result(node)

    def convert(node):
        nonlocal raw_bytes, raw_copies
        node = metadata_value(node)
        if isinstance(node, (list, tuple)):
            values = [convert(item) for item in node]
            return tuple(values) if isinstance(node, tuple) else values
        file_key = file_reference_id(node)
        if file_key is not None:
            resolve_file(module, node)
            return submissions.reference(file_key)
        key = reference_id(node)
        if key is not None:
            if key not in pool and key not in additions:
                raise ValueError('Missing physical CGYRO result: ' + key)
            return _reference(remapped.get(key, key), factory)
        if is_result(node):
            key = plan_result(node)
            raw_bytes += sizes[key]
            raw_copies += 1
            return _reference(key, factory)
        if _file_node(node) or not hasattr(node, 'items'):
            return deepcopy(node)
        if submissions.pending(node):
            return submissions.convert_bundle(node, convert)
        if not has_raw(node):
            # Preserve ordinary metadata dictionaries, whose keys may be full
            # file paths. Native OMFITtree keys prohibit slashes.
            return copy_result_tree(node, factory)
        result = factory()
        for key, value in node.items():
            result[key] = convert(value)
        return result

    # Fast path: indexed projects need no directory reads on every queue update.
    def has_raw(node):
        node = metadata_value(node)
        if isinstance(node, (list, tuple)):
            return any(has_raw(item) for item in node)
        if is_result(node):
            return True
        if file_reference_id(node) is not None:
            resolve_file(module, node)
            return False
        key = reference_id(node)
        if key is not None:
            return key in remapped or (browse and (BROWSE not in node or not browse_current(node[BROWSE], key)))
        if _file_node(node) or not hasattr(node, 'items'):
            return False
        if submissions.pending(node):
            return True
        return any(has_raw(value) for value in node.values())

    plan_target = db
    if run_token is None:
        for branch, value in db.items():
            if branch not in (STORE, STATE) and has_raw(value):
                plans[branch] = convert(value)
    else:
        records = run_records(module)
        token = str(run_token)
        if token in records and has_raw(records[token]):
            plan_target = records
            plans[token] = convert(records[token])
    submissions.verify_sources()

    def summary(target):
        # Queue bookkeeping needs only this attempt's conversion counts.
        # Enumerating every packed inventory for global totals defeats the
        # scoped fast path even when no file is parsed. Explicit maintenance
        # remains responsible for complete physical/logical space statistics.
        report = (_storage_totals(target, sizes, submissions.sizes, checkpoints)
                  if run_token is None else dict(scope='run', run_token=str(run_token)))
        report.update(dict(converted_copies=raw_copies,
                    converted_input_zips=submissions.converted, expanded_input_bytes=submissions.omitted_bytes,
                    retained_expanded_files=submissions.retained_files,
                    duplicate_bytes=max(0, raw_bytes - sum(sizes[key] for key in additions)) +
                        max(0, submissions.raw_bytes - sum(submissions.sizes[key] for key in submissions.additions)) +
                        submissions.omitted_bytes))
        return report

    if (not plans and not additions and not submissions.additions and
            (run_token is not None or previous_state.get('checkpoint_policy', 0) == CHECKPOINT_POLICY_VERSION)
            and STORE in db):
        # Queue bookkeeping calls this repeatedly. A verified, already indexed
        # tree needs no commit: avoid deep-copying/replacing all saved size and
        # checkpoint metadata, which also invalidates native GUI/lazy views.
        # Still inspect live branches above; users can import legacy owners at
        # any time, so a persistent "compacted" flag would be unsafe.
        return summary(pool)
    original = {branch: plan_target[branch] for branch in plans}
    previous_sizes = db.get(STATE, None)
    created_pool = STORE not in db
    target = result_pool(module, factory)
    created_files = FILE_STORE not in target
    try:
        for key, value in additions.items():
            target[key] = value
        if submissions.additions:
            files = target.setdefault(FILE_STORE, factory())
            for key, value in submissions.additions.items():
                files[key] = value
        for branch, replacement in plans.items():
            plan_target[branch] = replacement
        state = factory()
        state.update(deepcopy(dict(previous_state)))
        # A scoped pass has not revalidated the other legacy owners. Do not
        # advertise a project-wide checkpoint migration that never happened.
        policy = CHECKPOINT_POLICY_VERSION if run_token is None else previous_state.get('checkpoint_policy', 0)
        state.update(dict(version=max(STORAGE_SCHEMA_VERSION, previous_state.get('version', 0)),
                          checkpoint_policy=policy, bytes=sizes, checkpoints=checkpoints,
                          file_bytes=submissions.sizes))
        db[STATE] = state
    except BaseException as original_error:
        errors = rollback_actions(original_error,
            ((branch, lambda branch=branch, value=value: plan_target.__setitem__(branch, value))
             for branch, value in original.items()))
        if not errors:
            # A rejected branch restoration may leave indexes to new owners.
            # Keep those immutable owners reachable instead of turning a
            # recoverable rollback error into missing scientific data.
            cleanup = [(key, lambda key=key: target.pop(key, None)) for key in additions]
            cleanup.extend((key, lambda key=key: target.get(FILE_STORE, {}).pop(key, None))
                           for key in submissions.additions)
            if created_files:
                cleanup.append((FILE_STORE, lambda: target.pop(FILE_STORE, None)))
            if created_pool:
                cleanup.append((STORE, lambda: db.pop(STORE, None)))
            rollback_actions(original_error, cleanup)
        rollback_actions(original_error, [(STATE,
            (lambda: db.pop(STATE, None)) if previous_sizes is None else
            (lambda: db.__setitem__(STATE, previous_sizes)))])
        raise
    return summary(target)


def prune_storage(module, *, result_ids=None):
    """Drop unreachable pool entries atomically; never delete physical files.

    Validate the complete reference graph before changing any owner. Keep a
    shallow rollback journal: a native result object must not be deep-copied
    merely to protect a metadata transaction from Abort or an assignment error.
    """
    db = ensure_layout(module, audit_history=result_ids is None)
    pool = result_pool(module)
    used, used_files = set(), set()
    bounded = result_ids is not None
    candidates = set(result_ids or [])

    def visit(node):
        # Resolve reopened metadata before classifying native file leaves.
        # Otherwise an unopened old scan can look unreachable and be pruned.
        node = metadata_value(node)
        if isinstance(node, (list, tuple)):
            for item in node:
                visit(item)
            return
        file_key = file_reference_id(node)
        if file_key is not None:
            if not bounded:
                resolve_file(module, node)
            used_files.add(file_key)
            return
        key = reference_id(node)
        if key is not None:
            if not bounded and (key not in pool or not (is_result(pool[key]) or is_packed(pool[key]))):
                raise ValueError('Missing physical CGYRO result: ' + key)
            if not bounded and key not in used and is_packed(pool[key]):
                used_files.update(row[2] for row in payload_sources(module, pool[key], key))
            used.add(key)
        elif not _file_node(node) and hasattr(node, 'items'):
            for value in node.values():
                visit(value)

    for key, value in db.items():
        if key not in (STORE, STATE):
            visit(value)
    stale = [key for key in pool if key != FILE_STORE and key not in used and (not bounded or key in candidates)]
    files = pool.get(FILE_STORE, {})
    if bounded:
        # Publication only releases the replaced owners. Inventory is metadata:
        # never stat/hash/read unrelated result files as part of this cleanup.
        candidate_files = set()
        for key, owner in pool.items():
            if key == FILE_STORE or not is_packed(owner):
                continue
            try:
                digests = {row[2] for row in payload_inventory(owner, key)}
            except ValueError:
                used_files.update(files)  # An unknown owner may still need any blob.
                continue
            (candidate_files if key in stale else used_files).update(digests)
        # Every retained packed owner and input reference has contributed its
        # digests above. This also releases ZIPs detached by save_current without
        # inspecting any physical file or pruning unrelated result owners.
        stale_files = [key for key in files if key not in used_files]
    else:
        stale_files = [key for key in files if key not in used_files]
    state = storage_state(module)
    sizes = state.get('bytes', {})
    checkpoints = state.get('checkpoints', {})
    file_sizes = state.get('file_bytes', {})
    missing = []  # Unique sentinel; no persistent node or result copy.
    journal = [(pool, {key: pool[key] for key in stale}),
               (files, {key: files[key] for key in stale_files}),
               (sizes, {key: sizes.get(key, missing) for key in stale}),
               (checkpoints, {key: checkpoints.get(key, missing) for key in stale}),
               (file_sizes, {key: file_sizes.get(key, missing) for key in stale_files})]
    try:
        for key in stale:
            del pool[key]
            sizes.pop(key, None)
            checkpoints.pop(key, None)
        for key in stale_files:
            del files[key]
            file_sizes.pop(key, None)
    except BaseException as original_error:
        # Abort can arrive between a deletion and its size/index update. Restore
        # every planned key, including the interrupted operation's owner. A
        # native assignment may fail again during rollback: still restore the
        # remaining owners and indexes, without replacing the original Abort.
        errors = []
        for mapping, previous in journal:
            for key, value in previous.items():
                try:
                    if value is missing:
                        mapping.pop(key, None)
                    else:
                        mapping[key] = value
                except BaseException as rollback_error:
                    errors.append('storage ' + str(key) + ': ' + str(rollback_error))
        if errors:
            try:
                original_error.cgyro_rollback_errors = list(getattr(original_error, 'cgyro_rollback_errors', [])) + errors
            except BaseException:
                pass  # An immutable exception must still propagate unchanged.
        raise
    return len(stale) + len(stale_files)


def consolidate_storage(module, factory=dict):
    """The explicit migration/compaction command; no scheduler operation."""
    ensure_layout(module, factory, audit_history=True)
    # Free verified expansions before allocating new physical owners. Otherwise
    # an old project near its /tmp quota could not start compaction at all.
    staged = clean_staging(module, factory)
    cleanup = deepcopy(dict(storage_state(module).get('scratch_cleanup', {})))
    report = compact_storage(module, factory, browse=True)
    before_total = report['physical_bytes'] + report['input_zip_bytes']
    recovery = recover_archives(module, resolve_result, factory)
    storage_state(module, factory)['recovery'] = recovery
    report['recovered_archives'] = len(recovery['recovered'])
    report['unresolved_archives'] = len(recovery['unresolved'])
    before_bytes = dict(storage_state(module).get('bytes', {}))
    before_files = dict(storage_state(module).get('file_bytes', {}))
    retirement = retire_superseded(module, resolve_result, reference_id, prune=prune_storage)
    report['retired_runs'] = list(retirement['retire'])
    report['retired_points'] = {token: list(value['points']) for token, value in retirement['partial'].items()}
    report['retained_history'] = retirement['retained']
    report['unreferenced_results'] = retirement['unreferenced_results']
    state = storage_state(module)
    report['released_result_bytes'] = sum(size for key, size in before_bytes.items() if key not in state.get('bytes', {}))
    report['released_input_bytes'] = sum(size for key, size in before_files.items() if key not in state.get('file_bytes', {}))
    report['packed_results'] = pack_results(module, directory_inventory, factory)
    # Report the committed archive, not compact_storage's pre-retirement pool.
    # Otherwise the GUI would still claim that removed historical owners exist.
    pool = result_pool(module)
    report.update(_storage_totals(pool, state.get('bytes', {}), state.get('file_bytes', {}), state.get('checkpoints', {})))
    # Logical per-result bytes overlap after file deduplication. Only compare
    # unique physical totals to report newly released bytes on repeated runs.
    report['released_archive_bytes'] = max(0, before_total - report['physical_bytes'] - report['input_zip_bytes'])
    report['staging_bytes_removed'] = staged + clean_staging(module, factory)
    cleanup['bytes_removed'] = report['staging_bytes_removed']
    cleanup['warnings'] = list(cleanup.get('warnings', [])) + list(storage_state(module).get('scratch_cleanup', {}).get('warnings', []))
    storage_state(module, factory)['scratch_cleanup'] = cleanup
    return report


def clean_staging(module, factory=dict):
    """Only frozen, checksummed expansions can be removed from /tmp runs."""
    removed, warnings = 0, []
    protected = []
    def protect(node):
        node = metadata_value(node)
        if reference_id(node) is not None:
            return  # The owner is visited in __STORE__; never evaluate data.
        if _file_node(node):
            protected.append(getattr(node, 'filename', ''))
        elif isinstance(node, (list, tuple)):
            for child in node:
                protect(child)
        elif hasattr(node, 'items'):
            for child in node.values():
                protect(child)
    # Include old, not-yet-compacted owners and editable input readers too.
    for name in ('RUN_DB', 'INPUTS', 'BATCH_INPUTS'):
        protect(module.get(name, {}))
    records = dict(run_records(module))
    current = module.get('RUN_MANIFEST', {})
    token = str(current.get('run_token', ''))
    if token:
        records[token] = dict(manifest=current)
    for token, entry in records.items():
        manifest = entry.get('manifest', {})
        workdir = manifest.get('source_local_workDir', manifest.get('local_workDir', ''))
        if not workdir:
            continue
        for point, hashes in manifest.get('input_sha256', {}).items():
            if not os.path.isdir(os.path.join(workdir, 'staging', str(point))):
                continue
            try:
                packed = submission_file(module, manifest, 'zip', point=point)
                removed += clean_stage(workdir, token, point, packed, hashes, protected)
            except (OSError, ValueError) as exc:
                warnings.append(str(point) + ': ' + str(exc))
    storage_state(module, factory)['scratch_cleanup'] = dict(bytes_removed=removed, warnings=warnings)
    return removed
