"""Check version-specific restart histories against the selected installation.

Only an explicit restart preparation calls this read-only probe. It never runs
CGYRO or inspects other archived points. Standard CGYRO does not require the
custom timing.debug stream; do not invent that history for older installations.
"""
from builtins import OSError, RuntimeError, ValueError, len, str
import os
import zipfile
from OMFITlib_cgyro_launch import _invocation
from OMFITlib_cgyro_run_state import native_remote_execute, quote, text_output

DEBUG_TIMING = 'out.cgyro.timing.debug'


def requirement_command(runtime):
    lines, index, raw, words, _ = _invocation(runtime['executable'])
    launcher = raw[1] if words[0] in ('exec', 'command') else raw[0]
    # Run the configured environment/preamble, never the solver invocation.
    setup = str(runtime.get('environment', '') or ':') + '\n' + '\n'.join(lines[:index]) + '\n'
    return setup + 'cgyro_launcher=$(command -v -- ' + launcher + ') || exit 1\n' + r'''
if [ -n "${GACODE_ROOT:-}" ] && [ "$cgyro_launcher" -ef "$GACODE_ROOT/cgyro/bin/cgyro" ]; then
  cgyro_binary="$GACODE_ROOT/cgyro/src/cgyro"
  [ -r "$cgyro_binary" ] || { echo 'Cannot inspect the selected CGYRO executable' >&2; exit 1; }
  if LC_ALL=C grep -aFq -- 'out.cgyro.timing.debug' "$cgyro_binary"; then
    printf 'CGYRO_RESTART_DEBUG|required\n'
  else
    status=$?
    [ "$status" = 1 ] || exit "$status"
    printf 'CGYRO_RESTART_DEBUG|absent\n'
  fi
else
  printf 'CGYRO_RESTART_DEBUG|unknown\n'
fi
'''


def _requirement(runtime, ui, server, workdir, tunnel, cache):
    if 'debug_timing' not in cache:
        output, errors = [], []
        code = native_remote_execute(ui, server, '/bin/bash -c ' + quote(requirement_command(runtime)),
            workdir, tunnel, quiet=True, ignoreReturnCode=True, use_bang_command=False,
            std_out=output, std_err=errors)
        states = [line.partition('|')[2] for line in text_output(output).splitlines()
                  if line.startswith('CGYRO_RESTART_DEBUG|')]
        if code != 0 or len(states) != 1 or states[0] not in ('required', 'absent', 'unknown'):
            raise RuntimeError('Could not check CGYRO restart histories; no job submitted. ' + text_output(errors))
        cache['debug_timing'] = states[0]
    return cache['debug_timing']


def _missing_message(point):
    return ('{}: 所选 CGYRO 版本续算需要 {}，此点归档缺失或为空。'
            '需从此点原始计算目录补收匹配检查点的文件后再续算；'
            '重复“收集未归档结果”不会补齐已归档文件。现有结果保留，此点不提交。').format(point, DEBUG_TIMING)


def check_debug_history(directory, point, runtime, ui, server, workdir, tunnel, cache):
    """Probe at most once per preparation, only if this point lacks the file."""
    path = os.path.join(directory, DEBUG_TIMING)
    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return
    if _requirement(runtime, ui, server, workdir, tunnel, cache) == 'required':
        raise ValueError(_missing_message(point))


def filter_restart_points(plan, runtime, ui, server, workdir, tunnel, cache):
    """Reject only selected points missing an installation-specific history.

    The plan already binds exact RUN_DB owners. This checks their own directory
    or ZIP member list, never a parent job or a different result at that ky.
    Keep coverage/rows as metadata so rejected points cannot appear completed.
    """
    retained = []
    for point in plan['points']:
        source = plan['sources'][point]
        try:
            if source['mode'] == 'checkpoint':
                check_debug_history(source['directory'], point, runtime, ui, server, workdir, tunnel, cache)
            elif source['mode'] == 'checkpoint_zip':
                with zipfile.ZipFile(source['zip']) as archive:
                    present = DEBUG_TIMING in archive.namelist() and archive.getinfo(DEBUG_TIMING).file_size > 0
                if not present and _requirement(runtime, ui, server, workdir, tunnel, cache) == 'required':
                    raise ValueError(_missing_message(point))
            # A retained input without a checkpoint starts fresh, so no old
            # timer stream is required. prepare_point verifies its frozen ZIP.
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            plan.setdefault('rejected', {})[point] = str(error)
            continue
        retained.append(point)
    if not retained:
        raise ValueError('No selected point can restart; no job submitted:\n' +
                         '\n'.join(plan.get('rejected', {}).values()))
    plan['points'] = retained
    return plan
