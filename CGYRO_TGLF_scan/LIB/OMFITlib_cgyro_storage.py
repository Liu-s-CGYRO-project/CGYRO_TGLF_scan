"""One immutable physical owner for CGYRO results, with serializable indexes.

References are ordinary native trees, not Python aliases or dynamic expressions.
OMFIT therefore saves the directory once and can reload it without a custom data
class. Only explicit readers resolve indexes into temporary, unsaved views.
"""
from builtins import (OSError, RuntimeError, ValueError, any, dict, getattr, hasattr,
                      int, isinstance, iter, len, list, max, open, set, sorted, str, sum, tuple, type)
from copy import deepcopy
import hashlib
import json
import os
import re
from omfit_classes.omfit_gacode import OMFITcgyro
from OMFITlib_cgyro_checkpoint import select_checkpoint
from OMFITlib_cgyro_db import (POOL, STATE, ensure_layout, metadata_value,
                              result_pool, run_cases, run_records, storage_state)
from OMFITlib_cgyro_recover import recover_archives
from OMFITlib_cgyro_scratch import clean_stage, ensure_capacity
from OMFITlib_cgyro_storage_files import (FILE_STORE, SubmissionFiles,
                                         file_reference_id, native_kind, resolve_file)

STORE = POOL
REF = '__RESULT_REF__'
REFERENCE_WALK_VERSION = 4  # Direct radius scans and separate BASE references.


def is_result(node):
    # Derived diagnostic objects may carry extra in-memory state. Do not
    # collapse those merely because they originated from the same directory.
    return native_kind(node, 'OMFITcgyro')


def _file_node(node):
    # OMFITtree also has .filename (usually ''). It must remain traversable;
    # only native file readers are opaque leaves in the index scaffolding.
    names = {base.__name__ for base in type(node).__mro__}
    return 'OMFITobject' in names or 'OMFITlazyLoad' in names


def reference_id(node):
    node = metadata_value(node)
    if _file_node(node) or not hasattr(node, 'items') or REF not in node:
        return None
    key = metadata_value(node[REF])
    if len(node) != 1 or not isinstance(key, str) or re.fullmatch(r'[0-9a-f]{64}', key) is None:
        raise ValueError('Invalid CGYRO result reference')
    return key


def resolve_result(module, node):
    """Accept both the former native object and the new on-disk index."""
    node = metadata_value(node)
    key = reference_id(node)
    if key is None:
        return node
    result = result_pool(module).get(key, None)
    if result is None or not is_result(result):
        raise ValueError('Missing physical CGYRO result: ' + key)
    return result


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
    return {key: result_view(module, value) for key, value in node.items()}


def submission_file(module, manifest, name, point=None):
    """Find a frozen input even after reopening a project on another machine.

    Point ZIP names on disk may belong to another deduplicated point. Callers
    that upload them must deploy to the requested point basename explicitly.
    """
    token = manifest.get('run_token', '')
    record = run_records(module).get(str(token), {})
    candidates = [record.get('inputs', {}), run_cases(module, manifest)]
    for cases in candidates:
        node = cases.get(point, {}) if point is not None else cases
        if not _file_node(node) and hasattr(node, 'get'):
            value = node.get(name, None)
            if value is not None:
                value = resolve_file(module, value)
                path = getattr(value, 'filename', '')
                if path and os.path.isfile(path):
                    return path
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
    result = factory()
    result[REF] = key
    return result


def store_result(module, result, factory=dict):
    """Freeze a verified downloaded point before installing any public view."""
    ensure_layout(module, factory)
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
        pool[key] = _physical_copy(result, files)
    if not is_result(pool[key]):
        raise ValueError('Invalid physical CGYRO result: ' + key)
    state = storage_state(module, factory)
    state.update(dict(version=max(4, state.get('version', 0)), checkpoint_policy=1))
    state.setdefault('bytes', factory())[key] = sum(row[1] for row in files)
    state.setdefault('checkpoints', factory())[key] = json.dumps(checkpoint, sort_keys=True)
    return _reference(key, factory)


