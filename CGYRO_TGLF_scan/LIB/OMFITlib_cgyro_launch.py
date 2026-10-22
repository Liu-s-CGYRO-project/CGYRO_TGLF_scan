"""Keep Slurm allocations, GACODE arguments and checkpoint layouts consistent.

Resource fields own MPI/OpenMP counts. A command copied from an older project
must not freeze ``-n 16`` when the user selects 32 MPI tasks. NUMA placement is
left to the selected GACODE platform rather than carrying stale placement flags
alongside a changed allocation. No solver, scheduler or filesystem is accessed.
"""
from builtins import ValueError, any, dict, enumerate, int, len, list, next, str, tuple
import re
import shlex


_CALL = re.compile(r'''^\s*(?:(?:exec|command)\s+)?(?:"(?:[^"\n]*/)?cgyro"|'(?:[^'\n]*/)?cgyro'|(?:[^\s;&|]+/)?cgyro)(?=\s|$)''')
_WORD = re.compile(r'''(?:[^\s"'\\]|\\.|"(?:[^"\\]|\\.)*"|'[^']*')+''')
_MANAGED = ('-n', '-nomp', '-numa', '-mpinuma')


def _invocation(command):
    lines = str(command).strip().splitlines()
    matches = [(index, line) for index, line in enumerate(lines) if _CALL.match(line)]
    if len(matches) != 1:
        raise ValueError('CGYRO command must contain one direct cgyro -e invocation; put environment setup in the environment field.')
    index, line = matches[0]
    shlex.split(line, comments=True)  # Reject unbalanced quotes before retaining raw words.
    raw = _WORD.findall(line)
    comment = next((i for i, word in enumerate(raw) if word.startswith('#')), len(raw))
    tail, raw = raw[comment:], raw[:comment]
    words = [shlex.split(word)[0] for word in raw]
    if '-e' not in words or any(word in (';', '&&', '||', '|') for word in words):
        raise ValueError('CGYRO command must use cgyro -e without inline shell control operators.')
    return lines, index, raw, words, tail


def _options(words):
    result = {}
    for index, word in enumerate(words):
        if word not in _MANAGED:
            continue
        if word in result or index + 1 == len(words):
            raise ValueError('Missing or repeated CGYRO parallel option: ' + word)
        result[word] = (index, words[index + 1])
    return result


def command_template(command):
    """Migrate literal rank/thread counts while retaining nonparallel arguments.

Keep raw quoted words, paths and shell-variable references intact. Rejoining
shlex's decoded tokens would quote $GACODE_ROOT literally and break launchers.
The topology flags default to automatic placement in GACODE; retaining an old
``-mpinuma`` here can keep half a newly enlarged allocation unused.
"""
    lines, index, raw, words, tail = _invocation(command)
    options = _options(words)
    replacements = {'-n': '{mpi}', '-nomp': '{threads}'}
    result, position = [], 0
    while position < len(raw):
        word = words[position]
        if word in _MANAGED:
            value = options[word][1]
            if not re.fullmatch(r'[0-9]+|\{(?:mpi|threads|mpi_per_node)\}', value):
                raise ValueError('Use resource fields instead of a computed CGYRO parallel option: ' + word)
            if value.isdigit() and (int(value) < 0 or (word in replacements and int(value) < 1)):
                raise ValueError('Invalid CGYRO parallel option: ' + word)
            if word in replacements:
                result.extend((word, replacements[word]))
            position += 2
        else:
            result.append(raw[position])
            position += 1
    for option, placeholder in replacements.items():
        if option not in options:
            result.extend((option, placeholder))
    lines[index] = ' '.join(result + tail)
    return '\n'.join(lines)


def _positive(value, label):
    if not re.fullmatch(r'[1-9][0-9]*', str(value).strip()):
        raise ValueError(label + ' must be a positive integer')
    return int(value)


