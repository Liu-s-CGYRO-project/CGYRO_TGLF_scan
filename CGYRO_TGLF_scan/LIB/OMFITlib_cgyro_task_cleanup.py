"""Explicit task deletion, scoped by run_token rather than a scan directory.

Plan off-tree; delete only indexed points owned by selected submissions. A
same-coordinate replacement from a newer job belongs to that newer job. The
shared physical owner pool is reclaimed by explicit maintenance, separately
from record/result unlinking. Unknown legacy provenance is never guessed.
"""
from builtins import (ValueError, any, bool, dict, enumerate, float, isinstance, len, list,
                      set, sorted, str, sum, tuple)
from copy import deepcopy
import hashlib
from OMFITlib_cgyro_archive import (canonical_case_key, case_scans, clean_run_id, full_point_coordinate,
                                   point_coordinate, scan_branch, summarize_tasks)
from OMFITlib_cgyro_cleanup_state import DELETE, commit_cleanup, deletion_markers
from OMFITlib_cgyro_db import DELETED_TASKS, ensure_layout, run_records, storage_state
from OMFITlib_cgyro_task_catalog import (indexed_sources, manifest_sources, mapping,
                                        metadata_revision, row_token, task_catalog)


def _validate_selection(module, tokens, delete_results):
    if not isinstance(tokens, (list, tuple)) or not tokens or any(not isinstance(t, str) or not t for t in tokens):
        raise ValueError('请明确选择至少一条任务，不能以空选择删除全部任务。')
    selected = set(tokens)
    if len(selected) != len(tokens):
        raise ValueError('任务选择重复，请刷新列表。')
    catalog = {row['token']: row for row in task_catalog(module, include_results=delete_results, tokens=selected)}
    if selected - set(catalog):
        raise ValueError('所选任务已不存在，请刷新列表。')
    for token in selected:
        row = catalog[token]
        if row['busy']:
            raise ValueError('任务正在提交、运行流程或收集，请先结束本地操作：' + token)
        if any(len(row[field]) > 1 for field in ('servers', 'runids', 'cases')):
            raise ValueError('任务身份存在冲突，未删除任何数据：' + token)
    sources = manifest_sources(module, selected)
    for token, manifest, _ in sources:
        if token in selected and str(manifest.get('run_token', token)) != token:
            raise ValueError('任务记录与冻结清单身份不一致：' + token)
    return selected, [catalog[token] for token in sorted(selected)]


def _without_points(node, paths):
    """Copy just changed scaffolding; never deepcopy native file owners."""
    result = dict(mapping(node).items())
    grouped = {}
    for path in paths:
        if not path or path[0] not in result:
            raise ValueError('结果路径与任务索引不一致，原归档保留。')
        grouped.setdefault(path[0], []).append(path[1:])
    for key, children in grouped.items():
        if any(not child for child in children):
            if any(child for child in children):
                raise ValueError('结果路径存在重叠，原归档保留。')
            result.pop(key)
        else:
            child = _without_points(result[key], children)
            if child:
                result[key] = child
            else:
                result.pop(key)
    return result


def _retained_info(info, tasks, manifests):
    saved = deepcopy(dict(info))
    tokens = list(dict.fromkeys(row_token(row, info) for row in tasks.values()))
    anchor = str(info.get('run_token', ''))
    if anchor not in tokens:
        anchor = tokens[-1]
        source = manifests.get(anchor, {})
        # A public header must not keep pointing at a deleted frozen task.
        # Schema/coordinate fields stay with the scan, execution fields follow
        # a surviving source or are omitted when old provenance is incomplete.
        for key in ('job_id', 'server', 'workDir', 'runtime', 'retry_count', 'attempts', 'continuations',
                    'fixed_parameters', 'numeric_parameters', 'scale_time_with_ky', 'source_runid'):
            saved.pop(key, None)
            if key in source:
                saved[key] = deepcopy(source[key])
    saved.update(dict(run_token=anchor, merged_run_tokens=tokens, points=len(tasks),
        planned_points=list(tasks), point_workdirs={p: r['result_workDir'] for p, r in tasks.items()
                                                  if r.get('result_workDir', '')}))
    for key in ('continuation_pending',):
        saved[key] = {p: row[key] for p, row in tasks.items() if row.get(key, '')}
    saved['skipped_points'] = []
    for index, axis in enumerate(saved.get('scan_axes', [])):
        # Preserve linked-axis descriptions; only remove values whose entire
        # coordinate/ky slice disappeared with this task.
        values = {float(row['result_path'][index * 2 + 1]) for row in tasks.values()}
        axis['values'] = [v for v in axis.get('values', []) if float(v) in values]
    summarize_tasks(saved, tasks)
    return saved


