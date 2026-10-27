"""Metadata-only identities for explicit CGYRO task management.

A run_token owns one immutable submission and its automatic retry attempts.
Continuations have new tokens. Scheduler numbers alone are not global IDs:
different clusters can reuse them, and p000001 is local to each submission.
"""
from builtins import (TypeError, ValueError, any, bool, dict, enumerate, hasattr, id, isinstance,
                      len, list, set, sorted, str, tuple, type)
import hashlib
import json
from OMFITlib_cgyro_archive import canonical_case_key, case_scans, case_sources, clean_run_id, scan_key
from OMFITlib_cgyro_db import PENDING, run_is_deleted, run_records
from OMFITlib_cgyro_reference import REF, is_native_file, metadata_value
from OMFITlib_cgyro_result_index import _public_headers, at

BUSY_STATES = ('preparing', 'uploading', 'submitting', 'running', 'cancel_requested')


def mapping(value):
    value = metadata_value(value)
    return value if not is_native_file(value) and hasattr(value, 'items') else {}


def manifest_sources(module, tokens=None):
    """Include parked/unarchived tasks, independently of the current queue focus."""
    sources = []
    for label, entries in (('history', module.get('RUN_HISTORY', {})), ('retained', run_records(module))):
        entries = mapping(entries)
        selected = entries.items() if tokens is None else ((token, entries[token]) for token in tokens if token in entries)
        for token, entry in selected:
            manifest = mapping(mapping(entry).get('manifest', {}))
            if manifest:
                sources.append((str(token), manifest, label))
    current = mapping(module.get('RUN_MANIFEST', {}))
    if current.get('run_token', '') and (tokens is None or str(current['run_token']) in tokens):
        sources.append((str(current['run_token']), current, 'current'))
    return sources


def indexed_sources(module, tokens=None):
    """Yield actual storage paths, never writable synthetic case views."""
    if tokens is not None:
        seen = set()
        for info in _public_headers(module).values():
            linked = set(info.get('merged_run_tokens', [])) | {info.get('run_token', '')}
            path = tuple(info['destination'])
            if linked & set(tokens) and path not in seen:
                seen.add(path)
                yield path, info['case_id'], at(module['RUN_DB'], path)
        return
    db = mapping(module.get('RUN_DB', {}))
    for runid, cases in case_sources(module).items():
        for case_id, case, path in cases:
            if mapping(case):
                yield (str(runid),) + tuple(path), case_id, case
    for key, case in mapping(db.get(PENDING, {})).items():
        if mapping(case):
            yield (PENDING, key), '', case


def row_token(row, info):
    explicit = str(mapping(row).get('run_token', '') or '')
    if explicit:
        return explicit
    merged = set(str(t) for t in info.get('merged_run_tokens', []) if t)
    # Old single-source archives had no per-point token. A merged header is
    # insufficient evidence: guessing would remove another job's ky points.
    return str(info.get('run_token', '') or '') if len(merged) <= 1 else ''


def task_jobs(manifest):
    return sorted({str(m.get('job_id', '')) for m in [manifest] + list(manifest.get('attempts', []))
                   if mapping(m).get('job_id', '')})


