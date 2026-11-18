"""Retention of operation logs, separate from input backups and result owners.

Only known final metadata records are disposable. Legacy/unknown payloads,
pending operations and backups may be the only retained copy; never traverse
their values or remove them as part of automatic log retention.
"""
from builtins import ValueError, dict, getattr, id, len, list, max, object, set, str
from contextlib import contextmanager

LOG_LIMIT = 100
ERROR_LOG_LIMIT = 20
DISPLAY_LIMIT = 20
FINAL = {'returned', 'complete', 'failed', 'cancelled', 'ready', 'archived', 'inputs_copied'}
LOG_FIELDS = {'id', 'title', 'created', 'status', 'error', 'destinations', 'modules', 'removed_run_ids'}

# Native OMFIT can reload library namespaces between nested GUI callbacks.
# Keep live actions on their project; SortedDict omits _OMFIT* attributes
# from saved state. Plain mapping adapters share this temporary registry.
_adapter_operations = {}


def _operation_slot(root):
    attributes = getattr(root, '__dict__', None)
    if attributes is None:
        return _adapter_operations, id(root)
    return attributes, '_OMFIT_workbench_operations'


def live_operations(root):
    storage, key = _operation_slot(root)
    return list(storage.get(key, {}).values())


@contextmanager
def running_operation(root, title):
    storage, key = _operation_slot(root)
    operations = storage.setdefault(key, {})
    marker = object()
    operations[marker] = title
    try:
        yield
    finally:
        del operations[marker]
        if not operations:
            del storage[key]


def record_kind(record):
    keys = set(record.keys())
    if record.get('status', '') not in FINAL:
        return 'retained'
    if keys <= LOG_FIELDS:
        return 'log'
    if keys <= LOG_FIELDS | {'previous_inputs'}:
        return 'input_backup'
    return 'retained'


def history_counts(records):
    counts = dict(log=0, input_backup=0, retained=0)
    for record in records.values():
        counts[record_kind(record)] += 1
    return counts


def trim_logs(records, normal_limit=LOG_LIMIT, error_limit=ERROR_LOG_LIMIT):
    """Run on explicit action writes, never from rendering or project load."""
    normal, errors = [], []
    for key, record in records.items():
        if record_kind(record) == 'log':
            (errors if record.get('status', '') in ('failed', 'cancelled') else normal).append(key)
    # The browser may explicitly sort a tree. UUID suffix order is not time
    # order; use the recorded UTC microseconds, with stable ordering for ties.
    for keys in (normal, errors):
        keys.sort(key=lambda key: str(records[key].get('created', key)))
    removed = normal[:max(0, len(normal) - normal_limit)] + errors[:max(0, len(errors) - error_limit)]
    for key in removed:
        del records[key]
    return len(removed)


def clear_history(records, kind):
    """Explicit cleanup of pure logs OR pure input backups; no disk deletion."""
    if kind not in ('log', 'input_backup'):
        raise ValueError('Choose operation logs or input backups.')
    removed = [key for key, record in records.items() if record_kind(record) == kind]
    for key in removed:
        del records[key]
    return len(removed)
