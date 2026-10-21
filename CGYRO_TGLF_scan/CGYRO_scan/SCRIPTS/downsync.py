"""Collect only manifest-owned points, preserving partial and prior results.

Probe completion before parsing outputs. The retry controller consumes probe
failures separately from transport/reader errors and decides whether to rerun.
"""
from builtins import Exception, RuntimeError, ValueError, any, enumerate, float, int, len, list, set, str
import os
import re
from OMFITlib_cgyro_run_state import quote as shell_quote, refresh_run_state, text_output as output_text
from OMFITlib_cgyro_continue import validate_continued_result
from OMFITlib_cgyro_retry import point_scheduler_states
from OMFITlib_cgyro_storage import compact_storage, store_result


def read_run_files(command):
    output, errors = [], []
    status = OMFITx.remote_execute(rmtserver, '/bin/bash -c ' + shell_quote(command),
                                  rmtworkdir, rmttunnel, quiet=True, ignoreReturnCode=True,
                                  use_bang_command=False, std_out=output, std_err=errors)
    return status, output_text(output), output_text(errors)


def unique_points(points):
    seen, result = set(), []
    for point in points:
        if point not in seen:
            seen.add(point)
            result.append(point)
    return result


def point_result_dir(point):
    return path_join(manifest.get('point_workdirs', {}).get(point, rmtworkdir), point)


def job_log_tail(points):
    # Solver errors are written to out.cgyro.info, sometimes with a zero exit
    # from the launcher. Show failed points first; successful logs must not
    # consume the diagnostic budget before the actual cause is reported.
    points = unique_points(points)
    command = ''
    for point in points[:12]:
        command += 'point=' + shell_quote(point_result_dir(point)) + '; printf "\\nPOINT: %s\\n" "$point";\n'
        command += ('if [ -s "$point/out.cgyro.info" ]; then\n'
                    '  printf "FILE: %s/out.cgyro.info\\n" "$point";\n'
                    '  grep -m 8 -E "^[[:space:]]*ERROR:" "$point/out.cgyro.info" || true;\nfi\n'
                    'if [ -s "$point/input.cgyro.gen" ]; then\n'
                    '  grep -E "[[:space:]](KY|DELTA_T|DELTA_T_METHOD|ERROR_TOL)[[:space:]]*$" '
                    '"$point/input.cgyro.gen" || true;\nfi\n')
    job_id = str(manifest.get('job_id', '') or '')
    for point in points[:2]:
        paths = [point_result_dir(point) + '/out.cgyro.info', point_result_dir(point) + '/run_log']
        if re.fullmatch(r'[0-9]+', job_id) and point in parentdir:
            index = parentdir.index(point)
            paths += [job_id + '_' + str(index) + '.err', job_id + '_' + str(index) + '.out']
        for name in paths:
            path = shell_quote(name)
            command += ('[ ! -s ' + path + ' ] || { printf "\\nFILE: %s\\n" '
                        + path + '; tail -c 1500 -- ' + path + '; }\n')
    _, output, errors = read_run_files(command)
    return output + ('\n' + errors if errors else '')


def failure_report(points, status='failed'):
    points = unique_points(points)
    manifest['failed_points'] = points
    manifest['status'] = status
    solver_errors = manifest.get('solver_errors', {})
    summary = '\n'.join(point + ': ' + error for point in points for error in solver_errors.get(point, []))
    try:
        logs = job_log_tail(points)
    except Exception as exc:
        logs = 'Could not read additional failed-task logs: ' + str(exc)
    details = summary + ('\n' if summary else '') + logs
    manifest['failure_log'] = details
    labels = []
    for point in points:
        ky = manifest.get('point_table', {}).get(point, {}).get('values', {}).get('KY', None)
        labels.append(point + (' (KY={:g})'.format(float(ky)) if ky is not None else ''))
    report = 'CGYRO failed points: ' + ', '.join(labels) + '\nRun directory: ' + rmtworkdir
    if 'Integration error exceeded limit' in details:
        report += ('\nIntegration error exceeded limit: try a smaller DELTA_T or '
                   'adaptive DELTA_T_METHOD (1-3) in Calculation parameters.')
    states = manifest.get('scheduler_status', '')
    if states:
        report += '\n' + states
    report += '\n' + details if details.strip() else '\nNo valid output; inspect the failed task logs.'
    return report


OUTPUT_PROBE_MAX_BYTES = 16 * 1024


