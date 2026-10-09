"""Maintain installation roots and inspect files without running GACODE."""
from builtins import all, any, dict, len, list, ord, set, str, zip
from collections import OrderedDict
import copy
from datetime import datetime, timezone
from pathlib import PurePosixPath
import re
import shlex


PROGRAMS = OrderedDict([
    ('cgyro', ('CGYRO', ('cgyro/bin/cgyro', 'cgyro/src/cgyro'))),
    ('tgyro', ('TGYRO', ('tgyro/bin/tgyro', 'tgyro/src/tgyro_main',
                         'tglf/bin/tglf', 'tglf/src/tglf_mpi'))),
    ('tglf', ('TGLF', ('tglf/bin/tglf', 'tglf/src/tglf'))),
    ('profiles', ('profiles_gen', ('profiles_gen/bin/profiles_gen',
                                  'profiles_gen/src/prgen', 'profiles_gen/locpargen/locpargen'))),
])
INSTALL_DEFAULTS = dict(gacode_scan_dir='', gacode_installs={},
                        cgyro_install='', tgyro_install='', tglf_install='', profiles_install='')


def valid_path(value):
    value = str(value or '').strip()
    path = PurePosixPath(value)
    return (path.is_absolute() and str(path) != '/' and '..' not in path.parts
            and not any(ord(char) < 32 for char in value))


def script_root(script):
    """Migrate only a literal absolute GACODE_ROOT; never evaluate shell code."""
    match = re.search(r'^\s*(?:export\s+)?GACODE_ROOT\s*=\s*(.*?)\s*(?:;\s*)?$', str(script or ''), re.M)
    if match is None:
        return ''
    try:
        words = shlex.split(match.group(1), comments=True)
    except ValueError:
        return ''
    value = words[0] if len(words) == 1 else ''
    return value.rstrip('/') if valid_path(value) and not any(c in value for c in '$`') else ''


def initialize_installations(config, factory=dict):
    fresh = 'gacode_installs' not in config
    for key, value in INSTALL_DEFAULTS.items():
        config.setdefault(key, copy.deepcopy(value))
    if fresh:
        root = script_root(config.get('environment', ''))
        if root:
            name = PurePosixPath(root).name
            config['gacode_installs'] = factory()
            config['gacode_installs'][name] = root
            config['gacode_scan_dir'] = str(PurePosixPath(root).parent)
            for program in PROGRAMS:
                config[program + '_install'] = name
    return config['gacode_installs']


def selected_root(config, program):
    name = str(config.get(program + '_install', '') or '')
    return str(config.get('gacode_installs', {}).get(name, '') or '').strip()


def installation_issues(config, detection=None):
    issues = []
    installs = config.get('gacode_installs', {})
    for name, root in installs.items():
        if not valid_path(root):
            issues.append('GACODE 路径需要为绝对路径：' + str(name))
    current = (detection or {}).get('endpoint', {})
    same_server = all(str(current.get(key, '') or '') == str(config.get(key, '') or '')
                      for key in ('server', 'tunnel'))
    entries = (detection or {}).get('entries', {}) if same_server else {}
    for program, (label, _) in PROGRAMS.items():
        name = str(config.get(program + '_install', '') or '')
        if not name:
            continue
        if name not in installs:
            issues.append(label + ' 的安装已移除，请重新选择')
            continue
        record = entries.get(str(installs[name]), {})
        if record and not record.get(program, False):
            missing = record.get('missing', {}).get(program, [])
            issues.append(label + ' 在 ' + name + ' 中不可用：' + '、'.join(missing))
    return issues


def probe_script(config, scan=True):
    """Bounded Bash inventory, with quoted paths and machine-readable markers."""
    installs = config.get('gacode_installs', {})
    if any(not valid_path(path) for path in installs.values()):
        raise ValueError('请先填写有效的 GACODE 绝对路径')
    lines = ['set -e', 'probe_install() {', '  local root="$1"',
             '  printf "OMFIT_GACODE\\t%s" "$root"',
             '  if [ -d "$root" ]; then printf "\\t1"; else printf "\\t0"; fi',
             '  if [ -r "$root/shared/bin/gacode_setup" ]; then printf "\\t1"; else printf "\\t0"; fi']
    files = list(OrderedDict.fromkeys(file for _, paths in PROGRAMS.values() for file in paths))
    for file in files:
        path = '"$root"/' + shlex.quote(file)
        lines.append('  if [ -f ' + path + ' ] && [ -x ' + path + ' ]; then printf "\\t1"; else printf "\\t0"; fi')
    lines.extend(['  printf "\\n"', '}'])
    if scan:
        parent = str(config.get('gacode_scan_dir', '') or '').strip()
        if not valid_path(parent):
            raise ValueError('请填写 GACODE 搜索目录的绝对路径')
        lines.extend(['parent=' + shlex.quote(parent),
                      '[ -d "$parent" ] || { echo "GACODE search directory does not exist." >&2; exit 1; }',
                      'shopt -s nullglob nocaseglob', 'count=0',
                      'for root in "$parent"/gacode*; do',
                      '  [ -d "$root" ] || continue', '  count=$((count+1))',
                      '  [ "$count" -le 128 ] || { echo "Too many GACODE directories; narrow the search." >&2; exit 1; }',
                      '  probe_install "$root"', 'done'])
    lines.extend('probe_install ' + shlex.quote(str(path)) for path in installs.values())
    lines.append('printf "OMFIT_GACODE_END\\n"')
    return '\n'.join(lines) + '\n'


