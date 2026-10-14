"""Human-readable metadata for saved TGLF runs; no GUI or solver imports."""
from builtins import any, float, len, max, min, next, iter, set, str
from datetime import datetime, timezone
import math


def record_summary(record, run_id):
    """Describe saved run metadata; never open solver inputs or result arrays."""
    try:
        moment = datetime.fromisoformat(str(record.get('created', '')).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        try:
            moment = datetime.strptime(str(run_id).split('_')[0], '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc)
        except ValueError:
            moment = None
    if moment is None:
        when = '时间未知'
    else:
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        moment = moment.astimezone()
        when = moment.strftime('%m-%d %H:%M:%S' if moment.year == datetime.now().year else '%Y-%m-%d %H:%M:%S')
    saved_plan = record.get('plan', {})
    sources = saved_plan.get('sources', [])
    mode = record.get('mode', saved_plan.get('mode', ''))
    modes = {'single': '单点计算' if len(sources) <= 1 else '径向计算',
             '1d': '一维扫描', '2d': '二维扫描', 'uq': '不确定度扫描'}
    scan = modes.get(mode, '计算')
    axes = saved_plan.get('uq', []) if mode == 'uq' else saved_plan.get('axes', [])
    captions = []
    for axis in axes:
        name = str(axis.get('name', ''))
        if not name:
            continue
        values = axis.get('values', [])
        variants = [item for source in sources for item in source.get('axes', []) if item.get('name', None) == name]
        varies = any(item.get('values', []) != values for item in variants)
        try:
            if values and not varies:
                name += '=' + ('{:g}'.format(values[0]) if len(values) == 1 else
                               '{:g}…{:g}'.format(min(values), max(values)))
        except (TypeError, ValueError):
            pass
        captions.append(name + ('（随半径）' if varies else ''))
    if captions:
        scan += ' ' + ' × '.join(captions[:2]) + ('等' if len(captions) > 2 else '')
    radii, coordinates = [], set()
    for source in sources:
        try:
            radius = float(source.get('rho', None))
            if math.isfinite(radius):
                radii.append(radius)
                coordinates.add(str(source.get('coordinate', 'rho')))
        except (TypeError, ValueError):
            pass
    if radii and len(radii) == len(sources) and len(coordinates) == 1:
        coordinate = next(iter(coordinates))
        coordinate = 'ρ' if coordinate == 'rho' else coordinate
        span = '{:g}'.format(radii[0]) if min(radii) == max(radii) else '{:g}–{:g}'.format(min(radii), max(radii))
        inputs = coordinate + '=' + span
    elif len(sources) == 1:
        inputs = str(sources[0].get('label', '单个输入'))
    else:
        inputs = '{} 个输入'.format(len(sources))
    total = saved_plan.get('total', None)
    if total is None:
        total = len(record.get('points', {}))
    status = {'complete': '完成', 'failed': '失败', 'partial': '部分完成',
              'running': '运行中', 'cancelled': '已中止', 'prepared': '待运行'}.get(
                  record.get('status', ''), '状态未知')
    return '{} · {} · {} · {} 点 · {}'.format(when, scan, inputs, total, status)

