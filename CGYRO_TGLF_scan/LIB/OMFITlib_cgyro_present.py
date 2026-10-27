"""Metadata-only captions for CGYRO views; never use display text as identity.

These helpers read small manifest fields, not result arrays or remote files.
Keep complete identifiers in record_details and persistent keys unchanged.
"""
from builtins import len, str
from collections import Counter, OrderedDict
import re
from OMFITlib_cgyro_archive import canonical_case_key, case_parts, clean_run_id, scan_key
from OMFITlib_workbench_catalog import STATUS


def case_caption(value):
    """Shared radius/isotope label for selectors, live jobs and result records."""
    parts = case_parts(value)
    if parts is None:
        return canonical_case_key(value)
    nr, rho, ion = parts
    radius = 'nr=' + nr if rho == 'unknown' else 'ρ=' + rho
    return '{} · {}'.format(radius, '原始' if ion == 'BASE' else ion)


def short_text(value, limit=24):
    value = ' '.join(str(value).split())
    return value if len(value) <= limit else value[:limit - 1] + '…'


def collection_caption(record):
    """Collection and scheduler state are independent, especially after Kill."""
    state = record.get('collection_status', '')
    if state == 'partial':
        return '部分结果已保留'
    if state == 'empty':
        return '无新结果'
    if record.get('status', '') == 'published':
        return '已归档'
    return {'complete': '已归档', 'collecting': '正在收集', 'ready': '已读取，待归档',
            'incomplete': '收集中断，可重收集', 'pending': '待收集',
            'loaded': '已读取，待归档'}.get(state, '待收集')


def run_caption(record):
    status = str(record.get('status', ''))
    job = str(record.get('job_id', '') or '尚未确认')
    caption = '{} · 作业 {} · {}'.format(short_text(case_caption(record.get('case_id', '')), 30),
                                        job, STATUS.get(status, status or '尚无记录'))
    if record.get('retry_count', 0):
        caption += ' · 重试{}'.format(record['retry_count'])
    return caption


def record_details(record, token=''):
    """Full copyable identity for help windows, including recovery paths."""
    values = [('结果集', record.get('runid', '')), ('案例', record.get('case_id', '')),
              ('扫描轴', scan_key(record, record.get('scan_key', ''))),
              ('作业', record.get('job_id', '')), ('运行标识', token or record.get('run_token', '')),
              ('作业状态', STATUS.get(record.get('status', ''), record.get('status', ''))),
              ('收集状态', collection_caption(record)), ('服务器', record.get('server', '')),
              ('运行目录', record.get('workDir', '')), ('结果目录', record.get('result_dir', ''))]
    return '\n'.join('{}：{}'.format(key, value) for key, value in values if value != '')


def record_options(records):
    """Short unique labels mapped to unchanged tokens, including legacy runs.

    Equal radius/ion/axes need disambiguation (e.g. multiple original inputs).
    Never let a truncated caption silently overwrite another selectable run.
    """
    labels = OrderedDict()
    for token, record in records.items():
        runid = clean_run_id(record.get('runid', '未命名'))
        scan = scan_key(record, record.get('scan_key', '')).replace('__', ' × ')
        labels[token] = ' | '.join((short_text(runid, 18),
            short_text(case_caption(record.get('case_id', '未知案例')), 26), short_text(scan or '旧扫描', 32)))
        if record.get('kind', '') == 'scan':
            labels[token] += ' · 当前结果'
        elif record.get('kind', '') == 'version':
            labels[token] += ' · 未归档 ' + str(record.get('job_id', '') or record.get('run_token', '')[:8])
        suffix = ('待核对' if record.get('resume_error', '') else
                  '无新结果' if record.get('collection_status', '') == 'empty' else
                  '旧记录' if record.get('legacy_record', False) else '')
        if suffix:
            labels[token] += ' · ' + suffix
    counts, options = Counter(labels.values()), OrderedDict()
    for token, label in labels.items():
        if counts[label] > 1:
            label += ' · ' + str(token)[:8]
        candidate, index = label, 1
        while candidate in options:
            index += 1
            candidate = '{} ({})'.format(label, index)
        options[candidate] = token
    return options
