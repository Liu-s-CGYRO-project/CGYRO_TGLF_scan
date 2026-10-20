"""Scheduler I/O and cancellation for one recorded CGYRO attempt.

This layer never submits work. Queue orchestration selects the saved manifest;
all queries and cancellation use that manifest's endpoint and job identity.
"""
from builtins import (Exception, RuntimeError, ValueError, any, bool, dict, enumerate,
                      getattr, int, isinstance, len, list, print, range, set, str, tuple, zip)
from contextlib import contextmanager
from datetime import datetime, timezone
import re

TERMINAL = {'COMPLETED', 'CANCELLED', 'FAILED', 'TIMEOUT', 'OUT_OF_MEMORY',
            'NODE_FAIL', 'BOOT_FAIL', 'DEADLINE', 'PREEMPTED', 'REVOKED'}

JOB_ID_RULES = {
    'slurm': r'(?i)submitted\s+batch\s+job\s+([0-9]+)',
    'pbs': r'(?m)^\s*([0-9]+(?:\.[A-Za-z0-9._-]+)?)\s*$',
}


def saved_slurm_run(root):
    """Use the submitted run's endpoint, never a newly selected server."""
    manifest = root.get('RUN_MANIFEST', {})
    if not manifest:
        raise ValueError('No CGYRO run record is available.')
    remote = root['SETTINGS']['REMOTE_SETUP']
    scheduler = str(manifest.get('scheduler', '') or remote.get(
        str(manifest.get('serverPicker', '') or ''), {}).get('scheduler', '')).lower()
    job_id = str(manifest.get('job_id', '') or '')
    if scheduler != 'slurm' or not re.fullmatch(r'[0-9]+', job_id):
        raise ValueError('This run lacks a saved Slurm job ID; its remote state cannot be inferred.')
    if not manifest.get('server', '') or not str(manifest.get('workDir', '')).startswith('/'):
        raise ValueError('The submitted run needs its original server and absolute working directory.')
    return manifest, job_id


def text_output(value):
    if isinstance(value, (list, tuple)):
        return '\n'.join(text_output(item) for item in value)
    return '' if value is None else str(value)