def task_catalog(module, include_results=True, tokens=None):
    """Build unsaved rows only on opening/refreshing the task manager."""
    found = {}
    def remember(token, manifest):
        if not token or tokens is not None and token not in tokens or run_is_deleted(module, token):
            return None
        row = found.setdefault(token, dict(token=token, jobs=set(), servers=set(), runids=set(), cases=set(),
            scans=set(), statuses=set(), archived_points=0, retained_points=0, has_inputs=False, busy=False))
        row['jobs'].update(task_jobs(manifest))
        for field, value in (('servers', manifest.get('server', '')), ('runids', clean_run_id(manifest.get('runid', ''))),
                             ('cases', canonical_case_key(manifest.get('case_id', ''), manifest)),
                             ('scans', scan_key(manifest))):
            if value:
                row[field].add(str(value))
        row['statuses'].add(str(manifest.get('status', '') or 'unknown'))
        row['busy'] |= manifest.get('status', '') in BUSY_STATES or manifest.get('collection_status', '') == 'collecting'
        return row
    for token, manifest, _ in manifest_sources(module, tokens):
        row = remember(token, manifest)
        if row is not None:
            record = mapping(run_records(module).get(token, {}))
            row['retained_points'] = len(mapping(record.get('cases', {})))
            row['has_inputs'] = bool(record.get('inputs', {}))
    if include_results and tokens is None:
        for info in _public_headers(module).values():
            header = str(info.get('run_token', '') or '')
            counts = info.get('task_counts', {})
            linked = set(info.get('merged_run_tokens', [])) | {header}
            for token in linked:
                row = remember(token, info if token == header else dict(runid=info['runid'], case_id=info['case_id']))
                if row is not None:
                    count = counts.get(token, info.get('points', 0) if len(linked) == 1 else None)
                    row['archived_points'] = (None if count is None or row['archived_points'] is None
                                              else row['archived_points'] + count)
                    row['scans'].add(scan_key(info))
    for path, case_id, case in (indexed_sources(module, tokens) if include_results and tokens is not None else ()):
        for name, info, tasks in case_scans(case):
            header = str(info.get('run_token', '') or '')
            remember(header, info)
            for source in tasks.values():
                token = row_token(source, info)
                # A merged header describes its own job only. Never assign its
                # scheduler ID to another token's retained numeric point.
                row = remember(token, info if token == header else mapping(source))
                if row is not None:
                    row['archived_points'] += 1
                    if path[0] != PENDING:
                        row['runids'].add(clean_run_id(path[0]))
                    if case_id:
                        row['cases'].add(canonical_case_key(case_id, info))
                    row['scans'].add(scan_key(info, name))
    batch = mapping(module.get('RUN_BATCH', {}))
    for row in found.values():
        row['busy'] |= row['token'] in batch.get('tokens', []) and batch.get('status', '') in BUSY_STATES
        for field in ('jobs', 'servers', 'runids', 'cases', 'scans', 'statuses'):
            row[field] = sorted(row[field])
    return sorted(found.values(), key=lambda row: (row['servers'], row['runids'], row['jobs'], row['token']))


def metadata_revision(module, tokens=None, case_paths=()):
    """Bind confirmation to live indexes, not just a count or list of tokens.

    A modal Tk confirmation processes events: a download or queue update may
    finish while it is open. Hash metadata and reference identities again at
    commit. Opaque result readers/arrays are never evaluated or serialized.
    """
    digest, active = hashlib.sha256(), set()
    def visit(value):
        value = metadata_value(value)
        if is_native_file(value):
            digest.update(('owner:' + str(id(value))).encode('ascii'))
        elif hasattr(value, 'items'):
            if REF in value:
                visit(str(value[REF]))
                return
            if id(value) in active:
                raise ValueError('Cyclic task metadata; cleanup is unsafe.')
            active.add(id(value))
            digest.update(b'{')
            for key in sorted(value, key=lambda k: (str(type(k)), str(k))):
                visit(str(type(key)) + ':' + str(key))
                visit(value[key])
            digest.update(b'}')
            active.remove(id(value))
        elif isinstance(value, (list, tuple)):
            if id(value) in active:
                raise ValueError('Cyclic task metadata; cleanup is unsafe.')
            active.add(id(value))
            digest.update(b'[')
            for child in value:
                visit(child)
            digest.update(b']')
            active.remove(id(value))
        else:
            # JSON scalars are length-delimited by their encoding. Unknown
            # objects (e.g. an old loaded array) remain opaque runtime identities.
            try:
                encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError):
                encoded = str(type(value)) + ':' + str(id(value))
            digest.update(encoded.encode('utf-8'))
            digest.update(b';')
    if tokens is not None:
        # A task-only deletion binds exactly its records. It need not open or
        # hash any unrelated result indexes or the physical owner catalog.
        for token, manifest, label in manifest_sources(module, tokens):
            visit((token, label, manifest))
        for token in sorted(tokens):
            visit(run_records(module).get(token, {}))
        visit(module.get('RUN_BATCH', {}))
        for path in case_paths:
            node = module.get('RUN_DB', {})
            for key in path:
                node = node[key]
            visit((path, node))
        return digest.hexdigest()
    for name in ('RUN_DB', 'RUN_HISTORY', 'RUN_MANIFEST', 'RUN_BATCH'):
        visit(name)
        visit(module.get(name, {}))
    return digest.hexdigest()
