"""Explicit result-only cleanup. Never visits paths on disk or remote servers."""
from builtins import dict, hasattr, list, str, tuple
from OMFITlib_compare_state import MODES, SELECTION_KEYS
from OMFITlib_cgyro_queue import queue_records

RESULT_KEYS = ('scanResults', 'scanResults_spectra', 'scanResults2D', 'scanResults2D_spectra',
               'UQResults', 'UQResults_spectra', 'Experimental_fluxes', 'Experimental_spectra',
               'tgyro_output', '_scan_cache_provenance',
               '_radial_cache_provenance')
BRANCHES = (
    ((), ('OUTPUTS',)),
    # Cases and history can retain downloaded payloads after RUN_DB is cleared;
    # RUN_INDEX is also a legacy browser source. Clear the complete result set
    # together, while INPUTS and prepared BATCH_INPUTS remain available.
    (('CGYRO_scan',), ('OUTPUTS', 'OUTPUTScan', 'RUN_DB', 'RUN_MANIFEST', 'RUN_BATCH',
                     'RUN_HISTORY', 'RUN_INDEX', 'Cases', '_PLOT_CACHE', 'RESULT_STORE', 'RESULT_STORAGE')),
    (('TGLF_scan',), ('RUN_DB',) + RESULT_KEYS),
    (('TGLF_scan', 'TGLF'), RESULT_KEYS),
    (('TGLF_scan', 'TGYRO'), ('OUTPUTS', 'RUN_DB')),
    (('Transfer_tool', 'OUTPUTS'), ('TGYRO',)),
)
ACTIVE = ('running', 'submitted', 'submitting', 'queued', 'preparing', 'cancel_requested')


def node_at(root, path):
    node = root
    for key in path:
        if not hasattr(node, 'get'):
            return {}
        node = node.get(key, {})
    return node


def active_jobs(root):
    records = [('CGYRO 当前任务', node_at(root, ('CGYRO_scan', 'RUN_MANIFEST')))]
    records.extend(('CGYRO ' + str(token), entry['manifest'])
                   for token, entry in queue_records(node_at(root, ('CGYRO_scan',))))
    for path in (('TGLF_scan', 'RUN_DB'), ('TGLF_scan', 'TGYRO', 'RUN_DB'), ('PROJECT_STATE', 'activity')):
        records.extend((str(key), record) for key, record in node_at(root, path).items())
    for case in root.get('TGLF_CASES', {}).values():
        for key, record in case.get('runs', {}).items():
            records.append((str(key), record))
            for point in record.get('points', {}).values():
                records.extend((str(key), attempt) for attempt in point.get('attempts', {}).values())
    return [label for label, record in records if hasattr(record, 'get') and (
        record.get('submission_uncertain', False) or
        record.get('status', None) in ACTIVE or
        (record.get('status', None) == 'submitted_or_finished' and not record.get('failed_points', None)))]


def clear_results(root, factory=dict):
    """Called only after the UI confirmation; repeat active-job check at mutation."""
    if active_jobs(root):
        raise ValueError('还有正在运行或已提交的任务。请先结束任务并收集结果，再清空。')
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