def quote(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def submitted_job_id(output, scheduler):
    """Accept only the scheduler's submission reply, never incidental numbers."""
    if scheduler not in JOB_ID_RULES:
        raise ValueError('A Slurm/PBS scheduler is required to confirm submission.')
    match = re.search(JOB_ID_RULES[scheduler], text_output(output))
    return match.group(1) if match is not None else ''


def slurm_queue_query(job_id):
    """Define a Bash query shared by waiting, synchronization and cancellation.

    Slurm can reject a finished allocation ID after purging its live record.
    Only that response permits a second query without an ID filter. A successful
    listing with no matching allocation confirms absence from the current
    queue, not successful completion: accounting and output checks still apply.
    Other query errors must remain errors to avoid duplicate submissions.
    """
    if not re.fullmatch(r'[0-9]+', str(job_id)):
        raise ValueError('A numeric Slurm job ID is required to synchronize this run.')
    return r'''cgyro_queue_rows() {
  local job_id=JOB_ID format="$1" rows row queued_id
  if ! rows=$(LC_ALL=C squeue --local -r -h --states=all -j "$job_id" -o "$format" 2>&1); then
    if [[ "$rows" != *"Invalid job id specified"* ]]; then
      printf '%s\n' "$rows" >&2; return 1
    fi
    # Do not suppress controller/connection failures or trust stale accounting.
    # Query the visible queue successfully, then retain this allocation only.
    if ! rows=$(LC_ALL=C squeue --local -r -h --states=all -o "$format" 2>&1); then
      printf '%s\n' "$rows" >&2; return 1
    fi
  fi
  while IFS= read -r row; do
    [ -n "$row" ] || continue
    queued_id=${row%%|*}
    if [[ "$row" != *"|"* ]] || [[ ! "$queued_id" =~ ^[0-9]+([_+].+)?$ ]]; then
      printf 'Unexpected squeue response: %s\n' "$row" >&2; return 1
    fi
    case "$queued_id" in
      "$job_id"|"${job_id}_"*|"${job_id}+"*) printf '%s\n' "$row" ;;
    esac
  done <<< "$rows"
  return 0
}
'''.replace('JOB_ID', str(job_id))


def slurm_probe(job_id):
    return slurm_queue_query(job_id) + '''for name in ${!SQUEUE_@} ${!SACCT_@}; do unset "$name"; done
unset SLURM_CLUSTERS
if command -v squeue >/dev/null 2>&1; then
  if rows=$(cgyro_queue_rows '%i|%T'); then
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


def parse_probe(output, job_id, points, task_indices=None):
    """Map a retry subset using original array indices, not subset positions."""
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
    indices = list(range(len(points))) if task_indices is None else list(task_indices)
    if len(indices) != len(points) or len(set(indices)) != len(indices):
        raise ValueError('Scheduler task indices must match the distinct active points.')
    child_states = {str(index): accounts.get(str(job_id) + '_' + str(index), '') for index in indices}
    all_children_done = bool(points) and all_terminal(child_states.values())
    # Accounting can lag a requeue. A failed queue query is not proof that the
    # allocation stopped, even when an older accounting row says COMPLETED.
    terminal = ('CGYRO_QUEUE_OK' in markers and 'CGYRO_ACCOUNT_OK' in markers and bool(accounts)
                and not any(state not in TERMINAL for state in accounts.values())
                and (root_state in TERMINAL or all_children_done) and not active)
    states = list(accounts.values())
    outcome = ('active' if active else 'cancelled' if terminal and 'CANCELLED' in states else
               'failed' if terminal and any(state != 'COMPLETED' for state in states) else
               'completed' if terminal else 'unknown')
    return dict(outcome=outcome, terminal=terminal, active=active,
                queue_verified='CGYRO_QUEUE_OK' in markers, accounting_verified='CGYRO_ACCOUNT_OK' in markers,
                point_states={point: child_states[str(index)] or root_state for point, index in zip(points, indices)},
                scheduler_status='\n'.join(raw_states), raw=output)


def all_terminal(states):
    values = list(states)
    return bool(values) and not any(state not in TERMINAL for state in values)


def stop_marker(job_id, run_token):
    if not re.fullmatch(r'[0-9]+', str(job_id)) or not re.fullmatch(r'[0-9a-f]{32}', str(run_token)):
        raise ValueError('A saved job ID and run token are required to stop this scan.')
    return '.cgyro_stop_' + str(run_token), str(job_id) + ':' + str(run_token)


def slurm_cancel(job_id, run_token, workdir):
    """Cancel one verified parent allocation, then wake only its local waiter."""
    marker, stamp = stop_marker(job_id, run_token)
    return slurm_queue_query(job_id) + '''set -eu
job_id=JOB_ID
stop_file=STOP_FILE
stop_stamp=STOP_STAMP
cd -- WORK_DIR
expected_dir=$(pwd -P)
# Ambient Slurm filters must not hide elements or turn cancellation into signalling.
for name in ${!SQUEUE_@} ${!SCANCEL_@}; do unset "$name"; done
unset SLURM_CLUSTERS
if ! rows=$(cgyro_queue_rows '%i|%Z'); then
  printf 'CGYRO_CANCEL_QUERY_ERROR\n'; exit 31
fi
if [ -n "$rows" ]; then
  while IFS='|' read -r queued_id queued_dir; do
    if [[ ! "$queued_id" =~ ^${job_id}(_[0-9]+)?$ ]]; then
      printf 'CGYRO_CANCEL_ID_ERROR\n'; exit 32
    fi
    if [ -z "$queued_dir" ] || ! actual_dir=$(cd -- "$queued_dir" 2>/dev/null && pwd -P); then
      printf 'CGYRO_CANCEL_DIRECTORY_ERROR\n'; exit 33
    fi
    if [ "$actual_dir" != "$expected_dir" ]; then
      printf 'CGYRO_CANCEL_DIRECTORY_MISMATCH\n'; exit 34
    fi
  done <<< "$rows"
  if ! scancel "$job_id"; then printf 'CGYRO_CANCEL_REJECTED\n'; exit 35; fi
  printf 'CGYRO_CANCEL_ACCEPTED\n'
else
  printf 'CGYRO_CANCEL_IDLE\n'
fi
if printf '%s\n' "$stop_stamp" > "$stop_file"; then
  printf 'CGYRO_CANCEL_WAKE_OK\n'
else
  printf 'CGYRO_CANCEL_WAKE_ERROR\n'; exit 36
fi
'''.replace('JOB_ID', str(job_id)).replace('STOP_FILE', quote(marker)).replace(
        'STOP_STAMP', quote(stamp)).replace('WORK_DIR', quote(workdir))


def slurm_wait(job_id, run_token):
    """Poll Slurm every 30 s, but notice an accepted stop within one second."""
    marker, stamp = stop_marker(job_id, run_token)
    return slurm_queue_query(job_id) + '''for name in ${!SQUEUE_@}; do unset "$name"; done
unset SLURM_CLUSTERS
stop_file=STOP_FILE
stop_stamp=STOP_STAMP
check_stop() {
  if [ -f "$stop_file" ] && [ "$(cat -- "$stop_file" 2>/dev/null)" = "$stop_stamp" ]; then
    printf 'CGYRO_WAIT_STOPPED\n'; exit 125
  fi
}
hb=0
while true; do
  check_stop
  queued=$(cgyro_queue_rows '%i|%T') || exit 1
  [ -n "$queued" ] || break
  tick=0
  while [ "$tick" -lt 30 ]; do
    check_stop
    sleep 1
    tick=$((tick+1))
  done
  hb=$((hb+30))
  if [ "$hb" -ge 600 ]; then
    echo "[heartbeat] job JOB_ID still in queue/running at $(date)"; hb=0
  fi
done
echo "[heartbeat] job JOB_ID left the queue at $(date)"
'''.replace('JOB_ID', str(job_id)).replace('STOP_FILE', quote(marker)).replace('STOP_STAMP', quote(stamp))


def pbs_wait(job_id):
    """Do not confuse an unavailable PBS server with a finished allocation."""
    if not re.fullmatch(r'[0-9]+(?:\.[A-Za-z0-9._-]+)?', str(job_id)):
        raise ValueError('A recorded PBS job ID is required before waiting.')
    return '''while true; do
  if state=$(LC_ALL=C qstat -f JOB_ID 2>&1); then
    if printf '%s\\n' "$state" | grep -Eq 'job_state[[:space:]]*=[[:space:]]*[CF]([[:space:]]|$)'; then
      break
    fi
  elif printf '%s\\n' "$state" | grep -Eiq 'unknown[[:space:]]+job[[:space:]]+id'; then
    break
  else
    printf '%s\\n' "$state" >&2; exit 1
  fi
  sleep 30
done
'''.replace('JOB_ID', str(job_id))


def stop_message(manifest):
    if manifest.get('collection_status', '') in ('partial', 'empty'):
        return '本次结果已收集：完整点 {}，部分结果点 {}，无结果跳过 {}。可选择未完成点继续计算。'.format(
            len(manifest.get('loaded_points', [])), len(manifest.get('partial_points', [])),
            len(manifest.get('skipped_points', [])))
    state = manifest.get('status', '')
    if state == 'cancelled':
        return '本次扫描已中止，正在自动收集已有输出；无结果的点将跳过。'
    if state == 'failed':
        return '当前作业已结束，后续组合不再提交；已有输出和日志保留。'
    if manifest.get('scheduler_sync', {}).get('outcome', '') == 'completed':
        return '当前作业已完成，后续组合不再提交；正在收集当前结果。'
    if manifest.get('cancellation', {}).get('accepted', False):
        return '取消请求已送达 Slurm，本地等待与后续提交停止；作业收尾状态可通过“同步作业状态”查看。'
    return '后续组合不再提交；远程作业终态尚未确认，请同步作业状态。'


def stop_run(root, ui, expected_job_id, expected_run_token):
    """Explicit user action; preserve outputs and never invent a terminal state."""
    manifest, job_id = saved_slurm_run(root)
    if manifest.get('status', '') == 'published':
        raise ValueError('This run is already archived; there is no current job to stop.')
    run_token = str(manifest.get('run_token', '') or '')
    if job_id != str(expected_job_id) or run_token != str(expected_run_token):
        raise ValueError('当前运行记录已变化，不能通过旧等待窗口取消另一项作业。')
    record_root = dict(RUN_MANIFEST=manifest, SETTINGS=root['SETTINGS'])
    command = slurm_cancel(job_id, run_token, manifest['workDir'])
    previous = manifest.get('cancellation', {})
    if previous.get('accepted', False) and previous.get('wake_sent', False):
        try:
            return refresh_run_state(record_root, ui)
        except Exception as exc:
            previous['sync_error'] = str(exc)
            return None
    request = dict(requested_at=datetime.now(timezone.utc).isoformat(), job_id=job_id,
                   in_progress=True, accepted=False, wake_sent=False)
    manifest['cancellation'] = request
    request = manifest['cancellation']  # OMFIT may wrap mappings on assignment.
    manifest['stop_requested'] = True
    output, errors = [], []
    try:
        code = ui.remote_execute(manifest['server'], '/bin/bash -c ' + quote(command),
                                 manifest['workDir'], manifest.get('tunnel', ''), quiet=True,
                                 ignoreReturnCode=True, use_bang_command=False, std_out=output, std_err=errors)
        rows = set(text_output(output).splitlines())
        request.update(dict(accepted='CGYRO_CANCEL_ACCEPTED' in rows,
                            wake_sent='CGYRO_CANCEL_WAKE_OK' in rows,
                            no_active_job='CGYRO_CANCEL_IDLE' in rows,
                            return_code=code, output=text_output(output), errors=text_output(errors)))
        if request['accepted']:
            manifest['status'] = 'cancel_requested'
        try:
            result = refresh_run_state(record_root, ui)
        except Exception as exc:
            request['sync_error'] = str(exc)
            result = None
        if not request['accepted'] and not request['wake_sent'] and not (result and result['terminal']):
            raise RuntimeError('未能取消本次 Slurm 作业，本地仍在等待，可再次点击 Kill local 重试。\n'
                               + text_output(errors) + '\n' + text_output(output))
        return result
    except Exception as exc:
        request['error'] = str(exc)
        raise
    finally:
        request['in_progress'] = False


@contextmanager
def linked_kill_local(run_root, ui, job_id, run_token, stop_callback=None):
    """Rebind only this wait dialog's existing Kill local; do not patch OMFIT.

    Native OMFIT places its command-details Text and button row in one panel.
    The unique wait stamp identifies the panel, including embedded run windows.
    A Map handler wires the button before interaction and is inactive afterwards.
    """
    import tkinter as tk
    from tkinter import messagebox

    _, stamp = stop_marker(job_id, run_token)
    aux = getattr(ui, '_aux', {})
    tk_root = aux.get('rootGUI', None)
    if not isinstance(tk_root, tk.Misc):
        tk_root = getattr(tk, '_default_root', None)
    if not isinstance(tk_root, tk.Misc):
        yield
        return
    handlers = getattr(tk_root, '_cgyro_stop_handlers', None)
    if handlers is None:
        handlers = {}
        tk_root._cgyro_stop_handlers = handlers
    if not getattr(tk_root, '_cgyro_stop_map_binding', None):
        def mapped(event):
            for attach in list(tk_root._cgyro_stop_handlers.values()):
                attach(event.widget)
        tk_root._cgyro_stop_map_binding = tk_root.bind_class('TButton', '<Map>', mapped, add='+')
    linked = {}
    needle = stamp
    wait_manifest = run_root.get('RUN_MANIFEST', {})

    def attach(button):
        if button in linked:
            return
        try:
            if str(button.cget('text')).strip() != 'Kill local':
                return
            panel = button.master.master
            if not any(isinstance(widget, tk.Text) and needle in widget.get('1.0', 'end-1c')
                       and 'CGYRO_WAIT_STOPPED' in widget.get('1.0', 'end-1c')
                       for widget in panel.winfo_children()):
                return
            original = str(button.cget('command'))
            if not original:
                return

            def stop():
                try:
                    button.configure(state='disabled')
                    if stop_callback is None:
                        stop_run(run_root, ui, job_id, run_token)
                    else:
                        stop_callback()
                    wait_manifest['auto_collect_requested'] = True
                    print(stop_message(wait_manifest))
                    # The marker may already have ended the wait during the query.
                    if button.winfo_exists():
                        button.tk.call(original)
                except Exception as exc:
                    print('结束任务未完成：' + str(exc))
                    messagebox.showerror('结束任务未完成', str(exc))
                finally:
                    if button.winfo_exists():
                        button.configure(state='normal')

            button.configure(command=stop)
            linked[button] = original
        except tk.TclError:
            return  # A window can be destroyed while a nested request returns.

    handlers[stamp] = attach
    try:
        yield
    finally:
        handlers.pop(stamp, None)
        for button, original in list(linked.items()):
            try:
                if button.winfo_exists():
                    button.configure(command=original)
            except tk.TclError:
                pass


def refresh_run_state(root, ui):
    """Update only run bookkeeping after a read-only query of the saved endpoint."""
    manifest = root.get('RUN_MANIFEST', {})
    if not manifest:
        raise ValueError('No CGYRO run record is available.')
    if manifest.get('status', '') == 'published':
        return dict(outcome='published', terminal=True, active=False)
    manifest, job_id = saved_slurm_run(root)
    output, errors = [], []
    code = ui.remote_execute(manifest['server'], '/bin/bash -c ' + quote(slurm_probe(job_id)),
                             manifest['workDir'], manifest.get('tunnel', ''), quiet=True,
                             ignoreReturnCode=True, use_bang_command=False, std_out=output, std_err=errors)
    if code != 0:
        raise RuntimeError('Could not synchronize the previous CGYRO job; its record is unchanged. ' + text_output(errors))
    all_points = list(manifest.get('points', []))
    active = list(manifest.get('active_points', all_points))
    result = parse_probe(text_output(output), job_id, active, [all_points.index(point) for point in active])
    manifest['scheduler_status'] = result['scheduler_status']
    manifest['scheduler_sync'] = dict(result, checked_at=datetime.now(timezone.utc).isoformat(),
                                      errors=text_output(errors))
    if result['outcome'] == 'active':
        manifest['status'] = ('cancel_requested' if manifest.get('cancellation', {}).get('accepted', False)
                              else 'submitted')
    elif result['outcome'] in ('cancelled', 'failed'):
        manifest['status'] = result['outcome']
        manifest['terminal_reason'] = 'slurm_' + result['outcome']
    elif result['outcome'] == 'completed' and manifest.get('status', '') not in ('loaded', 'failed'):
        manifest['status'] = 'submitted_or_finished'
    return result