def launch_spec(config, setup=None):
    """Resolve one point's requested resources before staging any large inputs."""
    setup = {} if setup is None else setup
    scheduler = str(config.get('scheduler', '')).lower()
    if scheduler not in ('slurm', 'local'):
        raise ValueError('Managed CGYRO launch resources require Slurm or local execution.')
    if scheduler == 'local' and 'nodes' not in config and 'ntasks_per_node' not in config:
        # A standalone localhost command has no scheduler allocation to enlarge.
        # Retain its explicit size until the shared resource settings are applied.
        actual = command_layout(config.get('executable', ''))
        config = dict(config)
        config.update(dict(nodes=1, ntasks_per_node=actual['mpi_ranks']))
    nodes = _positive(config.get('nodes', setup.get('num_nodes', 1)), 'nodes')
    per_node = config.get('ntasks_per_node', setup.get('num_cores', 1))
    per_node = _positive(per_node, 'MPI ranks per node')
    threads = _positive(config.get('cpus_per_task', setup.get('cpus_per_task', 1)), 'threads per MPI rank')
    mpi = nodes * per_node
    template = command_template(config.get('executable', ''))
    executable = template.replace('{mpi}', str(mpi)).replace('{threads}', str(threads))
    executable = executable.replace('{mpi_per_node}', str(per_node))
    return dict(scheduler=scheduler, nodes=nodes, mpi_per_node=per_node,
                mpi_ranks=mpi, threads=threads, total_cpus=mpi * threads,
                template=template, executable=executable)


def command_layout(command):
    """Read actual arguments from an old command without changing their counts."""
    lines, index, raw, words, tail = _invocation(command)
    options = _options(words)
    counts = {key: _positive(options.get(key, (None, '1'))[1], key) for key in ('-n', '-nomp')}
    identity, position = [], 0
    while position < len(words):
        if words[position] in _MANAGED:
            position += 2
        else:
            identity.append(words[position])
            position += 1
    lines[index] = ' '.join(identity)
    return dict(mpi_ranks=counts['-n'], threads=counts['-nomp'], identity='\n'.join(lines))


def validate_checkpoint_runtime(previous, current, has_checkpoint=True):
    """Compare actual MPI/OMP counts, not historically incorrect allocations.

A run that requested 32 CPUs but launched 16 MPI ranks has a 16-rank execution
identity. Reject a silent change to 32 during continuation. Correcting just the
allocation to 16 is allowed when the executable/environment and actual layout
stay the same. Unknown legacy commands keep the previous conservative checks.
"""
    if not previous:
        return
    old_command, new_command = previous.get('executable', ''), current.get('executable', '')
    try:
        old, new = command_layout(old_command), command_layout(new_command)
    except ValueError:
        if any(value is not None and current.get(key, None) != value for key, value in previous.items()):
            raise ValueError('Restore the original checkpoint execution configuration before continuing.')
        return
    if has_checkpoint and (old['mpi_ranks'] != new['mpi_ranks'] or old['threads'] != new['threads']):
        raise ValueError('Checkpoint used {} MPI x {} threads; requested {} MPI x {} threads. '
                         'Restore its actual MPI/thread counts to continue; previous results are preserved.'.format(
                             old['mpi_ranks'], old['threads'], new['mpi_ranks'], new['threads']))
    if old['identity'] != new['identity'] or previous.get('environment', None) != current.get('environment', None):
        raise ValueError('Restore the original checkpoint executable and environment before continuing.')


def validate_slurm_script(script):
    """Block automatic retries of a frozen script with mismatched resources."""
    def directive(name, default=None):
        match = re.search(r'^#SBATCH\s+--' + name + r'(?:=|\s+)([0-9]+)\s*$', script, re.MULTILINE)
        return _positive(match.group(1), name) if match else default
    nodes = directive('nodes')
    per_node = directive('ntasks-per-node')
    total = directive('ntasks', nodes * per_node if nodes and per_node else None)
    threads = directive('cpus-per-task', 1)
    actual = command_layout(script)
    if total is None or (nodes and per_node and total != nodes * per_node):
        raise ValueError('Cannot establish the original Slurm allocation; retry was not submitted.')
    if total != actual['mpi_ranks'] or threads != actual['threads']:
        raise ValueError('Saved script requests {} MPI x {} threads but starts {} MPI x {} threads. '
                         'Create a resource-aligned run instead of retrying this old script.'.format(
                             total, threads, actual['mpi_ranks'], actual['threads']))
    return actual


def slurm_guard(spec):
    """Fail before solver startup if Slurm does not supply the requested layout."""
    return '''
if [ "${{SLURM_NTASKS:-}}" != "{mpi_ranks}" ] || [ "${{SLURM_CPUS_PER_TASK:-1}}" != "{threads}" ]; then
  echo "CGYRO resource mismatch: expected {mpi_ranks} MPI x {threads} threads; SLURM_NTASKS=${{SLURM_NTASKS:-unset}}, SLURM_CPUS_PER_TASK=${{SLURM_CPUS_PER_TASK:-unset}}" >&2
  exit 1
fi
echo "CGYRO resources: {mpi_ranks} MPI x {threads} threads = {total_cpus} CPUs; {nodes} node(s)"
'''.format(**spec)