def output_probe_commands():
    """Share the checker and bound the actual UTF-8, shell-quoted argv size.

    remote_execute transports commands over stdin, but our inner bash -c
    still receives one argument. Repeating the checker per point exceeded
    Linux's per-argument limit for larger scans. Paths can also vary after
    retries, so a fixed point count alone is not a safe command-size bound.
    """
    header = r'''cgyro_probe_point() {
  local point="$1" point_id="$2" missing="" name code solver_errors fatal error
  for name in out.cgyro.grids out.cgyro.time; do
    [ -s "$point/$name" ] || missing="$missing $name"
  done
  if [ ! -s "$point/out.cgyro.freq" ] && [ ! -s "$point/bin.cgyro.freq" ]; then
    missing="$missing frequency"
  fi
  if [ -s "$point/cgyro.exit" ]; then
    code=$(cat -- "$point/cgyro.exit"); [ "$code" = 0 ] || missing="$missing exit=$code"
  else missing="$missing no_exit_record"; fi
  if [ -s "$point/out.cgyro.info" ]; then
    solver_errors=$(grep -E "^[[:space:]]*ERROR:" "$point/out.cgyro.info" || true)
    if [ -n "$solver_errors" ]; then
      missing="$missing solver_error"
      printf '%s\n' "$solver_errors" | while IFS= read -r error; do
        printf 'CGYRO_ERROR|%s|%s\n' "$point_id" "$error"
      done
    fi
  fi
  if [ -s "$point/run_log" ]; then
    fatal=$(grep -m 4 -i -E "Integration error exceeded limit|Bogus parameter|Unknown parameter|invalid input|error reading input" "$point/run_log" || true)
    if [ -n "$fatal" ]; then
      missing="$missing solver_error"
      printf '%s\n' "$fatal" | while IFS= read -r error; do
        printf 'CGYRO_ERROR|%s|%s\n' "$point_id" "$error"
      done
    fi
  fi
  printf 'CGYRO_POINT|%s|%s\n' "$point_id" "$missing"
}
'''
    points, calls = [], []
    for point in parentdir:
        # Point IDs appear in a line protocol; paths remain separately quoted.
        if any(char in str(point) for char in ('|', '\n', '\r', '\x00')):
            raise ValueError('Invalid CGYRO point ID in output probe.')
        call = ('cgyro_probe_point ' + shell_quote(point_result_dir(point)) + ' '
                + shell_quote(point) + ' || exit $?\n')
        candidate = header + ''.join(calls) + call
        if len(('/bin/bash -c ' + shell_quote(candidate)).encode('utf-8')) > OUTPUT_PROBE_MAX_BYTES:
            if points:
                yield points, header + ''.join(calls)
                points, calls = [], []
            if len(('/bin/bash -c ' + shell_quote(header + call)).encode('utf-8')) > OUTPUT_PROBE_MAX_BYTES:
                raise ValueError('CGYRO output path exceeds the safe probe command size: ' + str(point))
        points.append(point)
        calls.append(call)
    if points:
        yield points, header + ''.join(calls)


