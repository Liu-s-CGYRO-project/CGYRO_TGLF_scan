"""RUN_DB is the sole persistent owner of CGYRO results and restart inputs.

Public runs retain their existing run/case/scan paths. Reserved children hold
physical owners, unfinished runs and preserved legacy data. Job history outside
RUN_DB contains metadata only. Readers never fall back to an external result
branch; migration is an explicit preparation/compaction operation.
"""
from builtins import (BaseException, ValueError, all, any, bool, dict, float, getattr, hasattr, int, isinstance, len,
                      list, max, object, set, str, tuple, type, zip)
from copy import deepcopy
from OMFITlib_cgyro_reference import REF, is_native_file, make_reference, metadata_value, validate_reference

POOL, STATE, RUNS = '__STORE__', '__STORAGE__', '__RUNS__'
STORAGE_SCHEMA_VERSION = 4  # Direct radius scans; BASE is only a fixed reference.
PENDING, LEGACY = '__UNCLASSIFIED__', '__LEGACY__'
DELETED_TASKS = 'deleted_tasks'  # Tokens only; no job history or result snapshots.
OLD_BRANCHES = ('RESULT_STORE', 'RESULT_STORAGE', 'Cases', 'OUTPUTScan', 'OUTPUTS',
                'LEGACY_UNCLASSIFIED', 'RUN_INDEX', '_PLOT_CACHE')
_MISSING = object()


def rollback_actions(original_error, actions):
    """Try every restoration without hiding the error that interrupted commit.

    Native tree assignment can fail even while restoring a journal. Retain
    secondary diagnostics on the original exception, so callers still handle
    an Abort as an Abort and can report any incomplete restoration separately.
    Returning errors also lets owner transactions avoid deleting payloads when
    a public reference could not be rolled back.
    """
    errors = []
    for label, restore in actions:
        try:
            restore()
        except BaseException as rollback_error:
            errors.append(str(label) + ': ' + str(rollback_error))
    if errors:
        try:
            original_error.cgyro_rollback_errors = list(getattr(original_error, 'cgyro_rollback_errors', [])) + errors
        except BaseException:
            pass
    return errors


def _mapping(node):
    node = metadata_value(node)
    if not hasattr(node, 'items'):
        raise ValueError('CGYRO archive metadata is not a mapping; original data retained')
    return node


def _tree(mapping, factory):
    # Plan with plain mappings: native assignment reparents file owners, so
    # constructing a native tree here would mutate the live tree before commit.
    return dict(_mapping(mapping).items())


def _native(value, factory):
    value = metadata_value(value)
    if is_native_file(value):
        return value
    if hasattr(value, 'items'):
        if REF in value:
            digest = metadata_value(value[REF])
            validate_reference(value, digest)
            return make_reference(digest, factory)
        if not _has_payload(value):
            # Job metadata may legitimately use full paths as dictionary keys.
            # Keep its original mapping types instead of forcing native trees.
            return deepcopy(value)
        node = factory()
        for key, child in value.items():
            node[key] = _native(child, factory)
        return node
    if isinstance(value, (list, tuple)):
        values = [_native(child, factory) for child in value]
        return tuple(values) if isinstance(value, tuple) else values
    return value


def _rebind(value):
    if not is_native_file(value) and hasattr(value, 'items'):
        if REF in value:
            return  # Native assignment binds the index; data is not an owner.
        for key, child in list(value.items()):
            value[key] = child
            _rebind(child)


