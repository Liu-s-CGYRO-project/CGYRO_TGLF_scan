# this script is used to downsync those results after the calculation running is finished.
# we will have two kinds of loading method, determined by iloadmthd
from builtins import Exception, RuntimeError, ValueError, float, int, isinstance, len, list, set, str, tuple
import os
import re


def shell_quote(value):
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def output_text(value):
    if isinstance(value, (list, tuple)):
        return '\n'.join(output_text(item) for item in value)
    return '' if value is None else str(value)


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


def job_log_tail(points):
    # Solver errors are written to out.cgyro.info, sometimes with a zero exit
    # from the launcher. Show failed points first; successful logs must not
    # consume the diagnostic budget before the actual cause is reported.
    points = unique_points(points)
    command = ''
    for point in points[:12]:
        command += 'point=' + shell_quote(point) + '; printf "\\nPOINT: %s\\n" "$point";\n'
        command += ('if [ -s "$point/out.cgyro.info" ]; then\n'
                    '  printf "FILE: %s/out.cgyro.info\\n" "$point";\n'
                    '  grep -m 8 -E "^[[:space:]]*ERROR:" "$point/out.cgyro.info" || true;\nfi\n'
                    'if [ -s "$point/input.cgyro.gen" ]; then\n'
                    '  grep -E "[[:space:]](KY|DELTA_T|DELTA_T_METHOD|ERROR_TOL)[[:space:]]*$" '
                    '"$point/input.cgyro.gen" || true;\nfi\n')
    job_id = str(manifest.get('job_id', '') or '')
    for point in points[:2]:
        paths = [str(point) + '/out.cgyro.info', str(point) + '/run_log']
        if re.fullmatch(r'[0-9]+', job_id) and point in parentdir:
            index = parentdir.index(point)
            paths += [job_id + '_' + str(index) + '.err', job_id + '_' + str(index) + '.out']
        for name in paths:
            path = shell_quote(name)
            command += ('[ ! -s ' + path + ' ] || { printf "\\nFILE: %s\\n" '
                        + path + '; tail -c 1500 -- ' + path + '; }\n')
    _, output, errors = read_run_files(command)
    return output + ('\n' + errors if errors else '')


def failure_report(points):
    points = unique_points(points)
    manifest['failed_points'] = points
    manifest['status'] = 'failed'
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


def probe_run_outputs(scheduler, job_id):
    command = ''
    if scheduler == 'slurm' and re.fullmatch(r'[0-9]+', job_id):
        command += ('queued=$(squeue -h -j ' + job_id + ') || exit 1;\n'
                    'if [ -n "$queued" ]; then printf "CGYRO_ACTIVE\\n"; exit 0; fi\n'
                    'if command -v sacct >/dev/null 2>&1; then\n'
                    '  sacct -X -n -P -j ' + job_id + ' --format=JobID,State,ExitCode 2>/dev/null '
                    '| while IFS= read -r row; do printf "CGYRO_STATE|%s\\n" "$row"; done\nfi\n')
    for point in parentdir:
        command += 'point=' + shell_quote(point) + '; missing="";\n'
        command += ('for name in out.cgyro.grids out.cgyro.time; do\n'
                    '  [ -s "$point/$name" ] || missing="$missing $name";\ndone\n'
                    'if [ -s "$point/cgyro.exit" ]; then\n'
                    '  code=$(cat -- "$point/cgyro.exit"); [ "$code" = 0 ] || missing="$missing exit=$code";\nfi\n'
                    'if [ -s "$point/out.cgyro.info" ]; then\n'
                    '  solver_errors=$(grep -E "^[[:space:]]*ERROR:" "$point/out.cgyro.info" || true);\n'
                    '  if [ -n "$solver_errors" ]; then\n'
                    '    missing="$missing solver_error";\n'
                    '    printf "%s\\n" "$solver_errors" | while IFS= read -r error; do\n'
                    '      printf "CGYRO_ERROR|%s|%s\\n" "$point" "$error";\n'
                    '    done;\n  fi;\nfi\n'
                    'printf "CGYRO_POINT|%s|%s\\n" "$point" "$missing";\n')
    status, output, errors = read_run_files(command)
    manifest['output_probe'] = output
    if status != 0:
        raise RuntimeError('CGYRO job query failed; results have not been loaded: ' + errors)
    if 'CGYRO_ACTIVE' in output.splitlines():
        manifest['status'] = 'submitted'
        raise RuntimeError('CGYRO job ' + job_id + ' is still queued/running; collect after it finishes.')
    failed, states, solver_errors = set(), [], {}
    seen = []
    for line in output.splitlines():
        fields = line.split('|')
        if len(fields) >= 3 and fields[0] == 'CGYRO_POINT':
            seen.append(fields[1])
            if fields[2].strip():
                failed.add(fields[1])
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
                    failed.add(point)
    manifest['scheduler_status'] = '\n'.join(states)
    manifest['solver_errors'] = solver_errors
    if set(seen) != set(parentdir):
        raise RuntimeError('CGYRO output probe did not return the complete task list; results have not been loaded.')
    return unique_points([point for point in parentdir if point in failed])


def cfg_get(node, key, default=None):
    try:
        if key in node.keys():
            return node[key]
    except Exception:
        pass
    return default


def cfg_str(node, key, default=''):
    value = cfg_get(node, key, default)
    if value is None:
        return default
    return str(value)


