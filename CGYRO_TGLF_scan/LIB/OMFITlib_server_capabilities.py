"""Read server capabilities, bind them to an endpoint, and adapt resource drafts.

Detection never loads user environment scripts, changes remote files or submits
jobs. Login limits are evidence for the UI, not limits to freeze into a batch
job: the generated process-limit preamble inspects its own allocation again.
"""
from builtins import KeyError, TypeError, ValueError, ZeroDivisionError, dict, hasattr, int, len, max, min, set, str
from datetime import datetime, timezone
import re

VERSION = 1
TOOLS = ('sbatch', 'sinfo', 'qsub', 'mpiexec', 'mpirun', 'srun')


def probe_script():
    """Bound controller queries, retaining an explicit unknown status on failure."""
    return r'''
printf 'OMFIT_SERVER\t1\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(hostname)" "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 0)" "$(ulimit -Sn)" "$(ulimit -Hn)" "$(ulimit -Ss)" "$(ulimit -Hs)"
omfit_find_tool() {
  command -v "$1" 2>/dev/null && return 0
  if [ -x "/opt/gridview/slurm/bin/$1" ]; then printf '%s\n' "/opt/gridview/slurm/bin/$1"; fi
  return 0
}
for tool in sbatch sinfo qsub mpiexec mpirun srun; do
  printf 'OMFIT_SERVER_TOOL\t%s\t%s\n' "$tool" "$(omfit_find_tool "$tool")"
done
sinfo_path=$(omfit_find_tool sinfo)
if [ -n "$sinfo_path" ] && command -v timeout >/dev/null 2>&1; then
  if rows=$(LC_ALL=C timeout 12s "$sinfo_path" --local -h -e -o '%P|%c|%m|%l|%a|%B' 2>/dev/null); then
    while IFS= read -r row; do
      [ -z "$row" ] || printf 'OMFIT_SERVER_QUEUE\t%s\n' "$row"
    done <<< "$rows"
    printf 'OMFIT_SERVER_SLURM\tok\n'
  else
    printf 'OMFIT_SERVER_SLURM\tunavailable\n'
  fi
else
  printf 'OMFIT_SERVER_SLURM\tunavailable\n'
fi
unset -f omfit_find_tool
printf 'OMFIT_SERVER_END\n'
'''


def _integer(value, maximum=10**9):
    if not re.fullmatch(r'[0-9]+', str(value)) or not 0 <= int(value) <= maximum:
        raise ValueError('服务器检测返回了无效的数值')
    return int(value)


def time_seconds(value):
    """Parse Slurm minute or [days-]hours:minutes:seconds forms conservatively."""
    value = str(value).strip().lower()
    if value in ('unlimited', 'infinite', 'n/a', 'partition_limit', ''):
        return None
    if re.fullmatch(r'[0-9]+', value):
        return int(value) * 60
    match = re.fullmatch(r'(?:(\d+)-)?(\d+):(\d+)(?::(\d+))?', value)
    if not match:
        return None
    days, first, second, third = match.groups()
    if third is None and days is None:  # Slurm's minutes:seconds spelling.
        return int(first) * 60 + int(second)
    return int(days or 0) * 86400 + int(first) * 3600 + int(second) * 60 + int(third or 0)


def parse_probe(output, config):
    profile, complete, rows = {}, False, 0
    for line in '\n'.join(output).splitlines():
        fields = line.split('\t')
        if fields[0] == 'OMFIT_SERVER':
            if profile or len(fields) != 8 or fields[1] != str(VERSION):
                raise ValueError('服务器检测信息重复或不完整；原配置保留')
            for value in fields[4:]:
                if value != 'unlimited':
                    _integer(value, 2**63 - 1)
            profile = dict(version=VERSION, hostname=fields[2], login_cpus=_integer(fields[3]),
                limits=dict(nofile_soft=fields[4], nofile_hard=fields[5],
                            stack_soft=fields[6], stack_hard=fields[7]), tools={}, partitions={})
        elif fields[0] == 'OMFIT_SERVER_TOOL' and profile:
            if len(fields) != 3 or fields[1] not in TOOLS:
                raise ValueError('服务器工具检测信息无效；原配置保留')
            profile['tools'][fields[1]] = fields[2]
        elif fields[0] == 'OMFIT_SERVER_QUEUE' and profile:
            rows += 1
            values = fields[1].split('|') if len(fields) == 2 else []
            if rows > 8192 or len(values) != 6:
                raise ValueError('队列检测信息不完整或过多；原配置保留')
            name, cpus, memory, walltime, state, maximum = [value.strip() for value in values]
            default, name = name.endswith('*'), name.rstrip('*')
            if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.+-]*', name):
                raise ValueError('队列名称无效；原配置保留')
            cpus, memory = _integer(cpus), _integer(memory)
            if maximum.isdigit() and int(maximum) > 0:
                cpus = min(cpus, _integer(maximum))
            previous = profile['partitions'].get(name, {})
            profile['partitions'][name] = dict(cpus_per_node=min(previous.get('cpus_per_node', cpus), cpus),
                memory_mib=min(previous.get('memory_mib', memory), memory), wall_time=walltime,
                available=state == 'up', default=default or previous.get('default', False))
        elif fields[0] == 'OMFIT_SERVER_SLURM' and profile:
            if len(fields) != 2 or fields[1] not in ('ok', 'unavailable'):
                raise ValueError('Slurm 检测状态无效；原配置保留')
            profile['slurm_status'] = fields[1]
        elif line == 'OMFIT_SERVER_END':
            complete = True
    if (not complete or not profile or set(profile['tools']) != set(TOOLS)
            or 'slurm_status' not in profile):
        raise ValueError('服务器能力检测未完成；原配置保留')
    profile.update(dict(endpoint={key: str(config.get(key, '') or '') for key in ('server', 'tunnel')},
                        checked=datetime.now(timezone.utc).isoformat()))
    return profile