def _has_payload(value):
    value = metadata_value(value)
    if is_native_file(value):
        return True
    if hasattr(value, 'items'):
        if '__RESULT_REF__' in value or '__FILE_REF__' in value:
            return True
        return any(_has_payload(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_payload(child) for child in value)
    return False


def _history_has_payload(entry, audit):
    entry = _mapping(entry)
    if 'cases' in entry:
        return True
    if audit:
        return _has_payload(entry)
    # A current-schema history entry is metadata. Check direct legacy owners
    # without walking every old manifest's point_table on each scoped update.
    for value in [entry] + list(entry.values()):
        value = metadata_value(value)
        if is_native_file(value) or (hasattr(value, 'items') and
                ('__RESULT_REF__' in value or '__FILE_REF__' in value)):
            return True
    return False


def _retain(mapping, key, value):
    """Never overwrite an uncertain legacy source during consolidation."""
    key = str(key).replace('/', '%2F')
    original, number = key, 1
    while key in mapping:
        number += 1
        key = original + ' [' + str(number) + ']'
    mapping[key] = value


def _same_snapshot(first, second):
    """Prove metadata/index equality without loading or comparing file arrays.

    Separate native readers are intentionally uncertain: old files may contain
    unsaved edits. Such conflicts must be resolved before migration can choose
    one snapshot. Literal owner references can safely compare their digests.
    """
    first, second = metadata_value(first), metadata_value(second)
    if first is second:
        return True
    if is_native_file(first) or is_native_file(second):
        return False
    if hasattr(first, 'items') and hasattr(second, 'items'):
        if REF in first or REF in second:
            return (REF in first and REF in second and
                    validate_reference(first, metadata_value(first[REF])) ==
                    validate_reference(second, metadata_value(second[REF])))
        return set(first) == set(second) and all(_same_snapshot(first[key], second[key]) for key in first)
    if isinstance(first, (list, tuple)) and isinstance(second, (list, tuple)):
        return len(first) == len(second) and all(_same_snapshot(a, b) for a, b in zip(first, second))
    return type(first) is type(second) and isinstance(first, (str, int, float, bool)) and first == second


def _set_migrated_cases(record, cases, token):
    if 'cases' in record and not _same_snapshot(record['cases'], cases):
        raise ValueError('Conflicting CGYRO case snapshots for run ' + str(token) +
                         '; original RUN_DB, history and Cases are preserved')
    record['cases'] = cases


def ensure_layout(module, factory=dict, *, audit_history=False):
    """Move old owners under RUN_DB, with a journal for Abort/error rollback.

    No result is classified or discarded here. In particular, old unclassified
    cases and unsupported outputs remain inside RUN_DB until independently
    validated. Moving native owners avoids copying their physical directories.
    Current metadata needs only shallow checks; explicit full maintenance audits
    nested history fields before reclaiming any unreferenced owners.
    """
    prior_db = module.get('RUN_DB', _MISSING)
    db = factory() if prior_db is _MISSING else _mapping(prior_db)
    old_history = module.get('RUN_HISTORY', _MISSING)
    history = {} if old_history is _MISSING else _mapping(old_history)
    current_state = metadata_value(db.get(STATE, {}))
    old_layout = (any(key in module for key in OLD_BRANCHES) or
                  current_state.get('version', 0) < STORAGE_SCHEMA_VERSION)
    has_cases = any(_history_has_payload(entry, audit_history or old_layout) for entry in history.values())
    if not old_layout and not has_cases:
        if prior_db is _MISSING:
            module['RUN_DB'] = db
        return db

    original = {key: module[key] for key in OLD_BRANCHES if key in module}
    state = _tree(current_state, factory)
    state['version'] = max(STORAGE_SCHEMA_VERSION, state.get('version', 0))
    plan = {STATE: state}
    if 'RESULT_STORE' in original:
        owners = _tree(db.get(POOL, {}), factory)
        for key, value in _mapping(original['RESULT_STORE']).items():
            if key in owners and owners[key] is not value:
                raise ValueError('Two CGYRO result pools overlap; original owners retained: ' + str(key))
            owners[key] = value
        plan[POOL] = owners
    if 'RESULT_STORAGE' in original:
        state.update(dict(_mapping(original['RESULT_STORAGE']).items()))
        state['version'] = max(STORAGE_SCHEMA_VERSION, state.get('version', 0))
        plan[STATE] = state
    if 'LEGACY_UNCLASSIFIED' in original:
        pending = _tree(db.get(PENDING, {}), factory)
        for key, value in _mapping(original['LEGACY_UNCLASSIFIED']).items():
            _retain(pending, key, value)
        plan[PENDING] = pending

    legacy = _tree(db.get(LEGACY, {}), factory)
    for key in ('OUTPUTScan', 'OUTPUTS', 'RUN_INDEX', '_PLOT_CACHE'):
        if key in original and original[key]:
            _retain(legacy, key, original[key])
    records = _tree(db.get(RUNS, {}), factory)
    cleaned_history = {}
    for token, source in history.items():
        source = _mapping(source)
        clean = _tree(source, factory)
        record = _tree(records.get(str(token), {}), factory)
        record.setdefault('manifest', deepcopy(source.get('manifest', {})))
        records[str(token)] = record
        if 'cases' in source:
            _set_migrated_cases(record, source['cases'], token)
            record['manifest'] = deepcopy(source.get('manifest', {}))
            records[str(token)] = record
            clean.pop('cases', None)
        extras = {key: value for key, value in clean.items() if key != 'manifest' and _has_payload(value)}
        if extras:
            record = _tree(records.get(str(token), {}), factory)
            retained = _tree(record.get('legacy_fields', {}), factory)
            retained.update(extras)
            record['legacy_fields'] = retained
            record.setdefault('manifest', deepcopy(source.get('manifest', {})))
            records[str(token)] = record
            for key in extras:
                clean.pop(key)
        cleaned_history[token] = clean
    current = module.get('RUN_MANIFEST', {})
    if current.get('run_token', ''):
        token = str(current['run_token'])
        record = _tree(records.get(token, {}), factory)
        record['manifest'] = deepcopy(current)
        records[token] = record
    if 'Cases' in original:
        old_cases = _mapping(original['Cases'])
        token, tag = str(current.get('run_token', '')), current.get('case_tag', '')
        for key, value in old_cases.items():
            if token and key == tag:
                record = _tree(records.get(token, {}), factory)
                _set_migrated_cases(record, value, token)
                record['manifest'] = deepcopy(current)
                records[token] = record
            else:
                unmatched = _tree(legacy.get('Cases', {}), factory)
                _retain(unmatched, key, value)
                legacy['Cases'] = unmatched
    if legacy:
        plan[LEGACY] = legacy
    if records:
        plan[RUNS] = records
    previous = {key: db.get(key, _MISSING) for key in plan}
    try:
        module['RUN_DB'] = db
        for key, value in plan.items():
            db[key] = _native(value, factory)
        if has_cases:
            module['RUN_HISTORY'] = _native(cleaned_history, factory)
        for key in original:
            module.pop(key, None)
    except BaseException as original_error:
        # Restore the original owners *before* removing migrated branches. If
        # a source restoration is rejected, the new RUN_DB is its remaining
        # recovery location and must stay reachable despite the failed commit.
        actions = []
        if old_history is not _MISSING:
            actions.append(('RUN_HISTORY', lambda: module.__setitem__('RUN_HISTORY', old_history)))
        actions.extend((key, lambda key=key, value=value: module.__setitem__(key, value))
                       for key, value in original.items())
        errors = rollback_actions(original_error, actions)
        if not errors:
            actions = [('RUN_DB/' + str(key),
                        (lambda key=key: db.pop(key, None)) if value is _MISSING else
                        (lambda key=key, value=value: db.__setitem__(key, value)))
                       for key, value in previous.items()]
            errors = rollback_actions(original_error, actions)
            if not errors:
                rollback_actions(original_error, [('RUN_DB',
                    (lambda: module.pop('RUN_DB', None)) if prior_db is _MISSING else
                    (lambda: module.__setitem__('RUN_DB', prior_db)))])
        # Rebinding is independent of restoring the enclosing branch: failure
        # on one native owner must not skip other trees or overwrite the Abort.
        actions = [('rebind ' + key, lambda value=value: _rebind(value))
                   for key, value in original.items()]
        actions.append(('rebind RUN_DB', lambda: _rebind(db)))
        rollback_actions(original_error, actions)
        raise
    return db


def result_pool(module, factory=None):
    db = ensure_layout(module, factory) if factory is not None else module.get('RUN_DB', {})
    return db.setdefault(POOL, factory()) if factory is not None else metadata_value(db.get(POOL, {}))


def storage_state(module, factory=None):
    db = ensure_layout(module, factory) if factory is not None else module.get('RUN_DB', {})
    return db.setdefault(STATE, factory()) if factory is not None else metadata_value(db.get(STATE, {}))


def run_is_deleted(module, token):
    """Block stale dialogs/finally handlers from recreating explicitly deleted runs.

    The token-only marker survives saving, but is not a task/result record and
    is never listed in the task manager. Verified, explicit job recovery may
    clear one marker; a cached GUI callback has no authority to do that.
    """
    return str(token) in metadata_value(storage_state(module).get(DELETED_TASKS, {}))


def run_records(module, factory=None):
    db = ensure_layout(module, factory) if factory is not None else module.get('RUN_DB', {})
    return db.setdefault(RUNS, factory()) if factory is not None else metadata_value(db.get(RUNS, {}))


def run_cases(module, manifest=None, factory=None):
    """Return one run's flat point map; never read Cases/RUN_HISTORY payloads."""
    manifest = module.get('RUN_MANIFEST', {}) if manifest is None else manifest
    token = str(manifest.get('run_token', ''))
    records = run_records(module, factory)
    if factory is not None:
        if not token:
            raise ValueError('A frozen run token is required before storing CGYRO points')
        return records.setdefault(token, factory()).setdefault('cases', factory())
    return metadata_value(records.get(token, {}).get('cases', {}))


def set_run_cases(module, manifest, cases, factory=dict):
    token = str(manifest.get('run_token', ''))
    if not token:
        raise ValueError('Missing frozen CGYRO run token')
    record = run_records(module, factory).setdefault(token, factory())
    record['cases'] = cases
    record['manifest'] = deepcopy(manifest)


def freeze_run_inputs(module, manifest, factory=dict):
    """Keep original ZIP references before a download replaces point entries."""
    token = str(manifest.get('run_token', ''))
    if not token:
        raise ValueError('Missing frozen CGYRO run token')
    record = run_records(module, factory).setdefault(token, factory())
    cases = run_cases(module, manifest, factory)
    inputs = record.setdefault('inputs', factory())
    for key, node in list(cases.items()):
        node = metadata_value(node)
        if is_native_file(node):
            if str(key).endswith(('.pbs', '.sh')) and key not in inputs:
                # Native assignment can fail or receive Abort. Install the new
                # owner before removing the old link, so either interruption
                # leaves the original submission script available for retry.
                inputs[key] = cases[key]
                cases.pop(key)
        elif hasattr(node, 'get') and 'zip' in node and key not in inputs:
            frozen = factory()
            frozen['zip'] = deepcopy(node['zip'])
            inputs[key] = frozen


def legacy_branch(module, name):
    return module.get('RUN_DB', {}).get(LEGACY, {}).get(name, {})


def legacy_outputs(module, factory=None):
    """Compatibility for nonlinear tools; their owners also live in RUN_DB."""
    if factory is None:
        return legacy_branch(module, 'OUTPUTS')
    db = ensure_layout(module, factory)
    outputs = db.setdefault(LEGACY, factory()).setdefault('OUTPUTS', factory())
    outputs.setdefault('NonLinear', factory())
    return outputs


def legacy_case_root(module, factory=None):
    if factory is None:
        return legacy_branch(module, 'Cases')
    return ensure_layout(module, factory).setdefault(LEGACY, factory()).setdefault('Cases', factory())