def compact_storage(module, factory=dict):
    """Plan all replacements before committing; retain every unique result.

    In particular, partial/unpublished history is not a disposable cache. It
    receives the same references as published scans and remains restartable.
    No solver directory or prior project ZIP is deleted by this operation.
    """
    db = ensure_layout(module, factory)
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
    if previous_state.get('checkpoint_policy', 0) != 1:
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
            return deepcopy(node)
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
            return key in remapped
        if _file_node(node) or not hasattr(node, 'items'):
            return False
        if submissions.pending(node):
            return True
        return any(has_raw(value) for value in node.values())

    for branch, value in db.items():
        if branch not in (STORE, STATE) and has_raw(value):
            plans[branch] = convert(value)
    submissions.verify_sources()
    original = {branch: db[branch] for branch in plans}
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
            db[branch] = replacement
        state = factory()
        state.update(deepcopy(dict(previous_state)))
        state.update(dict(version=max(4, previous_state.get('version', 0)), checkpoint_policy=1, bytes=sizes, checkpoints=checkpoints,
                          file_bytes=submissions.sizes))
        db[STATE] = state
    except BaseException:
        for branch, value in original.items():
            db[branch] = value
        for key in additions:
            target.pop(key, None)
        for key in submissions.additions:
            target.get(FILE_STORE, {}).pop(key, None)
        if created_files:
            target.pop(FILE_STORE, None)
        if created_pool:
            db.pop(STORE, None)
        if previous_sizes is None:
            db.pop(STATE, None)
        else:
            db[STATE] = previous_sizes
        raise
    reports = [json.loads(value) for key, value in checkpoints.items() if key in target]
    return dict(converted_copies=raw_copies, physical_results=len(target) - int(FILE_STORE in target),
                converted_input_zips=submissions.converted, expanded_input_bytes=submissions.omitted_bytes,
                retained_expanded_files=submissions.retained_files,
                input_zip_bytes=sum(submissions.sizes.get(key, 0) for key in target.get(FILE_STORE, {})),
                duplicate_bytes=max(0, raw_bytes - sum(sizes[key] for key in additions)) +
                    max(0, submissions.raw_bytes - sum(submissions.sizes[key] for key in submissions.additions)) +
                    submissions.omitted_bytes,
                physical_bytes=sum(sizes.get(key, 0) for key in target if key != FILE_STORE),
                checkpoint_warnings=sum(1 for report in reports if report.get('warning', '')),
                backup_checkpoints=sum(1 for report in reports if report.get('selected', '') == 'bin.cgyro.restart.old'))


def prune_storage(module):
    """Drop unreachable pool entries from the saved tree, never delete files."""
    db = ensure_layout(module)
    pool = result_pool(module)
    used, used_files = set(), set()

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
            resolve_file(module, node)
            used_files.add(file_key)
            return
        key = reference_id(node)
        if key is not None:
            if key not in pool or not is_result(pool[key]):
                raise ValueError('Missing physical CGYRO result: ' + key)
            used.add(key)
        elif not _file_node(node) and hasattr(node, 'items'):
            for value in node.values():
                visit(value)

    for key, value in db.items():
        if key not in (STORE, STATE):
            visit(value)
    stale = [key for key in pool if key != FILE_STORE and key not in used]
    files = pool.get(FILE_STORE, {})
    stale_files = [key for key in files if key not in used_files]
    state = storage_state(module)
    sizes = state.get('bytes', {})
    checkpoints = state.get('checkpoints', {})
    file_sizes = state.get('file_bytes', {})
    for key in stale:
        del pool[key]
        sizes.pop(key, None)
        checkpoints.pop(key, None)
    for key in stale_files:
        del files[key]
        file_sizes.pop(key, None)
    return len(stale) + len(stale_files)


def consolidate_storage(module, factory=dict):
    """The explicit migration/compaction command; no scheduler operation."""
    ensure_layout(module, factory)
    # Free verified expansions before allocating new physical owners. Otherwise
    # an old project near its /tmp quota could not start compaction at all.
    staged = clean_staging(module, factory)
    cleanup = deepcopy(dict(storage_state(module).get('scratch_cleanup', {})))
    report = compact_storage(module, factory)
    recovery = recover_archives(module, resolve_result, factory)
    storage_state(module, factory)['recovery'] = recovery
    report['recovered_archives'] = len(recovery['recovered'])
    report['unresolved_archives'] = len(recovery['unresolved'])
    report['unreferenced_results'] = prune_storage(module)
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