def parse_probe(output):
    files = list(OrderedDict.fromkeys(file for _, paths in PROGRAMS.values() for file in paths))
    records, complete = {}, False
    # Native OMFIT captures stdout with split('\n'), stripping line endings.
    for line in '\n'.join(output).splitlines():
        if line.strip() == 'OMFIT_GACODE_END':
            complete = True
        if not line.startswith('OMFIT_GACODE\t'):
            continue
        fields = line.split('\t')
        if len(fields) != len(files) + 4 or not valid_path(fields[1]):
            raise ValueError('服务器返回的 GACODE 检测信息不完整')
        flags = fields[2:]
        if any(value not in ('0', '1') for value in flags):
            raise ValueError('服务器返回的 GACODE 检测状态无效')
        available = dict(zip(files, flags[2:]))
        record = dict(exists=flags[0] == '1', setup=flags[1] == '1', missing={})
        for program, (_, paths) in PROGRAMS.items():
            missing = ([] if record['setup'] else ['shared/bin/gacode_setup'])
            missing += [path for path in paths if available[path] != '1']
            record[program] = not missing and record['exists']
            record['missing'][program] = missing
        records[fields[1]] = record
    if not complete:
        raise ValueError('GACODE 自动检测未完成；原安装列表保留')
    return records


def merge_probe(config, records, factory=dict):
    installs = config['gacode_installs']
    known = set(str(path) for path in installs.values())
    added = 0
    for root, record in records.items():
        if root in known or not record['exists']:
            continue
        name = PurePosixPath(root).name
        key, index = name, 2
        while key in installs:
            key, index = name + '_' + str(index), index + 1
        installs[key] = root
        known.add(root)
        added += 1
    detection = factory()
    detection.update(dict(endpoint={key: str(config.get(key, '') or '') for key in ('server', 'tunnel')},
                          checked=datetime.now(timezone.utc).isoformat(), entries=records))
    return added, detection


def choices(config, detection=None, program=None):
    result = OrderedDict() if program is None else OrderedDict([('沿用环境脚本', '')])
    entries = (detection or {}).get('entries', {})
    if (detection or {}).get('endpoint', {}) != {key: str(config.get(key, '') or '') for key in ('server', 'tunnel')}:
        entries = {}
    for name, root in config.get('gacode_installs', {}).items():
        record = entries.get(str(root), {})
        if not record:
            status = '未检测'
        elif program:
            status = '可用' if record.get(program, False) else '缺少程序'
        else:
            status = ' / '.join(label for key, (label, _) in PROGRAMS.items() if record.get(key, False)) or '无可用程序'
        result[str(name) + '（' + status + '）'] = name
    return result


def program_guard(program):
    """Repeat file checks on the execution node, including legacy environments."""
    label, files = PROGRAMS[program]
    lines = ['[ -n "${GACODE_ROOT:-}" ] || { echo "GACODE_ROOT is not set for ' + label + '." >&2; exit 1; }']
    for file in files:
        path = '"$GACODE_ROOT"/' + shlex.quote(file)
        lines.append('[ -f ' + path + ' ] && [ -x ' + path + ' ] || { printf "Missing ' + label
                     + ' executable: %s/' + file + '\\n" "$GACODE_ROOT" >&2; exit 1; }')
    return '\n'.join(lines) + '\n'


def program_environment(config, program):
    common = str(config.get('environment', '') or '').strip() or ':'
    if program not in PROGRAMS:
        return common
    root = selected_root(config, program)
    if root:
        if not valid_path(root):
            raise ValueError('GACODE 安装路径无效：' + root)
        common += ('\nexport GACODE_ROOT=' + shlex.quote(root)
                   + '\n[ -r "$GACODE_ROOT/shared/bin/gacode_setup" ] || { echo "Missing gacode_setup." >&2; exit 1; }'
                   + '\nsource "$GACODE_ROOT/shared/bin/gacode_setup"\nhash -r')
    return common + '\n' + program_guard(program).rstrip()
