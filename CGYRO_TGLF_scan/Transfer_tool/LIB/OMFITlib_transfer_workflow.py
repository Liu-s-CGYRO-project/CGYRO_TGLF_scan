"""Input preparation shared by the Transfer GUI and command box 1."""
from builtins import any, dict, enumerate, float, int, list, range, str
import hashlib
import math
import re
from OMFITlib_transfer_particles import PARTICLE_DEFAULTS, particle_options

PROFILE_KEYS = {'input.gacode': ('input.gacode',), 'statefile': ('statefile', 'statefile.nc'),
                'pfile': ('pfile',), 'input.profiles': ('input.profiles',)}


def selected_profile(node, selected=None):
    inputs = node.get('INPUTS', {})
    # Direct main.py calls retain command box 1's input.gacode-first workflow.
    if selected is None:
        selected = 'input.gacode' if 'input.gacode' in inputs else node['SETTINGS']['PHYSICS'].get('start_from', 'input.gacode')
    if selected not in PROFILE_KEYS:
        raise ValueError('请选择支持的剖面来源。')
    for key in PROFILE_KEYS[selected]:
        if key in inputs:
            return selected, key
    raise ValueError('请先载入 ' + selected + '。')


def initialize_generation(node, factory=dict):
    physics = node['SETTINGS']['PHYSICS']
    inputs = node.get('INPUTS', {})
    if physics.get('start_from', None) not in PROFILE_KEYS:
        physics['start_from'] = 'input.gacode'
    if 'generation' not in physics:
        # One-time migration only: later source selections must remain editable.
        source = physics['start_from']
        if not any(key in inputs for key in PROFILE_KEYS[source]) and 'input.gacode' in inputs:
            physics['start_from'] = 'input.gacode'
    seed = inputs.get('input.tgyro', None)
    if seed is None:
        seed = node.get('TEMPLATES', {}).get('input.tgyro', {})
    options = physics.setdefault('generation', factory())
    options.pop('main_ion', None)  # Main populations are now determined by ni/ne.
    options.pop('equivalent_ion', None)  # All non-main ions contribute; no representative is selected.
    for key, value in [('minimum', seed.get('TGYRO_RMIN', 0.2)),
                       ('maximum', seed.get('TGYRO_RMAX', 0.8)),
                       ('points', node['SETTINGS']['SETUP'].get('p_tgyro', 3)),
                       ('coordinate', 'rho' if seed.get('TGYRO_USE_RHO', 1) else 'r/a')]:
        options.setdefault(key, value)
    for key, value in PARTICLE_DEFAULTS.items():
        options.setdefault(key, value)
    return options


def radial_values(options):
    try:
        minimum, maximum = float(options['minimum']), float(options['maximum'])
        raw_points = float(options['points'])
        points = int(raw_points)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('请填写有效的起始半径、结束半径和整数点数。')
    if not math.isfinite(minimum) or not math.isfinite(maximum) or not 0 <= minimum < maximum <= 1:
        raise ValueError('半径范围需满足 0 ≤ 起始半径 < 结束半径 ≤ 1。')
    if raw_points != points or points < 2:
        raise ValueError('Transfer_tool 的径向网格至少需要 2 个点。')
    coordinate = options.get('coordinate', 'rho')
    if coordinate not in ('rho', 'r/a'):
        raise ValueError('请选择 rho 或 r/a 坐标。')
    return minimum, maximum, points, coordinate


def generation_issues(node, selected=None, options=None):
    issues = []
    try:
        kind, key = selected_profile(node, selected)
        if kind == 'pfile' and not any(name in node['INPUTS'] for name in ('gEQDSK', 'gfile')):
            issues.append('p-file 需要平衡文件 g-file。')
    except ValueError as exc:
        issues.append(str(exc))
    for name in ('input.tglf', 'input.tgyro'):
        if name not in node.get('INPUTS', {}) and name not in node.get('TEMPLATES', {}):
            issues.append('缺少 ' + name + '，请在高级设置中载入。')
    if options is not None:
        try:
            minimum, maximum, points, coordinate = radial_values(options)
            particle_options(options)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            issues.append(str(exc))
    try:
        tgyro_batch_settings(node)
    except ValueError as exc:
        issues.append(str(exc))
    return issues


