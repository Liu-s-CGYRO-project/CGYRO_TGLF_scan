"""Explicit result-only cleanup. Never visits paths on disk or remote servers."""
from builtins import ValueError, dict, hasattr, list, str, tuple
from OMFITlib_compare_state import MODES, SELECTION_KEYS
from OMFITlib_cgyro_run_state import collection_finished
from OMFITlib_cgyro_task_catalog import manifest_sources, mapping
from OMFITlib_project_history import live_operations
from OMFITlib_workbench_catalog import STATUS

RESULT_KEYS = ('scanResults', 'scanResults_spectra', 'scanResults2D', 'scanResults2D_spectra', 'scanResults3D', 'scanResults3D_spectra',
               'UQResults', 'UQResults_spectra', 'presetResults', 'Experimental_fluxes', 'Experimental_spectra',
               'tgyro_output', '_scan_cache_provenance', '_workbench_index',
               '_radial_cache_provenance')
BRANCHES = (
    ((), ('OUTPUTS',)),
    # Cases and history can retain downloaded payloads after RUN_DB is cleared;
    # RUN_INDEX is also a legacy browser source. Clear the complete result set
    # together, while INPUTS and prepared BATCH_INPUTS remain available.
    (('CGYRO_scan',), ('OUTPUTS', 'OUTPUTScan', 'RUN_DB', 'RUN_MANIFEST', 'RUN_BATCH',
                     'RUN_HISTORY', 'RUN_INDEX', 'Cases', 'LEGACY_UNCLASSIFIED', '_PLOT_CACHE', 'RESULT_STORE', 'RESULT_STORAGE')),
    (('TGLF_scan',), ('RUN_DB', '_workbench_runs', 'sourceResults') + RESULT_KEYS),
    (('TGLF_scan', 'TGLF'), RESULT_KEYS),
    (('TGLF_scan', 'TGYRO'), ('OUTPUTS', 'RUN_DB')),
    (('Transfer_tool', 'OUTPUTS'), ('TGYRO',)),
)
ACTIVE = ('running', 'submitted', 'submitting', 'uploading', 'queued', 'preparing', 'cancel_requested')


def node_at(root, path):
    node = root
    for key in path:
        if not hasattr(node, 'get'):
            return {}
        node = node.get(key, {})
    return node


def _blocking_state(record, model):
    if not hasattr(record, 'get'):
        return ''
    status = record.get('status', '')
    if record.get('submission_uncertain', False) or status == 'submission_unconfirmed':
        return '提交状态待确认'
    if status in ACTIVE:
        return STATUS.get(status, '排队中' if status == 'queued' else status)
    if model == 'CGYRO':
        if collection_finished(record):
            return ''
        stage = record.get('collection_status', '')
        if stage == 'collecting':
            return '正在收集'
        if status == 'loaded' or stage in ('ready', 'incomplete') or (stage == 'pending' and record.get('job_id', '')):
            return '结果待归档'
    if status == 'submitted_or_finished' and not record.get('failed_points', None):
        return '已提交，结果待核对'
    return ''


def active_jobs(root):
    # Persisted activity entries describe a past call, including snapshots
    # saved while it was on the stack. Only a live call owns that local lock.
    blockers = ['本次会话 · ' + title for title in live_operations(root)]
    module = node_at(root, ('CGYRO_scan',))
    records = [('CGYRO', token, manifest) for token, manifest, _ in manifest_sources(module)]
    current = mapping(module.get('RUN_MANIFEST', {}))
    if not current.get('run_token', ''):  # Legacy current manifest outside the token catalog.
        records.append(('CGYRO', '当前任务', current))
    for model, path in (('TGLF', ('TGLF_scan', '_workbench_runs')), ('TGLF', ('TGLF_scan', 'RUN_DB')),
                        ('TGYRO', ('TGLF_scan', 'TGYRO', 'RUN_DB'))):
        records.extend((model, str(key), record) for key, record in node_at(root, path).items())
    for case_id, case in root.get('TGLF_CASES', {}).items():
        for key, record in case.get('runs', {}).items():
            run = '{} / {}'.format(case_id, key)
            records.append(('TGLF', run, record))
            for point_id, point in record.get('points', {}).items():
                records.extend(('TGLF', '{} / {} / {}'.format(run, point_id, attempt_id), attempt)
                               for attempt_id, attempt in point.get('attempts', {}).items())
    for model, key, record in records:
        state = _blocking_state(record, model)
        if state:
            job = record.get('job_id', '')
            label = '{} 作业 {}'.format(model, job) if job else model
            blockers.append('{} · {} · {}'.format(label, key, state))
    return list(dict.fromkeys(blockers))


def require_clearable_results(root):
    blockers = active_jobs(root)
    if blockers:
        raise ValueError('以下任务仍在执行或有结果待核对，暂时无法清空。\n' + '\n'.join(blockers))


def clear_results(root, factory=dict):
    """Called only after the UI confirmation; repeat active-job check at mutation."""
    require_clearable_results(root)
    for path, keys in BRANCHES:
        node = node_at(root, path)
        for key in keys:
            if key in node:
                node[key] = factory()
    # Native runTGLF places output files beside input.tglf in FILES.
    tglf = node_at(root, ('TGLF_scan', 'TGLF'))
    if 'FILES' in tglf:
        files = tglf['FILES']
        kept = factory()
        for key in list(files.keys()):
            if str(key).startswith('input.'):
                value = files[key]
                kept[key] = value.duplicate() if hasattr(value, 'duplicate') else value
        tglf['FILES'] = kept
    for case in root.get('TGLF_CASES', {}).values():
        case['runs'] = factory()
        case['selected_run'] = ''
    state = root.get('PROJECT_STATE', {})
    activity = state.get('activity', {})
    # Keep input replacement history, strip archived calculation payloads.
    for key in list(activity.keys()):
        record = activity[key]
        if not record.get('previous_inputs', None):
            del activity[key]
            continue
        for name in ('tglf_data', 'tgyro_result', 'result', 'results', 'outputs'):
            record.pop(name, None)
    state.pop('pipeline', None)
    workbench = root.get('SETTINGS', {}).get('WORKBENCH', {})
    workbench['message'] = ''
    workbench.pop('cgyro_result_view', None)
    for key in ('result_run', 'result_point'):
        workbench.get('tglf', {})[key] = ''
    root.get('SETTINGS', {}).get('TGLF_MULTI', {}).update(dict(status=''))
    physics = root.get('SETTINGS', {}).get('PHYSICS', {})
    for mode in MODES:
        saved = physics.get(mode, {})
        for selection in (saved, saved.get('CGYRO', {}), saved.get('TGLF', {})):
            for key in SELECTION_KEYS + ('runid', 'result_source', '_selection_source', '_selection_sources', '_pairing_run'):
                selection.pop(key, None)
