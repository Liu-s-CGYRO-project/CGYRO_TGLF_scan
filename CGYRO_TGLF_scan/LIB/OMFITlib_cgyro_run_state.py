"""Read Slurm state without cancelling jobs or altering result payloads."""
from builtins import RuntimeError, ValueError, any, bool, dict, enumerate, int, isinstance, len, list, set, str, tuple
from datetime import datetime, timezone
import re

TERMINAL = {'COMPLETED', 'CANCELLED', 'FAILED', 'TIMEOUT', 'OUT_OF_MEMORY',
            'NODE_FAIL', 'BOOT_FAIL', 'DEADLINE', 'PREEMPTED', 'REVOKED'}


def text_output(value):
    if isinstance(value, (list, tuple)):
        return '\n'.join(text_output(item) for item in value)
    return '' if value is None else str(value)


def quote(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def slurm_probe(job_id):
    if not re.fullmatch(r'[0-9]+', str(job_id)):
        raise ValueError('A numeric Slurm job ID is required to synchronize this run.')
    return '''if command -v squeue >/dev/null 2>&1; then
  if rows=$(squeue -r -h -j JOB_ID -o '%i|%T'); then
    printf 'CGYRO_QUEUE_OK\n'
    if [ -n "$rows" ]; then printf '%s\n' "$rows" | while IFS= read -r row; do printf 'CGYRO_QUEUE|%s\n' "$row"; done; fi
  else printf 'CGYRO_QUEUE_ERROR\n'; fi
else printf 'CGYRO_QUEUE_MISSING\n'; fi
if command -v sacct >/dev/null 2>&1; then
  if rows=$(sacct -X -n -P -j JOB_ID --format=JobID%128,State%64,ExitCode); then
    printf 'CGYRO_ACCOUNT_OK\n'
    if [ -n "$rows" ]; then printf '%s\n' "$rows" | while IFS= read -r row; do printf 'CGYRO_STATE|%s\n' "$row"; done; fi
  else printf 'CGYRO_ACCOUNT_ERROR\n'; fi
else printf 'CGYRO_ACCOUNT_MISSING\n'; fi
'''.replace('JOB_ID', str(job_id))


def parse_probe(output, job_id, points):
    markers, queued, accounts, raw_states = set(), {}, {}, []
    unknown_queue_row = False
    identity = re.compile(re.escape(str(job_id)) + r'(?:_([0-9]+))?')
    for line in output.splitlines():
        fields = [field.strip() for field in line.split('|')]
        if len(fields) == 1:
            markers.add(fields[0])
            continue
        if fields[0] not in ('CGYRO_QUEUE', 'CGYRO_STATE') or len(fields) < 3:
            continue
        if identity.fullmatch(fields[1]) is None:
            if fields[0] == 'CGYRO_QUEUE':
                unknown_queue_row = True
            continue  # Exclude .batch/.extern steps and unrelated allocations.
        state = fields[2].split()[0].rstrip('+') if fields[2].split() else ''
        if not state:
            continue
        if fields[0] == 'CGYRO_QUEUE':
            queued[fields[1]] = state
        else:
            accounts[fields[1]] = state
            raw_states.append(line)
    active = unknown_queue_row or any(state not in TERMINAL for state in queued.values())
    root_state = accounts.get(str(job_id), '')
    child_states = {str(index): accounts.get(str(job_id) + '_' + str(index), '')
                    for index, _ in enumerate(points)}
    all_children_done = bool(points) and all_terminal(child_states.values())
    terminal = ('CGYRO_ACCOUNT_OK' in markers and bool(accounts)
                and not any(state not in TERMINAL for state in accounts.values())
                and (root_state in TERMINAL or all_children_done) and not active)
    states = list(accounts.values())
    outcome = ('active' if active else 'cancelled' if terminal and 'CANCELLED' in states else
               'failed' if terminal and any(state != 'COMPLETED' for state in states) else
               'completed' if terminal else 'unknown')
    return dict(outcome=outcome, terminal=terminal, active=active,
                queue_verified='CGYRO_QUEUE_OK' in markers, accounting_verified='CGYRO_ACCOUNT_OK' in markers,
                point_states={point: child_states[str(index)] or root_state for index, point in enumerate(points)},
                scheduler_status='\n'.join(raw_states), raw=output)


def all_terminal(states):
    values = list(states)
    return bool(values) and not any(state not in TERMINAL for state in values)


def refresh_run_state(root, ui):
    """Update only run bookkeeping after a read-only query of the saved endpoint."""
    manifest = root.get('RUN_MANIFEST', {})
    if not manifest:
        raise ValueError('No CGYRO run record is available.')
    if manifest.get('status', '') == 'published':
        return dict(outcome='published', terminal=True, active=False)
    remote = root['SETTINGS']['REMOTE_SETUP']
    scheduler = str(manifest.get('scheduler', '') or remote.get(
        str(manifest.get('serverPicker', '') or ''), {}).get('scheduler', '')).lower()
    job_id = str(manifest.get('job_id', '') or '')
    if scheduler != 'slurm' or not re.fullmatch(r'[0-9]+', job_id):
        raise ValueError('This run lacks a saved Slurm job ID; its remote state cannot be inferred.')
    output, errors = [], []
    code = ui.remote_execute(manifest['server'], '/bin/bash -c ' + quote(slurm_probe(job_id)),
                             manifest['workDir'], manifest.get('tunnel', ''), quiet=True,
                             ignoreReturnCode=True, use_bang_command=False, std_out=output, std_err=errors)
    if code != 0:
        raise RuntimeError('Could not synchronize the previous CGYRO job; its record is unchanged. ' + text_output(errors))
    result = parse_probe(text_output(output), job_id, list(manifest.get('points', [])))
    manifest['scheduler_status'] = result['scheduler_status']
    manifest['scheduler_sync'] = dict(result, checked_at=datetime.now(timezone.utc).isoformat(),
                                      errors=text_output(errors))
    if result['outcome'] == 'active':
        manifest['status'] = 'submitted'
    elif result['outcome'] in ('cancelled', 'failed'):
        manifest['status'] = result['outcome']
        manifest['terminal_reason'] = 'slurm_' + result['outcome']
    elif result['outcome'] == 'completed' and manifest.get('status', '') != 'loaded':
        manifest['status'] = 'submitted_or_finished'
    return result
