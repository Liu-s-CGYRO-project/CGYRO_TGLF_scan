"""One immutable physical owner for CGYRO results, with serializable indexes.

References are ordinary native trees, not Python aliases or dynamic expressions.
OMFIT therefore saves the directory once and can reload it without a custom data
class. Only explicit readers resolve indexes into temporary, unsaved views.
"""
from builtins import (OSError, RuntimeError, ValueError, any, dict, getattr, hasattr,
                      isinstance, iter, len, list, max, open, set, sorted, str, sum, tuple, type)
from copy import deepcopy
import hashlib
import json
import os
import re
from omfit_classes.omfit_gacode import OMFITcgyro
from OMFITlib_cgyro_checkpoint import select_checkpoint

STORE = 'RESULT_STORE'
REF = '__RESULT_REF__'
BRANCHES = ('RUN_DB', 'Cases', 'RUN_HISTORY', 'OUTPUTScan', 'RUN_INDEX')


def is_result(node):
    names = {base.__name__ for base in type(node).__mro__}
    # Derived diagnostic objects may carry extra in-memory state. Do not
    # collapse those merely because they originated from the same directory.
    return type(node).__name__ == 'OMFITcgyro' or ('OMFITlazyLoad' in names and getattr(node, 'cls', '') == 'OMFITcgyro')


def _file_node(node):
    # OMFITtree also has .filename (usually ''). It must remain traversable;
    # only native file readers are opaque leaves in the index scaffolding.
    names = {base.__name__ for base in type(node).__mro__}
    return 'OMFITobject' in names or 'OMFITlazyLoad' in names


def reference_id(node):
    if _file_node(node) or not hasattr(node, 'items') or REF not in node:
        return None
    key = node[REF]
    if len(node) != 1 or not isinstance(key, str) or re.fullmatch(r'[0-9a-f]{64}', key) is None:
        raise ValueError('Invalid CGYRO result reference')
    return key


def resolve_result(module, node):
    """Accept both the former native object and the new on-disk index."""
    key = reference_id(node)
    if key is None:
        return node
    result = module.get(STORE, {}).get(key, None)
    if result is None or not is_result(result):
        raise ValueError('Missing physical CGYRO result: ' + key)
    return result


def result_view(module, node):
    """Return plain runtime scaffolding; never attach this view to the tree."""
    key = reference_id(node)
    if key is not None:
        return resolve_result(module, node)
    if _file_node(node) or not hasattr(node, 'items'):
        return node
    return {key: result_view(module, value) for key, value in node.items()}


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
    old = reference_id(result)
    if old is not None:
        resolve_result(module, result)
        return _reference(old, factory)
    if not is_result(result):
        raise ValueError('Only native CGYRO output objects enter result storage')
    pool = module.get(STORE, {})
    for key in pool:
        if pool[key] is result:
            return _reference(key, factory)
    files, checkpoint = archive_inventory(result.filename)
    key = content_key(files)
    pool = module.setdefault(STORE, factory())
    if key not in pool:
        pool[key] = _physical_copy(result, files)
    if not is_result(pool[key]):
        raise ValueError('Invalid physical CGYRO result: ' + key)
    state = module.setdefault('RESULT_STORAGE', factory())
    state.update(dict(version=2, checkpoint_policy=1))
    state.setdefault('bytes', factory())[key] = sum(row[1] for row in files)
    state.setdefault('checkpoints', factory())[key] = json.dumps(checkpoint, sort_keys=True)
    return _reference(key, factory)


def compact_storage(module, factory=dict):
    """Plan all replacements before committing; retain every unique result.

    In particular, partial/unpublished history is not a disposable cache. It
    receives the same references as published scans and remains restartable.
    No solver directory or prior project ZIP is deleted by this operation.
    """
    pool = module.get(STORE, {})
    previous_state = module.get('RESULT_STORAGE', {})
    sizes = dict(previous_state.get('bytes', {}))
    checkpoints = dict(previous_state.get('checkpoints', {}))
    additions, plans, paths, remapped = {}, {}, {}, {}
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
            remapped[old] = plan_result(node)

    def convert(node):
        nonlocal raw_bytes, raw_copies
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
        result = factory()
        for key, value in node.items():
            result[key] = convert(value)
        return result

    # Fast path: indexed projects need no directory reads on every queue update.
    def has_raw(node):
        if is_result(node):
            return True
        key = reference_id(node)
        if key is not None:
            return key in remapped
        if _file_node(node) or not hasattr(node, 'items'):
            return False
        return any(has_raw(value) for value in node.values())

    for branch in BRANCHES:
        if branch in module and has_raw(module[branch]):
            plans[branch] = convert(module[branch])
    original = {branch: module[branch] for branch in plans}
    previous_sizes = module.get('RESULT_STORAGE', None)
    created_pool = STORE not in module
    target = module.setdefault(STORE, factory())
    try:
        for key, value in additions.items():
            target[key] = value
        for branch, replacement in plans.items():
            module[branch] = replacement
        state = factory()
        state.update(dict(version=2, checkpoint_policy=1, bytes=sizes, checkpoints=checkpoints))
        module['RESULT_STORAGE'] = state
    except BaseException:
        for branch, value in original.items():
            module[branch] = value
        for key in additions:
            target.pop(key, None)
        if created_pool:
            module.pop(STORE, None)
        if previous_sizes is None:
            module.pop('RESULT_STORAGE', None)
        else:
            module['RESULT_STORAGE'] = previous_sizes
        raise
    reports = [json.loads(value) for key, value in checkpoints.items() if key in target]
    return dict(converted_copies=raw_copies, physical_results=len(target),
                duplicate_bytes=max(0, raw_bytes - sum(sizes[key] for key in additions)),
                physical_bytes=sum(sizes.get(key, 0) for key in target),
                checkpoint_warnings=sum(1 for report in reports if report.get('warning', '')),
                backup_checkpoints=sum(1 for report in reports if report.get('selected', '') == 'bin.cgyro.restart.old'))


def prune_storage(module):
    """Drop unreachable pool entries from the saved tree, never delete files."""
    pool = module.get(STORE, {})
    used = set()

    def visit(node):
        key = reference_id(node)
        if key is not None:
            if key not in pool or not is_result(pool[key]):
                raise ValueError('Missing physical CGYRO result: ' + key)
            used.add(key)
        elif not _file_node(node) and hasattr(node, 'items'):
            for value in node.values():
                visit(value)

    for key, value in module.items():
        if key not in (STORE, 'RESULT_STORAGE'):
            visit(value)
    stale = [key for key in pool if key not in used]
    sizes = module.get('RESULT_STORAGE', {}).get('bytes', {})
    checkpoints = module.get('RESULT_STORAGE', {}).get('checkpoints', {})
    for key in stale:
        del pool[key]
        sizes.pop(key, None)
        checkpoints.pop(key, None)
    return len(stale)