def probe_run_outputs(scheduler, job_id, scheduler_record=None):
    """Validate every read-only batch before loading any solver results."""
    chunks = []
    manifest['output_probe'] = ''
    manifest['output_probe_progress'] = dict(total=len(parentdir), checked=0, batches=0,
                                           max_command_bytes=OUTPUT_PROBE_MAX_BYTES)
    progress = manifest['output_probe_progress']
    for index, (points, command) in enumerate(output_probe_commands(), 1):
        status, output, errors = read_run_files(command)
        chunks.append(output)
        manifest['output_probe'] = '\n'.join(chunks)
        if status != 0:
            progress.update(dict(failed_batch=index, return_code=status, error=errors))
            raise RuntimeError('CGYRO output-file probe failed in batch {} after {}/{} points; '
                               'results have not been loaded. Retry collection; saved jobs and results are preserved.\n{}'.format(
                                   index, progress['checked'], len(parentdir), errors or output))
        seen = [line.split('|')[1] for line in output.splitlines()
                if line.startswith('CGYRO_POINT|') and len(line.split('|')) >= 3]
        if len(seen) != len(points) or set(seen) != set(points):
            progress.update(dict(failed_batch=index, error='Incomplete or duplicate output-probe response'))
            raise RuntimeError('CGYRO output-file probe batch {} did not return its exact point list; '
                               'results have not been loaded. Retry collection.'.format(index))
        progress.update(dict(checked=progress['checked'] + len(points), batches=index))
    output = manifest['output_probe']
    if 'CGYRO_ACTIVE' in output.splitlines():
        manifest['status'] = 'submitted'
        raise RuntimeError('CGYRO job ' + job_id + ' is still queued/running; collect after it finishes.')
    failed, complete, states, solver_errors, absent = set(), set(), [], {}, {}
    seen = []
    for line in output.splitlines():
        fields = line.split('|')
        if len(fields) >= 3 and fields[0] == 'CGYRO_POINT':
            seen.append(fields[1])
            if fields[2].strip():
                failed.add(fields[1])
                missing = fields[2].strip()
                if any(name in missing.split() for name in ('out.cgyro.grids', 'out.cgyro.time', 'frequency')):
                    absent[fields[1]] = missing
            else:
                complete.add(fields[1])
        elif len(fields) >= 3 and fields[0] == 'CGYRO_ERROR':
            failed.add(fields[1])
            solver_errors.setdefault(fields[1], []).append('|'.join(fields[2:]))
        elif len(fields) >= 4 and fields[0] == 'CGYRO_STATE':
            states.append(line)
            state = fields[2].split()[0].rstrip('+') if fields[2].split() else ''
            if state in ('FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY', 'NODE_FAIL', 'BOOT_FAIL', 'DEADLINE', 'PREEMPTED'):
                match = re.fullmatch(job_id + r'_([0-9]+)', fields[1])
                if match and int(match.group(1)) < len(parentdir):
                    point = parentdir[int(match.group(1))]
                    if point not in complete:
                        failed.add(point)
    if states:
        manifest['scheduler_status'] = '\n'.join(states)
    if len(seen) != len(parentdir) or set(seen) != set(parentdir):
        raise RuntimeError('CGYRO output probe did not return the complete task list; results have not been loaded.')
    manifest['solver_errors'] = solver_errors
    manifest['missing_outputs'] = absent
    if scheduler_record is not None:
        # The newest allocation covers only the retried subset. Earlier OOM,
        # timeout/cancellation states still belong to their original points.
        for point, state in point_scheduler_states(manifest).items():
            if state and state != 'COMPLETED':
                failed.add(point)
    manifest['complete_output_points'] = [point for point in parentdir if point in complete]
    return unique_points([point for point in parentdir if point in failed])


def path_join(dirname, filename):
    dirname = str(dirname)
    if dirname.endswith('/') or dirname.endswith('\\'):
        return dirname + filename
    if dirname.startswith('/'):
        return dirname + '/' + filename
    return os.path.join(dirname, filename)


# Native OMFIT versions omit some newer optional histories and profile inputs.
# Preserve them for a subsequent restart without modifying OMFIT itself.
restart_extra_files = ['bin.cgyro.restart', 'bin.cgyro.restart.old', 'run_log', 'cgyro.exit',
                       'input.profiles', 'input.profiles.geo', 'bin.cgyro.kxky_v',
                       'bin.cgyro.lky_flux_n', 'bin.cgyro.lky_flux_e', 'bin.cgyro.lky_flux_v',
                       'bin.cgyro.eparb', 'bin.cgyro.hb']

compact_storage(root, OMFITtree)
setup = root['SETTINGS']['SETUP']
icgyro=setup['icgyro']
rmtsetup=root['SETTINGS']['REMOTE_SETUP']
manifest = root.get('RUN_MANIFEST', None)
if not manifest:
    raise ValueError('No run manifest. Prepare a run first; importing old result directories requires an explicit manifest.')
manifest['load_errors'] = {}
manifest['skipped_reasons'] = {}
manifest['continuation_pending'] = {}
manifest['collection_status'] = 'collecting'
rmtserver = manifest['server']
rmtworkdir = manifest['workDir']
rmttunnel = manifest['tunnel']
failed_cases = []
local = rmtserver == 'localhost'
caseTag = manifest['case_tag']
caseRoot = root['Cases']
parentdir = list(manifest['points'])
loaded_cases = []
partial_cases = []
skipped_cases = []
terminal_status = ''
if icgyro == 1:
    scheduler = str(manifest.get('scheduler', '') or rmtsetup.get(
        str(manifest.get('serverPicker', '') or ''), {}).get('scheduler', '') or '').lower()
    scheduler_record = None
    if scheduler == 'slurm':
        scheduler_record = refresh_run_state(root, OMFITx)
        if scheduler_record['active']:
            raise RuntimeError('CGYRO job is still queued/running; collect after it finishes.')
        if manifest.get('stop_requested', False) and not scheduler_record['terminal']:
            raise RuntimeError('The stop request has no confirmed Slurm terminal state yet. Synchronize job status before collecting.')
        if scheduler_record['outcome'] == 'unknown' and not scheduler_record['queue_verified']:
            raise RuntimeError('Could not confirm the CGYRO job state; its existing record is preserved.')
        if scheduler_record['outcome'] in ('cancelled', 'failed'):
            terminal_status = scheduler_record['outcome']
    failed_cases = probe_run_outputs(scheduler, str(manifest.get('job_id', '') or ''), scheduler_record)
    manifest['probe_failed_points'] = list(failed_cases)
