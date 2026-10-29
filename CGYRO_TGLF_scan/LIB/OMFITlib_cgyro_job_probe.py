"""Read-only Slurm identity and bounded file probes for job-ID recovery.

No shell received from a manifest is ever executed. Paths are quoted, IDs
validated, and a failed query is distinct from an empty scheduler response.
"""
from builtins import RuntimeError, ValueError, any, dict, int, len, list, set, str
import base64
import posixpath
import re
from OMFITlib_cgyro_run_state import (array_task_ranges, native_remote_execute, quote,
                                     slurm_account_query, slurm_queue_query, text_output)
from OMFITlib_cgyro_recovery_manifest import (MAX_MANIFEST_BYTES, MAX_SCRIPT_BYTES, SIDECAR,
                                             absolute_remote_path, job_number)


def remote_text(ui, endpoint, script):
    output, errors = [], []
    code = native_remote_execute(ui, endpoint['server'], '/bin/bash -c ' + quote(script), '/',
        endpoint.get('tunnel', ''), quiet=True, ignoreReturnCode=True,
        use_bang_command=False, std_out=output, std_err=errors)
    if code != 0:
        raise RuntimeError('CGYRO recovery query failed; records are unchanged.\n' + text_output(errors))
    return text_output(output)


def frame(name, command):
    return "printf '\n__CGYRO_RECOVERY_" + name + "_BEGIN__\n'\n" + command + "\nprintf '\n__CGYRO_RECOVERY_" + name + "_END__\n'\n"


def section(text, name):
    begin, end = '__CGYRO_RECOVERY_' + name + '_BEGIN__\n', '\n__CGYRO_RECOVERY_' + name + '_END__'
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError('Incomplete recovery response: ' + name)
    return text.split(begin, 1)[1].split(end, 1)[0]


def identity_command(job_id):
    job_id = job_number(job_id)
    return ('set -e\nfor name in ${!SQUEUE_@} ${!SACCT_@}; do unset "$name"; done\nunset SLURM_CLUSTERS\n'
        + slurm_queue_query(job_id) + slurm_account_query(job_id) + '\n' + frame('USER', 'id -un')
        + frame('QUEUE', 'cgyro_queue_rows ' + quote('%i|%u|%T|%Z'))
        # Prefer expanded accounting; old clients may retain grouped IDs.
        + frame('ACCOUNT', "cgyro_account_rows 'JobID%128,User%128,State%64,WorkDir%4096'"))


def parse_identity(text, job_id):
    """Require one owner and directory across live and historical records."""
    job_id = job_number(job_id)
    user = section(text, 'USER').strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', user):
        raise ValueError('Could not determine the authenticated remote account.')
    rows = []
    for source in ('QUEUE', 'ACCOUNT'):
        for line in section(text, source).splitlines():
            if not line.strip():
                continue
            fields = [field.strip() for field in line.split('|')]
            match = re.fullmatch(re.escape(job_id) + r'(?:_([0-9]+|\[[^\]]+\](?:%[0-9]+)?))?', fields[0])
            selector = match.group(1) if match is not None else None
            if (len(fields) != 4 or match is None
                    or (selector and selector.startswith('[') and array_task_ranges(selector) is None)):
                raise ValueError('Unexpected or truncated scheduler recovery row: ' + line)
            if fields[1] != user:
                raise ValueError('该作业不属于当前连接用户；未恢复任何记录。')
            absolute_remote_path(fields[3])
            rows.append(dict(job_id=fields[0], user=fields[1], state=fields[2], workdir=fields[3]))
    if not rows:
        raise ValueError('该服务器没有此作业的队列或记账记录，请检查服务器和主作业号。')
    directories = set(row['workdir'] for row in rows)
    if len(directories) != 1:
        raise ValueError('The job ID has multiple working directories; recovery is ambiguous.')
    workdir = directories.pop()
    match = re.search(r'/([a-f0-9]{32})(?:/retry_[A-Za-z0-9_]+)?$', workdir)
    if not match:
        raise ValueError('该作业不是受支持的 CGYRO 扫描目录，无法从当前参数推测原扫描。')
    return dict(job_id=job_id, user=user, workdir=workdir, token=match.group(1), rows=rows)


