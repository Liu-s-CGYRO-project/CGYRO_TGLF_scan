"""Human-readable metadata for saved TGLF runs; no GUI or solver imports."""
from builtins import str
from datetime import datetime, timezone


def record_summary(record, run_id):
    """Show local time and scan parameter names, without reading result data."""
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
    mode = record.get('mode', saved_plan.get('mode', ''))
    axes = saved_plan.get('uq', []) if mode == 'uq' else saved_plan.get('axes', [])
    captions = []
    for axis in axes:
        name = str(axis.get('name', '')).strip()
        if name and name not in captions:
            captions.append(name)
    return '{} · {}'.format(when, ' + '.join(captions) or '原值')