manifest['point_states'] = point_scheduler_states(manifest)
for itemdir in parentdir:
    missing = manifest.get('missing_outputs', {}).get(itemdir, '')
    if missing:
        # Input-only directories are normal for tasks cancelled in the queue.
        skipped_cases.append(itemdir)
        manifest['skipped_reasons'][itemdir] = missing
        print('Skipping ' + itemdir + ': no usable output (' + missing + ')')
        continue
    print("Loading "+itemdir)
    result_dir = point_result_dir(itemdir)
    if local and not os.path.isdir(result_dir):
        print("Missing local result directory: "+result_dir)
        failed_cases.append(itemdir)
        skipped_cases.append(itemdir)
        manifest['skipped_reasons'][itemdir] = 'Missing result directory'
        continue
    try:
        if icgyro==0:
            if local:
                candidate=OMFITgyro(result_dir,extra_files=['RESTART_0','RESTART_tag_0','RESTART_1','RESTART_tag_1','restart.dat'])
            else:
                candidate=OMFITgyro([result_dir,rmtserver,rmttunnel],extra_files=['RESTART_0','RESTART_tag_0','RESTART_1','RESTART_tag_1','restart.dat'])
        else:
            if local:
                candidate=OMFITcgyro(result_dir,extra_files=restart_extra_files)
            else:
                candidate=OMFITcgyro([result_dir,rmtserver,rmttunnel],extra_files=restart_extra_files)
        # Force lazy parsing before replacing a preserved node is considered successful.
        if candidate['n_time'] < 1:
            skipped_cases.append(itemdir)
            failed_cases.append(itemdir)
            manifest['skipped_reasons'][itemdir] = 'No time samples'
            continue
        warning = validate_continued_result(candidate, manifest.get('point_table', {}).get(itemdir, {}))
        caseRoot[caseTag][itemdir] = store_result(root, candidate, OMFITtree) if icgyro == 1 else candidate
        if warning:
            manifest['continuation_pending'][itemdir] = warning
            print(itemdir + ': ' + warning)
        if itemdir in failed_cases or warning:
            partial_cases.append(itemdir)  # Readable samples, never a completed calculation.
        else:
            loaded_cases.append(itemdir)
    except Exception as exc:
        print('Failed to load ' + itemdir + ': ' + str(exc))
        manifest['load_errors'][itemdir] = str(exc)
        failed_cases.append(itemdir)
root['RUN_MANIFEST']['loaded_points'] = loaded_cases
root['RUN_MANIFEST']['partial_points'] = partial_cases
root['RUN_MANIFEST']['skipped_points'] = unique_points(skipped_cases)
root['RUN_MANIFEST']['failed_points'] = unique_points(failed_cases)
root['RUN_MANIFEST']['collection_status'] = 'ready'
if terminal_status == 'cancelled':
    report = failure_report(failed_cases, status='cancelled')
    print('CGYRO job was cancelled. Preserved complete points: {}; readable partial points: {}. '
          'Available results will be archived separately; empty points are skipped.'.format(
              len(loaded_cases), len(partial_cases)))
    print(report)
elif failed_cases:
    print(failure_report(failed_cases) + '\nPrevious archived results are preserved.')
else:
    root['RUN_MANIFEST']['status'] = 'loaded'
if manifest['continuation_pending']:
    print('{} continuation points remain pending; their readable data will be archived as partial results. '
          'No automatic rerun is requested.'.format(len(manifest['continuation_pending'])))
if manifest['load_errors']:
    # Missing files were handled above. Transport/reader corruption remains an
    # error; retry a read without treating it as an empty solver calculation.
    raise RuntimeError('CGYRO result download/read failed: ' + str(manifest['load_errors']))