def tgyro_batch_settings(node):
    """Use the shared scheduler, retaining direct execution for legacy setups."""
    settings = node['SETTINGS']
    setup, remote = settings['SETUP'], settings.get('REMOTE_SETUP', {})
    selected = remote.get(str(remote.get('serverPicker', '') or ''), {})
    scheduler = str(selected.get('scheduler', '') or '').strip().lower()
    if not scheduler and not setup.get('gacode_shared', False):
        return None
    if scheduler == 'local':
        return None
    if scheduler not in ('slurm', 'pbs'):
        raise ValueError('Transfer_tool 缺少调度器配置，请重新应用统一环境。')
    queue = str(selected.get('queue', None) or setup.get('pbs_queue', '') or '').strip()
    wall_time = str(selected.get('w', None) or setup.get('wall_time', '') or '').strip()
    if any(not value or '\n' in value or '\r' in value for value in (queue, wall_time)):
        raise ValueError('请在统一环境中填写队列 / 分区和时限。')
    shared = str(selected.get('workDir', None) or remote.get('workDir', None) or '').strip()
    if (not shared.startswith('/') or shared == '/' or shared == '/tmp'
            or shared.startswith('/tmp/') or '\n' in shared or '\r' in shared):
        raise ValueError('批处理工作根目录必须是计算节点可见的共享绝对路径，不能使用 /tmp。')
    local = str(setup.get('workDir', None) or '').strip()
    if not local:
        raise ValueError('Transfer_tool 缺少 OMFIT 本地工作目录。')
    # A stable suffix isolates concurrent OMFIT sessions without exposing the
    # local /tmp path to compute nodes.  OMFIT keeps local result collection in
    # SETUP/workDir and stages the batch in this explicit shared directory.
    token = hashlib.sha256(local.encode('utf-8')).hexdigest()[:16]
    remotedir = shared.rstrip('/') + '/OMFIT_run_' + token + '/'
    return dict(batch_type=scheduler.upper(), partition=queue, job_time=wall_time,
                remotedir=remotedir)


def prepare_tgyro(node, profile, options=None):
    """Apply the original radius/ion setup, retaining other model parameters."""
    inputs, setup = node['INPUTS'], node['SETTINGS']['SETUP']
    templates = node.get('TEMPLATES', {})
    seed = inputs.get('input.tgyro', None)
    if seed is None:
        seed = templates['input.tgyro']
    prepared = seed.duplicate()
    n_ions = int(profile['N_ION'])
    if n_ions < 1 or n_ions != profile['N_ION']:
        raise ValueError('input.gacode 的 N_ION 必须为正整数。')
    ions = []
    for index in range(1, n_ions + 1):
        ion = profile['IONS'][index]
        charge, mass = float(ion[1]), float(ion[2])
        if not math.isfinite(charge) or not math.isfinite(mass) or mass <= 0:
            raise ValueError('input.gacode 的第 {} 个离子质量或电荷无效。'.format(index))
        ions.append((charge, mass, str(ion[3]).strip().lower()))
    if n_ions > 9:
        raise ValueError('当前 TGYRO 接口最多支持 9 种离子，请选择粒子简化方案。')
    for key in list(prepared.keys()):
        if re.fullmatch(r'LOC_MA\d+|LOC_Z\d*|TGYRO_(?:CALC_FLAG|THERM_FLAG|DEN_METHOD)\d+', str(key)):
            del prepared[key]
    prepared['LOC_N_ION'] = n_ions
    for index, (charge, mass, kind) in enumerate(ions, 1):
        prepared['LOC_MA' + str(index)] = mass
        prepared['LOC_Z' if index == 1 else 'LOC_Z' + str(index)] = charge
        prepared['TGYRO_CALC_FLAG' + str(index)] = 1
        prepared['TGYRO_THERM_FLAG' + str(index)] = 0 if kind == 'fast' else 1
    # The profile generator holds ne fixed and closes charge on its first ion.
    prepared['TGYRO_DEN_METHOD0'] = 0
    for index in range(1, 10):
        prepared['TGYRO_DEN_METHOD' + str(index)] = -1 if index == 1 else 0
        if index > n_ions:
            prepared['TGYRO_CALC_FLAG' + str(index)] = 0
            prepared['TGYRO_THERM_FLAG' + str(index)] = 1
    if options is not None:
        minimum, maximum, points, coordinate = radial_values(options)
        prepared['TGYRO_RMIN'], prepared['TGYRO_RMAX'] = minimum, maximum
        prepared['TGYRO_USE_RHO'] = 1 if coordinate == 'rho' else 0
        setup['p_tgyro'] = points
        # Command box 1 uses one MPI rank per radius, not the CGYRO CPU budget.
        setup['num_nodes'], setup['num_cores'] = 1, points
        prepared['DIR'].clear()
        for index in range(1, points + 1):
            prepared['DIR']['TGLF' + str(index)] = 1
    if 'input.tglf' not in inputs:
        inputs['input.tglf'] = templates['input.tglf'].duplicate()
    inputs['input.tgyro'] = prepared


def loaded_file(node, branch, key):
    value = node.get(branch, {}).get(key, None)
    if value is None:
        return key + '：未载入'
    filename = getattr(value, 'filename', '')
    return key + '：已载入' + (' · ' + str(filename) if filename else '')
