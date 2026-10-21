"""RUN_DB is the sole persistent owner of CGYRO results and restart inputs.

Public runs retain their existing run/case/scan paths. Reserved children hold
physical owners, unfinished runs and preserved legacy data. Job history outside
RUN_DB contains metadata only. Readers never fall back to an external result
branch; migration is an explicit preparation/compaction operation.
"""
from builtins import (ValueError, any, dict, getattr, hasattr, isinstance, len,
                      list, object, set, str, tuple, type, vars)
from copy import deepcopy

POOL, STATE, RUNS = '__STORE__', '__STORAGE__', '__RUNS__'
PENDING, LEGACY = '__UNCLASSIFIED__', '__LEGACY__'
OLD_BRANCHES = ('RESULT_STORE', 'RESULT_STORAGE', 'Cases', 'OUTPUTScan', 'OUTPUTS',
                'LEGACY_UNCLASSIFIED', 'RUN_INDEX', '_PLOT_CACHE')
_MISSING = object()


def metadata_value(node):
    """Materialize persisted metadata containers, retaining lazy file readers."""
    if any(base.__name__ == 'OMFITlazyLoad' for base in type(node).__mro__):
        attributes = vars(node)
        kind = attributes.get('tp', attributes.get('cls', ''))
        if kind in ('OMFITpickle', 'OMFITtree', 'OMFITmodule', 'SortedDict', 'OMFITlist'):
            return node.__lazy_load__()
    return node


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
    if any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(value).__mro__):
        return value
    if hasattr(value, 'items'):
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
    if hasattr(value, 'items') and not any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(value).__mro__):
        for key, child in list(value.items()):
            value[key] = child
            _rebind(child)


def _has_payload(value):
    value = metadata_value(value)
    if any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(value).__mro__):
        return True
    if hasattr(value, 'items'):
        if '__RESULT_REF__' in value or '__FILE_REF__' in value:
            return True
        return any(_has_payload(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_payload(child) for child in value)
    return False


def _retain(mapping, key, value):
    """Never overwrite an uncertain legacy source during consolidation."""
    key = str(key).replace('/', '%2F')
    original, number = key, 1
    while key in mapping:
        number += 1
        key = original + ' [' + str(number) + ']'
    mapping[key] = value


def ensure_layout(module, factory=dict):
    """Move old owners under RUN_DB, with a journal for Abort/error rollback.

    No result is classified or discarded here. In particular, old unclassified
    cases and unsupported outputs remain inside RUN_DB until independently
    validated. Moving native owners avoids copying their physical directories.
    """
    prior_db = module.get('RUN_DB', _MISSING)
    db = factory() if prior_db is _MISSING else _mapping(prior_db)
    old_history = module.get('RUN_HISTORY', _MISSING)
    history = {} if old_history is _MISSING else _mapping(old_history)
    has_cases = any('cases' in _mapping(entry) or _has_payload(entry) for entry in history.values())
    current_state = metadata_value(db.get(STATE, {}))
    if not any(key in module for key in OLD_BRANCHES) and not has_cases and current_state.get('version', 0) >= 4:
        if prior_db is _MISSING:
            module['RUN_DB'] = db
        return db

    original = {key: module[key] for key in OLD_BRANCHES if key in module}
    state = _tree(current_state, factory)
    state['version'] = 4
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
        state['version'] = 4
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
            record['cases'] = source['cases']
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
                record['cases'], record['manifest'] = value, deepcopy(current)
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
    except BaseException:
        for key, value in previous.items():
            if value is _MISSING:
                db.pop(key, None)
            else:
                db[key] = value
        if prior_db is _MISSING:
            module.pop('RUN_DB', None)
        else:
            module['RUN_DB'] = prior_db
        if old_history is not _MISSING:
            module['RUN_HISTORY'] = old_history
        for key, value in original.items():
            module[key] = value
            _rebind(value)
        _rebind(db)
        raise
    return db


def result_pool(module, factory=None):
    db = ensure_layout(module, factory) if factory is not None else module.get('RUN_DB', {})
    return db.setdefault(POOL, factory()) if factory is not None else metadata_value(db.get(POOL, {}))


def storage_state(module, factory=None):
    db = ensure_layout(module, factory) if factory is not None else module.get('RUN_DB', {})
    return db.setdefault(STATE, factory()) if factory is not None else metadata_value(db.get(STATE, {}))


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
    record = run_records(module, factory).setdefault(token, factory())
    cases = run_cases(module, manifest, factory)
    inputs = record.setdefault('inputs', factory())
    for key, node in list(cases.items()):
        node = metadata_value(node)
        if any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(node).__mro__):
            if str(key).endswith(('.pbs', '.sh')) and key not in inputs:
                inputs[key] = cases.pop(key)
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