def _owned_file(path, limit, encoded=False):
    path = quote(absolute_remote_path(path))
    return ('test -f {p} && test -O {p} && test ! -L {p}\n'
            'test "$(stat -c %s -- {p})" -le {limit}\n{reader} -- {p}').format(
                p=path, limit=limit, reader='base64' if encoded else 'cat')


def files_command(identity, manifest_path=''):
    directory, token = identity['workdir'], identity['token']
    # Exact OMFIT staging shapes avoid recursively traversing result arrays or
    # scanning another user's /tmp. The override supports nonstandard TMPDIRs.
    patterns = [quote(directory + '/' + SIDECAR), quote(directory + '/manifest.json')]
    if manifest_path:
        patterns = [quote(absolute_remote_path(manifest_path))]
    else:
        patterns.extend([
            '"/tmp/$(id -un)/OMFIT"/OMFIT_*/project/runs/*/*/p*/runs/' + token + '/manifest.json',
            '"${TMPDIR:-/tmp}/$(id -un)/OMFIT"/OMFIT_*/project/runs/*/*/p*/runs/' + token + '/manifest.json'])
    candidates = ('shopt -s nullglob\nfor candidate in ' + ' '.join(patterns) + '; do\n'
        ' if [ -f "$candidate" ] && [ -O "$candidate" ] && [ ! -L "$candidate" ]; then\n'
        '  printf "%s\\n" "$candidate"\n fi\ndone')
    nonce = 'if [ -f {p} ]; then cat -- {p}; fi'.format(p=quote(directory + '/.cgyro_submit.identity'))
    return ('set -e\ntest -d {p} && test -O {p} && test ! -L {p}\n'.format(p=quote(directory))
        + frame('RECEIPT', _owned_file(directory + '/.cgyro_submit.out', 65536))
        + frame('SCRIPT', _owned_file(directory + '/scan.pbs', MAX_SCRIPT_BYTES, encoded=True))
        + frame('NONCE', nonce) + frame('CANDIDATES', candidates))


def read_remote_manifest(ui, endpoint, path):
    text = remote_text(ui, endpoint, 'set -e\n' + frame('JSON', _owned_file(path, MAX_MANIFEST_BYTES)))
    return section(text, 'JSON')


def script_content(text):
    # Native remote_execute can deliver stdout in line chunks. Base64 preserves
    # the exact script bytes and final newline independently of those chunks.
    encoded = ''.join(section(text, 'SCRIPT').split())
    return base64.b64decode(encoded, validate=True).decode('utf-8')


def input_inventory_command(manifest):
    base = absolute_remote_path(manifest.get('source_workDir', manifest['workDir']))
    names = ['scan.pbs'] + [point + '.zip' for point in manifest['points']]
    return ('set -e\ncd -- ' + quote(base) + '\n' + frame('INPUTS',
        'for file in ' + ' '.join(quote(name) for name in names) + '; do\n'
        ' if [ -f "$file" ] && [ -O "$file" ] && [ ! -L "$file" ]; then\n'
        '  printf "%s|%s\\n" "$file" "$(stat -c %s -- "$file")"\n'
        ' fi\ndone'))


def parse_inventory(text, manifest):
    allowed = set(['scan.pbs'] + [point + '.zip' for point in manifest['points']])
    sizes = {}
    for row in section(text, 'INPUTS').splitlines():
        if not row:
            continue
        fields = row.split('|')
        if len(fields) != 2 or fields[0] not in allowed or fields[0] in sizes or not fields[1].isdigit():
            raise ValueError('Invalid recovery input inventory.')
        sizes[fields[0]] = int(fields[1])
    if 'scan.pbs' not in sizes:
        raise ValueError('The original submission script is missing from the remote run.')
    return sizes
