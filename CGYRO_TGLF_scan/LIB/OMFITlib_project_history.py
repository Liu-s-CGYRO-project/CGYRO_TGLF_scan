"""Retention of operation logs, separate from input backups and result owners.

Only known final metadata records are disposable. Legacy/unknown payloads,
pending operations and backups may be the only retained copy; never traverse
their values or remove them as part of automatic log retention.
"""
from builtins import ValueError, dict, len, max, set

LOG_LIMIT = 100
ERROR_LOG_LIMIT = 20
DISPLAY_LIMIT = 20
FINAL = {'returned', 'complete', 'failed', 'cancelled', 'ready', 'archived', 'inputs_copied'}
LOG_FIELDS = {'id', 'title', 'created', 'status', 'error', 'destinations', 'modules', 'removed_run_ids'}


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