def path_join(dirname, filename):
    dirname = str(dirname)
    if dirname.endswith('/') or dirname.endswith('\\'):
        return dirname + filename
    if dirname.startswith('/'):
        return dirname + '/' + filename
    return os.path.join(dirname, filename)


def runtime_abs_path(path):
    path = str(path)
    if path.startswith('/') or (len(path) > 2 and path[1] == ':' and path[2] in ['/', '\\']):
        return path
    return os.path.abspath(path)


def looks_like_result_dir(path):
    if not os.path.isdir(path):
        return False
    markers = [
        'input.cgyro',
        'out.cgyro.info',
        'out.cgyro.freq',
        'out.cgyro.time',
        'run_log',
    ]
    for marker in markers:
        if os.path.exists(path_join(path, marker)):
            return True
    return False


def discover_local_result_dirs(workdir):
    workdir = runtime_abs_path(workdir)
    if not os.path.isdir(workdir):
        return []
    result_dirs = []
    for name in sorted(os.listdir(workdir)):
        if name.startswith('.') or name == '__pycache__':
            continue
        full_path = path_join(workdir, name)
        if looks_like_result_dir(full_path):
            result_dirs.append(name)
    return result_dirs


setup=root['SETTINGS']['SETUP']
# iloadmthd=setup['iloadmthd'] # 0(default): OMFITcgyro, 1: OMFITgacode
# outputs={'bin.cgyro.aparb':OMFITgacode,'bin.cgyro.phib':OMFITgacode,'bin.cgyro.bparb':OMFITgacode,\
#                   'bin.cgyro.geo':OMFITgacode,'bin.cgyro.kxky_phi':OMFITgacode,'bin.cgyro.ky_flux':OMFITgacode,\
#                   'bin.cgyro.restart':OMFITgacode,'bin.cgyro.restart.old':OMFITgacode,\
#                   'input.cgyro':OMFITgacode,'input.cgyro.gen':OMFITgacode,\
#                   'out.cgyro.freq':OMFITgacode,'out.cgyro.info':OMFITgacode,'out.cgyro.time':OMFITgacode,'out.cgyro.timing':OMFITgacode,\
#                   'out.cgyro.egrid':OMFITgacode,'out.cgyro.equilibrium':OMFITgacode,'out.cgyro.grids':OMFITgacode,\
#                   'out.cgyro.hosts':OMFITgacode,'out.cgyro.memory':OMFITgacode,'out.cgyro.mpi':OMFITgacode,\
#                   'out.cgyro.prec':OMFITgacode,'out.cgyro.version':OMFITgacode,\
#                   'out.cgyro.tag':OMFITgacode,'run_log':OMFITgacode
#                  }
icgyro=setup['icgyro']
rmtsetup=root['SETTINGS']['REMOTE_SETUP']
manifest = root.get('RUN_MANIFEST', None)
if not manifest:
    raise ValueError('No run manifest. Prepare a run first; importing old result directories requires an explicit manifest.')
rmtserver = manifest['server']
rmtworkdir = manifest['workDir']
rmttunnel = manifest['tunnel']
failed_cases = []
local = rmtserver == 'localhost'
caseTag = manifest['case_tag']
caseRoot = root['Cases']
parentdir = list(manifest['points'])
loaded_cases = []
if icgyro == 1:
    scheduler = str(manifest.get('scheduler', '') or rmtsetup.get(
        str(manifest.get('serverPicker', '') or ''), {}).get('scheduler', '') or '').lower()
    failed_cases = probe_run_outputs(scheduler, str(manifest.get('job_id', '') or ''))
    if failed_cases:
        # Keep exception text ASCII: older OMFIT script serialization can
        # replace non-ASCII task-script messages with question marks.
        raise RuntimeError(failure_report(failed_cases))
for itemdir in parentdir:
    print("Loading "+itemdir)
    result_dir = path_join(rmtworkdir, itemdir)
    if local and not os.path.isdir(result_dir):
        print("Missing local result directory: "+result_dir)
        failed_cases.append(itemdir)
        continue
    try:
        if icgyro==0:
            if local:
                candidate=OMFITgyro(result_dir,extra_files=['RESTART_0','RESTART_tag_0','RESTART_1','RESTART_tag_1','restart.dat'])
            else:
                candidate=OMFITgyro([rmtworkdir+'/'+itemdir,rmtserver,rmttunnel],extra_files=['RESTART_0','RESTART_tag_0','RESTART_1','RESTART_tag_1','restart.dat'])
        else:
            if local:
                candidate=OMFITcgyro(result_dir,extra_files=['bin.cgyro.restart','bin.cgyro.restart.old','run_log','cgyro.exit'])
            else:
                candidate=OMFITcgyro([rmtworkdir+'/'+itemdir,rmtserver,rmttunnel],extra_files=['bin.cgyro.restart','bin.cgyro.restart.old','run_log','cgyro.exit'])
        # Force lazy parsing before replacing a preserved node is considered successful.
        if candidate['n_time'] < 1:
            raise ValueError('Result contains no time samples')
        caseRoot[caseTag][itemdir] = candidate
        loaded_cases.append(itemdir)
    except Exception as exc:
        print('Failed to load ' + itemdir + ': ' + str(exc))
        failed_cases.append(itemdir)
root['RUN_MANIFEST']['loaded_points'] = loaded_cases
root['RUN_MANIFEST']['failed_points'] = failed_cases
if failed_cases:
    raise RuntimeError(failure_report(failed_cases) + '\nPrevious archived results are preserved.')
root['RUN_MANIFEST']['status'] = 'loaded'
