"""Small, reversible metadata transactions shared by explicit cleanup actions.

Keep physical owners alive until the entire commit returns. An OMFIT Abort
can arrive after the garbage collector returns, not only inside its loop.
These helpers remove tree references; they never unlink a solver directory.
"""
from builtins import BaseException, dict, id, object, reversed, str, type
from OMFITlib_cgyro_db import DELETED_TASKS, metadata_value, result_pool, rollback_actions, storage_state
from OMFITlib_cgyro_storage_files import FILE_STORE

DELETE = object()  # An in-memory instruction, never persisted in a project.


def deletion_markers(module, tokens):
    markers = dict(metadata_value(storage_state(module).get(DELETED_TASKS, {})))
    markers.update(dict((token, True) for token in tokens))
    return markers


def pool_journal(module):
    pool, state = result_pool(module), storage_state(module)
    mappings = [pool, pool.get(FILE_STORE, {})]
    mappings.extend(state.get(key, {}) for key in ('bytes', 'checkpoints', 'file_bytes'))
    return [(mapping, dict(mapping.items())) for mapping in mappings]


def restore_pool(mapping, original):
    for key, value in original.items():
        if key not in mapping:
            mapping[key] = value


def _native_scaffolding(value, factory, memo):
    """Convert only newly planned dictionaries; retain native owners as-is.

    Run this inside the journal, not while preparing a preview: native tree
    assignment reparents objects. Memoization keeps the compatibility header
    and its per-scan index referring to the same metadata container.
    """
    if factory is dict or type(value) is not dict:
        return value
    if id(value) in memo:
        return memo[id(value)]
    result = factory()
    memo[id(value)] = result
    for key, child in value.items():
        result[key] = _native_scaffolding(child, factory, memo)
    return result


def commit_cleanup(module, writes, prune, factory=dict):
    """Journal before each native write, including one that mutates then fails.

    The caller builds replacement containers off-tree and validates the last
    preview before entering here. No UI/event-loop calls belong in this region.
    Rollback restores owners first so restored public references remain valid.
    """
    missing, journal = object(), []
    owners = pool_journal(module) if prune is not None else []
    try:
        for mapping, key, value in writes:
            journal.append((mapping, key, mapping.get(key, missing)))
            if value is DELETE:
                mapping.pop(key)
            else:
                mapping[key] = _native_scaffolding(value, factory, {})
        if prune is not None:
            prune(module)
    except BaseException as error:
        def restore(mapping, key, old):
            if old is missing:
                mapping.pop(key, None)
            else:
                mapping[key] = old
        rollback_actions(error,
            [('cleanup owner pool', lambda m=m, v=v: restore_pool(m, v)) for m, v in owners] +
            [('cleanup ' + str(k), lambda m=m, k=k, v=v: restore(m, k, v))
             for m, k, v in reversed(journal)])
        raise