def _rewrite_case(case, selected, manifests):
    records, result, removed, unknown = {}, dict(case.items()), [], 0
    for name, info, tasks in case_scans(case):
        linked = set(str(t) for t in info.get('merged_run_tokens', []) if t) | {str(info.get('run_token', ''))}
        unassigned = [p for p, row in tasks.items() if not row_token(row, info)]
        if selected & linked and unassigned:
            raise ValueError('混合归档缺少逐点任务身份，拒绝扩大删除范围：' + str(name))
        if selected & linked and not tasks:
            raise ValueError('归档缺少逐点索引，拒绝按任务猜测删除：' + str(name))
        unknown += len(unassigned)
        deleting = {p: row for p, row in tasks.items() if row_token(row, info) in selected}
        if deleting and unassigned:
            raise ValueError('混合归档缺少逐点任务身份，原归档保留：' + str(name))
        kept = {p: row for p, row in tasks.items() if p not in deleting}
        if deleting:
            paths = [list(row['result_path']) for row in deleting.values()]
            # Validate coordinates before path removal, including signed ky.
            coordinates = [full_point_coordinate(info, row) for row in tasks.values()]
            if len(set(coordinates)) != len(coordinates):
                raise ValueError('归档包含重复坐标，原归档保留：' + str(name))
            branch = scan_branch(case, info, tasks)
            if any(path[0] != branch for path in paths):
                raise ValueError('扫描索引与结果分支不一致，原归档保留。')
            result = _without_points(result, paths)
            if not kept and branch in result:
                raise ValueError('扫描含有未索引结果，拒绝删除整个参数分支：' + branch)
            removed.extend(str(p) for p in deleting)
        if kept:
            affected = bool(deleting) or str(info.get('run_token', '')) in selected
            records[name] = (dict(info=_retained_info(info, kept, manifests), tasks=kept) if affected else
                             dict(info=info, tasks=tasks))
    if not removed and not any(str(info.get('run_token', '')) in selected for _, info, _ in case_scans(case)):
        return None, [], unknown
    for key in ('__INFO__', '__SCANS__', '__TASKS__'):
        result.pop(key, None)
    if records:
        result['__SCANS__'] = records
        latest = list(records.values())[-1]
        result['__INFO__'], result['__TASKS__'] = latest['info'], latest['tasks']
    return result, removed, unknown


def _replace_path(node, path, replacement):
    """Replace one actual case path, preserving neighboring isotopes/scans."""
    result = dict(mapping(node).items())
    if not path or path[0] not in result:
        raise ValueError('归档路径发生变化，请刷新任务列表。')
    child = replacement if len(path) == 1 else _replace_path(result[path[0]], path[1:], replacement)
    if child:
        result[path[0]] = child
    else:
        result.pop(path[0])
    return result


def _batch_after(module, selected):
    batch = mapping(module.get('RUN_BATCH', {}))
    tokens = [t for t in batch.get('tokens', []) if t not in selected]
    if batch.get('focus_token', '') in selected or not tokens:
        return {}
    if len(tokens) == len(batch.get('tokens', [])):
        return None
    saved = deepcopy(dict(batch))
    saved['tokens'] = tokens
    saved['case_ids'] = [mapping(module.get('RUN_HISTORY', {}).get(t, {})).get('manifest', {}).get('case_id', t)
                         for t in tokens]
    saved['completed'] = [c for c in saved.get('completed', []) if c in saved['case_ids']]
    saved['errors'] = []
    return saved


def _plan(module, tokens, delete_results=False):
    selected, rows = _validate_selection(module, tokens, delete_results)
    manifests = {t: m for t, m, _ in manifest_sources(module, None if delete_results else selected)}
    db, replacements, archives = module.get('RUN_DB', {}), {}, []
    unknown = 0
    changed_paths = []
    for path, _, _ in (indexed_sources(module, selected) if delete_results else ()):
        # case_sources exposes a filtered view for direct radius scans. Start
        # from the actual node so replacing that scan cannot drop H/D/T beside it.
        case = replacements.get(path[0], db[path[0]])
        for part in path[1:]:
            case = mapping(case)[part]
        case = mapping(case)
        changed, points, unassigned = _rewrite_case(case, selected, manifests)
        unknown += unassigned
        if changed is not None:
            branch = replacements.get(path[0], db[path[0]])
            replacements[path[0]] = _replace_path(branch, path[1:], changed)
            archives.append(dict(path='/'.join(str(p) for p in path), points=len(points)))
            changed_paths.append(path)
    writes = [(db, key, value if value else DELETE) for key, value in replacements.items()]
    for entries in (module.get('RUN_HISTORY', {}), run_records(module)):
        writes.extend((entries, token, DELETE) for token in selected if token in entries)
    writes.append((storage_state(module), DELETED_TASKS, deletion_markers(module, selected)))
    current = mapping(module.get('RUN_MANIFEST', {}))
    if str(current.get('run_token', '')) in selected:
        writes.append((module, 'RUN_MANIFEST', {}))
    batch = _batch_after(module, selected)
    if batch is not None and module.get('RUN_BATCH', {}):
        writes.append((module, 'RUN_BATCH', batch))
    revision = metadata_revision(module, tokens=selected, case_paths=changed_paths)
    code = hashlib.sha256((revision + '\n' + '\n'.join(sorted(selected))).encode('utf-8')).hexdigest()[:8].upper()
    report = dict(tokens=sorted(selected), tasks=rows, archives=archives,
        delete_results=bool(delete_results),
        archived_points=sum(a['points'] for a in archives), unknown_points_preserved=unknown,
        revision=revision, confirmation='DELETE ' + code)
    return report, writes


def preview_tasks(module, tokens, delete_results=False):
    """No solver/file reads. Normalize old metadata before binding the preview."""
    ensure_layout(module)
    return _plan(module, tokens, delete_results)[0]


def remove_tasks(module, tokens, expected, confirmation, factory=dict):
    """Delete exactly the reviewed task group; never contact a scheduler.

    GUI callers must complete both dialogs and send the bound preview credential.
    Programmatic callers likewise need a fresh preview and explicit challenge.
    New retries/results/dependencies while dialogs are open invalidate it.
    """
    ensure_layout(module, factory)
    report, writes = _plan(module, tokens, bool(expected.get('delete_results', False)) if isinstance(expected, dict) else False)
    if not isinstance(expected, dict) or report != expected:
        raise ValueError('任务或结果已变化，请刷新并重新确认；未执行删除。')
    if confirmation != report['confirmation']:
        raise ValueError('确认凭据与预览不一致，未执行删除。')
    # Unlink the reviewed records/results only. Physical reclamation belongs
    # to explicit maintenance, which checks all surviving/pending references.
    commit_cleanup(module, writes, None, factory)
    return report