def matching_profile(config, detection):
    profile = detection.get('capabilities', {})
    endpoint = {key: str(config.get(key, '') or '') for key in ('server', 'tunnel')}
    return profile if (hasattr(profile, 'get') and profile.get('version', None) == VERSION
                       and profile.get('endpoint', {}) == endpoint) else {}


def _exceeds_time(requested, limit):
    maximum, value = time_seconds(limit), time_seconds(requested)
    return maximum is not None and (str(requested).lower() in ('infinite', 'unlimited')
                                     or value is not None and value > maximum)


def resource_issues(config, profile):
    """Only checked queue capacity is authoritative; login CPU count is not."""
    issues = []
    if str(config.get('scheduler', '')).lower() != 'slurm' or profile.get('slurm_status', '') != 'ok':
        return issues
    queue = str(config.get('queue', '') or '')
    partition = profile.get('partitions', {}).get(queue, None)
    if partition is None:
        return ['所选队列未在此次检测中找到，请核对队列或重新检测：' + queue]
    if not partition['available']:
        issues.append('所选队列当前未开放：' + queue)
    try:
        ranks = int(config.get('cores', config.get('ntasks_per_node', 1)))
        threads = int(config.get('cpus_per_task', 1))
        if ranks * threads > partition['cpus_per_node']:
            issues.append('每节点 MPI × 线程数超过队列已检测的 {} CPU/节点'.format(partition['cpus_per_node']))
    except (TypeError, ValueError):
        pass  # The existing settings validator supplies the numeric error.
    if _exceeds_time(config.get('wall_time', config.get('w', '')), partition['wall_time']):
        issues.append('运行时限超过队列上限：' + partition['wall_time'])
    return issues


def adapt_draft(config, profile):
    """The explicit Detect action edits only invalid resource draft values."""
    changes = []
    if config.get('scheduler', '') != 'slurm' or profile.get('slurm_status', '') != 'ok':
        return changes
    partitions = profile['partitions']
    if not config.get('queue', ''):
        defaults = [name for name, row in partitions.items() if row['default'] and row['available']]
        if len(defaults) == 1:
            config['queue'] = defaults[0]
            changes.append('队列 → ' + defaults[0])
    row = partitions.get(str(config.get('queue', '')), None)
    if not row or not row['available'] or not row['cpus_per_node']:
        return changes
    try:
        threads, ranks = int(config['cpus_per_task']), int(config['cores'])
        if threads > 0 and ranks > 0:
            for key, value, label in (('cpus_per_task', min(threads, row['cpus_per_node']), '线程/MPI'),
                    ('cores', min(ranks, max(1, row['cpus_per_node'] // min(threads, row['cpus_per_node']))), 'MPI/节点')):
                if int(config[key]) != value:
                    changes.append('{} {} → {}'.format(label, config[key], value))
                    config[key] = value
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        pass
    if _exceeds_time(config.get('wall_time', ''), row['wall_time']):
        changes.append('时限 {} → {}'.format(config['wall_time'], row['wall_time']))
        config['wall_time'] = row['wall_time']
    return changes


def summary(config, profile):
    if not profile:
        return ['尚未检测此服务器的运行能力。']
    limits = profile['limits']
    result = ['检测主机：' + profile['hostname'],
              '登录会话文件数：{} / {}（软 / 硬）'.format(limits['nofile_soft'], limits['nofile_hard']),
              '登录会话栈：{} / {} KiB（软 / 硬）'.format(limits['stack_soft'], limits['stack_hard'])]
    queue = str(config.get('queue', '') or '')
    row = profile.get('partitions', {}).get(queue, None)
    if row:
        result.append('{}：{} CPU/节点 · 内存 {} MiB/节点'.format(queue, row['cpus_per_node'], row['memory_mib']))
        result.append('队列最长时限：' + row['wall_time'])
    elif profile.get('slurm_status', '') != 'ok':
        result.append('队列信息未读取；保留原资源设置。')
    tools = [name for name in TOOLS if profile['tools'].get(name, '')]
    result.append('登录环境可见工具：' + ('、'.join(tools) or '未加载'))
    if profile.get('draft_changes', []):
        result.append('资源草稿已调整：' + '；'.join(profile['draft_changes']))
    return result
