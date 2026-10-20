"""Submission receipts and recovery by the saved endpoint and working directory.

The gate is never removed: either the submitter owns it or recovery seals it
before submission. An empty log alone cannot resolve a legacy attempt.
"""
from builtins import RuntimeError, ValueError, dict, iter, len, next, set, sorted, str
import posixpath
import re
from OMFITlib_cgyro_run_state import quote, text_output


PROTOCOL = 'gate-v1'


def identity(manifest):
    nonce = str(manifest.get('submission_nonce', ''))
    if manifest.get('submission_protocol', '') != PROTOCOL or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        raise ValueError('This attempt has no verifiable submission gate.')
    return nonce


def submit_command(manifest, command):
    """Anchor cwd after login startup and enter the once-only scheduler gate."""
    nonce = identity(manifest)
    script = 'cd -- ' + quote(manifest['workDir']) + ' || exit 72\nnonce=' + quote(nonce) + '''
[ "$(cat -- .cgyro_submit.identity)" = "$nonce" ] || exit 73
mkdir -- .cgyro_submit.gate || exit 74
''' + 'LC_ALL=C ' + command + ''' > .cgyro_submit.out 2>&1
status=$?
printf '%s\\n' "$status" > .cgyro_submit.gate/exit
cat -- .cgyro_submit.out
exit "$status"
'''
    return '/bin/bash -lc ' + quote(script)


def seal_command(manifest):
    """Only the winner of mkdir can prove no gated submitter will run later."""
    nonce = identity(manifest)
    script = 'cd -- ' + quote(manifest['workDir']) + ' || exit 72\nnonce=' + quote(nonce) + '''
[ "$(cat -- .cgyro_submit.identity)" = "$nonce" ] || exit 73
if mkdir -- .cgyro_submit.gate 2>/dev/null; then
    printf '%s\\n' "$nonce" > .cgyro_submit.gate/sealed || exit 75
fi
if [ -f .cgyro_submit.gate/sealed ] && [ "$(cat -- .cgyro_submit.gate/sealed)" = "$nonce" ]; then
    printf 'CGYRO_NOT_SUBMITTED|%s\\n' "$nonce"
fi
'''
    return '/bin/bash -c ' + quote(script)


def discovery_command(manifest):
    """Read both live and accounting rows; never infer non-submission from none."""
    directory = str(manifest.get('workDir', ''))
    if not directory.startswith('/') or '\n' in directory or '|' in directory:
        raise ValueError('Recovery requires the original absolute working directory.')
    script = '''target=DIRECTORY
physical=$(cd -- "$target" 2>/dev/null && pwd -P) || physical="$target"
for name in ${!SQUEUE_@} ${!SACCT_@}; do unset "$name"; done
unset SLURM_CLUSTERS
user=$(id -un) || exit 71
matching_rows() {
    while IFS='|' read -r job state directory; do
        if [ "$directory" = "$target" ] || [ "$directory" = "$physical" ]; then
            printf 'CGYRO_JOB|%s|%s\\n' "$job" "$state"
        fi
    done
}
if rows=$(LC_ALL=C squeue --local -h --states=all -u "$user" -o '%F|%T|%Z' 2>&1); then
    printf 'CGYRO_QUEUE_OK\\n'; printf '%s\\n' "$rows" | matching_rows
else printf 'CGYRO_QUEUE_ERROR\\n%s\\n' "$rows"; fi
if rows=$(LC_ALL=C sacct -X -n -P -u "$user" -S now-7days --format=JobID%128,State%64,WorkDir%4096 2>&1); then
    printf 'CGYRO_ACCOUNT_OK\\n'; printf '%s\\n' "$rows" | matching_rows
else printf 'CGYRO_ACCOUNT_ERROR\\n%s\\n' "$rows"; fi
'''
    return '/bin/bash -c ' + quote(script.replace('DIRECTORY', quote(posixpath.normpath(directory))))


def discover_submission(manifest, ui):
    output, errors = [], []
    code = ui.remote_execute(manifest['server'], discovery_command(manifest), '/',
        manifest.get('tunnel', ''), quiet=True, ignoreReturnCode=True,
        use_bang_command=False, std_out=output, std_err=errors)
    raw = text_output(output)
    manifest['submission_discovery'] = dict(raw=raw, errors=text_output(errors), days=7)
    markers = set(raw.splitlines())
    if code != 0 or not {'CGYRO_QUEUE_OK', 'CGYRO_ACCOUNT_OK'} <= markers:
        raise RuntimeError('Submission lookup failed; no submission was cleared.\n' + raw + '\n' + text_output(errors))
    jobs = set()
    for line in raw.splitlines():
        if line.startswith('CGYRO_JOB|'):
            parts = line.split('|')
            match = re.fullmatch(r'([0-9]+)(?:_[0-9]+|_\[[0-9,:%-]+\])?', parts[1]) if len(parts) == 3 else None
            if match is None:
                raise ValueError('Unrecognized allocation identity: ' + line)
            jobs.add(match.group(1))
    if len(jobs) > 1:
        raise ValueError('Several allocations use this directory; no job was chosen: ' + ', '.join(sorted(jobs)))
    return next(iter(jobs)) if jobs else ''


def seal_unstarted(manifest, ui):
    if manifest.get('submission_protocol', '') != PROTOCOL:
        return False  # A pre-gate submitter would not respect a new recovery seal.
    output, errors = [], []
    code = ui.remote_execute(manifest['server'], seal_command(manifest), '/',
        manifest.get('tunnel', ''), quiet=True, ignoreReturnCode=True,
        use_bang_command=False, std_out=output, std_err=errors)
    manifest['submission_seal_output'] = text_output([output, errors])
    return code == 0 and 'CGYRO_NOT_SUBMITTED|' + identity(manifest) in text_output(output).splitlines()
