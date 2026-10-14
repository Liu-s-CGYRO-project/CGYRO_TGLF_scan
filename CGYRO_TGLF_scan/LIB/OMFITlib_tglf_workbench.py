"""TGLF input selection and explicit scan plans, without running a solver."""
from builtins import abs, all, any, bool, dict, enumerate, float, int, isinstance, len, list, max, min, next, range, set, sorted, str, tuple
from collections import OrderedDict
import copy
import math

# OMFIT removes its library importer when GUI scripts return. Resolve this
# dependency while loading the module so button callbacks keep the function.
from OMFITlib_tglf_multi_data import profile_digest

PROFILE_PATH = ('TGLF_scan', 'TGYRO', 'PROFILES_GEN', 'OUTPUTS', 'input.gacode')
SEED_PATH = ('TGLF_scan', 'TGYRO', 'INPUTS', 'input.tglf')
RADII = [index / 100.0 for index in range(1, 100)]

MODES = OrderedDict([('原始参数', 'single'), ('一维参数扫描', '1d'),
                     ('二维参数扫描', '2d'), ('不确定度扫描（UQ）', 'uq')])
# References are displayed only. A value is applied only after the user edits it.
COMMON = OrderedDict([
    ('SAT_RULE', (2, '饱和规则')), ('KYGRID_MODEL', (4, 'ky 网格模型')),
    ('KY', (0.3, 'ky')), ('NKY', (19, 'ky 点数')), ('NMODES', (6, '模态数')),
    ('NBASIS_MIN', (2, '最少基函数')), ('NBASIS_MAX', (6, '最多基函数')),
    ('NXGRID', (16, '积分网格')), ('WIDTH', (1.65, '最大宽度')),
    ('WIDTH_MIN', (0.3, '最小宽度')), ('NWIDTH', (21, '宽度搜索点数')),
    ('FIND_WIDTH', (True, '搜索模态宽度')), ('USE_BPER', (False, '包含 A 平行扰动')),
    ('USE_BPAR', (False, '包含 B 平行扰动')), ('XNU_MODEL', (3, '碰撞模型')),
    ('USE_MHD_RULE', (True, 'MHD 规则')), ('ADIABATIC_ELEC', (False, '绝热电子')),
    ('USE_BISECTION', (True, '二分宽度搜索')), ('IBRANCH', (-1, '模态排序')),
    ('VPAR_MODEL', (0, '平行流模型')), ('VPAR_SHEAR_MODEL', (1, '平行流剪切模型')),
    ('ALPHA_E', (1.0, 'ExB 剪切系数')), ('ALPHA_P', (1.0, '平行流剪切系数')),
    ('ALPHA_QUENCH', (0.0, '剪切抑制系数')), ('ETG_FACTOR', (1.25, 'ETG 系数')),
    ('ALPHA_ZF', (1.0, '带状流系数')), ('WDIA_TRAPPED', (1.0, '俘获粒子漂移系数')),
    ('USE_AVE_ION_GRID', (True, '平均离子网格')),
])
# These scenarios are the bundled OMFIT TGYRO/TGLFinputGUI definitions.
SCENARIO_FIELDS = ('ALPHA_QUENCH', 'SAT_RULE', 'ALPHA_ZF', 'NKY', 'KYGRID_MODEL',
                   'NBASIS_MAX', 'NMODES', 'UNITS', 'XNU_MODEL', 'WDIA_TRAPPED', 'USE_AVE_ION_GRID')
SCENARIOS = OrderedDict([
    ('input', ('沿用当前设置', None)),
    ('custom', ('自定义', None)),
    ('quench', ('Quench · SAT0', (1.0, 0, 0.0, 12, 1, 4, 4, 'GYRO', 2, 0.0, False))),
    ('sat0', ('常规 · SAT0', (0.0, 0, 0.0, 12, 1, 4, 4, 'GYRO', 2, 0.0, False))),
    ('sat1', ('常规 · SAT1', (0.0, 1, 1.0, 12, 1, 4, 4, 'GYRO', 2, 0.0, False))),
    ('sat2', ('常规 · SAT2', (0.0, 2, 1.0, 12, 4, 6, 4, 'CGYRO', 3, 1.0, True))),
    ('jet', ('JET · SAT2', (0.0, 2, 1.0, 17, 4, 6, 5, 'CGYRO', 3, 1.0, True))),
    ('st', ('ST', (0.0, 1, 1.0, 12, 4, 4, 4, 'GYRO', 2, 0.0, False))),
    ('iter', ('ITER', (0.0, 1, 1.0, 20, 4, 4, 4, 'GYRO', 2, 0.0, False))),
])
INTEGERS = {'NS', 'SAT_RULE', 'KYGRID_MODEL', 'NKY', 'NMODES', 'NBASIS_MIN',
            'NBASIS_MAX', 'NXGRID', 'NWIDTH', 'IBRANCH', 'XNU_MODEL', 'GEOMETRY_FLAG',
            'VPAR_MODEL', 'VPAR_SHEAR_MODEL', 'WRITE_WAVEFUNCTION_FLAG', '并发任务数', 'UQ 参数数', '样本数', '扫描点数'}
POSITIVE = {'NS', 'NKY', 'NMODES', 'NBASIS_MIN', 'NBASIS_MAX', 'NXGRID', 'NWIDTH', 'WIDTH', 'WIDTH_MIN'}


def get(root, path, default=None):
    node = root
    for key in path:
        if not hasattr(node, 'get') or key not in node:
            return default
        node = node[key]
    return node


def clone(value):
    return value.duplicate() if hasattr(value, 'duplicate') else copy.deepcopy(value)


def generation_seed(root):
    seed = get(root, SEED_PATH)
    if seed is None:
        seed = get(root, ('Transfer_tool', 'TEMPLATES', 'input.tglf'))
    return seed


def scalar(value):
    return value.tolist() if hasattr(value, 'tolist') else value


def parameter_value(name, value, original):
    value, original = scalar(value), scalar(original)
    if isinstance(original, bool):
        text = str(value).strip().lower()
        if text in ('true', '.true.', '1'):
            return True
        if text in ('false', '.false.', '0'):
            return False
        raise ValueError(name + ' 需要 true 或 false')
    if isinstance(value, bool):
        raise ValueError(name + ' 需要数值')
    try:
        number = float(str(value).strip().replace('D', 'e').replace('d', 'e'))
    except (TypeError, ValueError, OverflowError):
        raise ValueError(name + ' 需要数值')
    if not math.isfinite(number):
        raise ValueError(name + ' 需要有限数值')
    if name in INTEGERS:
        if int(number) != number:
            raise ValueError(name + ' 需要整数')
        number = int(number)
    if (name in POSITIVE or name.startswith(('MASS_', 'TAUS_'))) and number <= 0:
        raise ValueError(name + ' 必须大于 0')
    return number


def numeric_parameters(source):
    result = OrderedDict()
    for name, value in source.items():
        value = scalar(value)
        if name in ('rho', 'USE_TRANSPORT_MODEL') or str(name).startswith('__'):
            continue
        if isinstance(value, (int, float, bool)):
            result[str(name)] = value
    return result


def parameter_overrides(settings, source):
    values = numeric_parameters(source)
    result = {}
    for name, item in settings['parameters'].items():
        if not item.get('enabled', False):
            continue
        if name == 'NS' or (name not in values and name not in COMMON):
            raise ValueError('当前输入不支持参数 ' + name)
        reference = values.get(name, COMMON.get(name, (0.0,))[0])
        result[name] = parameter_value(name, item['value'], reference)
    units = str(settings.get('units_override', '') or '')
    if units:
        if units not in ('GYRO', 'CGYRO'):
            raise ValueError('UNITS 请选择 GYRO 或 CGYRO')
        result['UNITS'] = units
    return result


def generation_overrides(root, settings):
    seed = generation_seed(root)
    if seed is None:
        raise ValueError('缺少 TGLF 种子输入')
    reference = dict(seed)
    # Existing local inputs supply the type of profile-derived parameters the
    # user may have edited on the full parameter page.
    rows = [row for row in input_rows(root) if row['group'] == 'radial']
    if rows:
        reference.update(get(root, rows[0]['path']))
    return parameter_overrides(settings, reference)


def input_rows(root):
    rows = []
    path = ('TGLF_scan', 'TGLF', 'FILES', 'input.tglf')
    if get(root, path) is not None:
        rows.append(dict(key='current', group='current', label='当前 / 导入的 TGLF 文件', path=path))
    prefix = ('Transfer_tool', 'OUTPUTS', 'Profiles_gen')
    metadata = get(root, ('Transfer_tool', 'OUTPUTS', 'Particle_processing', 'local_inputs'), {})
    for name in sorted(get(root, prefix, {}).keys(), key=str):
        if str(name).startswith('input.tglf_') and str(name)[11:].isdigit():
            nr = int(str(name)[11:])
            rho = metadata.get(name, {}).get('rho', None)
            label = 'nr={}'.format(nr) + (' · rho={:g}'.format(float(rho)) if rho is not None else '')
            rows.append(dict(key='transfer:' + str(nr), group='transfer', label=label, path=prefix + (name,), nr=nr, rho=rho))
    rows[1 if rows and rows[0]['key'] == 'current' else 0:] = sorted(
        rows[1 if rows and rows[0]['key'] == 'current' else 0:], key=lambda row: row['nr'])
    prefix = ('TGLF_scan', 'input.tglf')
    coordinate = get(root, ('TGLF_scan', '_local_input_generation', 'coordinate'), '半径')
    for radius in sorted(get(root, prefix, {}).keys(), key=float):
        rows.append(dict(key='radial:' + str(radius), group='radial', label=coordinate + '=' + str(radius),
                         path=prefix + (radius,), rho=radius, coordinate=coordinate))
    path = ('Transfer_tool', 'Transfer_file', 'input.tglf')
    if get(root, path) is not None:
        rows.append(dict(key='local', group='local', label='局部互转的 TGLF 文件', path=path))
    return rows


def initialize(root, factory=dict):
    settings = root['SETTINGS']['WORKBENCH'].setdefault('tglf', factory())
    physics = get(root, ('TGLF_scan', 'TGLF', 'SETTINGS', 'PHYSICS'), {})
    defaults = dict(mode='single', parameter1=physics.get('scanParameter', 'RLTS_1'),
                    parameter2=physics.get('scanParameter2D', 'XNUE'), values1=[], values2=[],
                    parallel=physics.get('parallelScan', 3), single_Ti=physics.get('single_Ti', False),
                    uq_count=1, samples=15, sampling='L', parameter_group='common', search='',
                    page='scan', scan_page='input')
    coordinate = 'rho' if get(root, ('TGLF_scan', 'TGYRO', 'INPUTS', 'input.tgyro', 'TGYRO_USE_RHO'), 1) else 'r/a'
    try:
        native_radius = float(get(root, ('TGLF_scan', 'SETTINGS', 'PHYSICS', 'rho'), 0.5))
        if not math.isfinite(native_radius) or not 0 < native_radius < 1:
            native_radius = 0.5
    except (TypeError, ValueError):
        native_radius = 0.5
    defaults.update(dict(profile_file='', profile_coordinate=coordinate, radius_start=0.2,
                         radius_end=0.8, radius_step=0.05, radius_values=[0.3, 0.5, 0.7],
                         radius=native_radius,
                         scenario='input', units_override=''))
    for index in (1, 2):
        key = 'scanParameter' if index == 1 else 'scanParameter2D'
        try:
            has_values = len(settings.get('values' + str(index), [])) > 0
        except TypeError:
            has_values = False
        defaults.update({
            'value_mode' + str(index): 'list' if has_values else 'factor',
            'scan_start' + str(index): physics.get(key + 'Min', 0.5),
            'scan_end' + str(index): physics.get(key + 'Max', 1.5),
            'scan_count' + str(index): physics.get(key + 'Steps', 5),
        })
    defaults['include_ions'] = get(root, ('TGLF_scan', 'TGYRO', 'SETTINGS', 'PHYSICS', 'INCLUDE_IONS'), 'thermal')
    for key, value in defaults.items():
        settings.setdefault(key, value)
    for key in ('selected', 'parameters', 'uq'):
        settings.setdefault(key, factory())
    rows = input_rows(root)
    settings.setdefault('source', 'radial')
    # An unavailable saved choice stays visible as a missing input, never switches silently.
    transfer = [row for row in rows if row['group'] == 'transfer']
    for row in rows:
        default_selected = row['group'] != 'transfer' or row['key'] == transfer[0]['key']
        settings['selected'].setdefault(row['key'], default_selected)
    if settings.get('radius_choice_version', 0) < 2:
        radial = [row for row in rows if row['group'] == 'radial']
        chosen = [row['rho'] for row in radial if settings['selected'].get(row['key'], False)]
        # Preserve explicit subsets, but replace the old automatic "all" default
        # with one visible radius. Selecting all is now a deliberate choice.
        if settings.get('radius_mode', None) not in ('range', 'list', 'single'):
            settings['radius_mode'] = 'list' if radial and len(chosen) != len(radial) else 'single'
            if settings['radius_mode'] == 'list':
                settings['radius_values'] = chosen
        if radial and settings['radius_mode'] == 'single':
            settings['radius'] = min(radial, key=lambda row: abs(float(row['rho']) - float(settings['radius'])))['rho']
        settings['radius_choice_version'] = 2
    return settings, rows


def selected_rows(root, settings):
    rows = [row for row in input_rows(root) if row['group'] == settings['source']]
    if settings['source'] == 'radial':
        return select_radii(rows, settings)
    return [row for row in rows if settings['selected'].get(row['key'], False)]


def select_radii(rows, settings):
    if not rows or settings['radius_mode'] == 'all':
        return rows
    if settings['radius_mode'] == 'single':
        wanted = [parameter_value('半径', settings['radius'], 0.0)]
    elif settings['radius_mode'] == 'range':
        start, end, step = [parameter_value('半径', settings[key], 0.0)
                            for key in ('radius_start', 'radius_end', 'radius_step')]
        if not 0 < start <= end < 1 or step <= 0:
            raise ValueError('半径范围需满足 0 < 起始 ≤ 结束 < 1，间隔大于 0')
        count = int(math.floor((end - start) / step + 1e-8)) + 1
        if count > len(rows):
            raise ValueError('半径间隔小于已有输入的间隔，请调整范围或间隔')
        wanted = [start + index * step for index in range(count)]
    elif settings['radius_mode'] == 'list':
        wanted = scan_values('半径', settings['radius_values'], 0.0)
    else:
        raise ValueError('请选择半径范围')
    selected = []
    for radius in wanted:
        matches = [row for row in rows if abs(float(row['rho']) - radius) < 1e-8]
        if len(matches) != 1:
            raise ValueError('没有半径 {:g} 的 input.tglf，请使用已生成的半径值'.format(radius))
        if matches[0] in selected:
            raise ValueError('半径列表包含重复值')
        selected.append(matches[0])
    return selected


def radial_input_issues(root, settings):
    if settings.get('profile_changed', False):
        return ['剖面已更换，请重新生成输入文件']
    metadata = get(root, ('TGLF_scan', '_local_input_generation'), {})
    if metadata and (metadata.get('coordinate', None) != settings['profile_coordinate']
                     or metadata.get('include_ions', None) != settings['include_ions']):
        return ['坐标或离子选项已变化，请重新生成半径输入']
    if metadata.get('profile_digest', None):
        profile = get(root, PROFILE_PATH)
        if profile is None or profile_digest(profile) != metadata['profile_digest']:
            return ['input.gacode 已变化，请重新生成半径输入']
    return []


def scan_values(name, values, original):
    if isinstance(values, (str, bytes)):
        raise ValueError(name + ' 扫描值请填列表，例如 [0.5, 1, 1.5]')
    try:
        values = list(values)
    except TypeError:
        raise ValueError(name + ' 扫描值请填列表')
    if not values:
        raise ValueError(name + ' 没有扫描值')
    parsed = [parameter_value(name, value, original) for value in values]
    if len(set(parsed)) != len(parsed):
        raise ValueError(name + ' 扫描值重复')
    return parsed


def axis_values(settings, index, name, original):
    suffix = str(index)
    mode = settings.get('value_mode' + suffix, 'list')
    if mode == 'list':
        return scan_values(name, settings['values' + suffix], original)
    if mode not in ('range', 'factor'):
        raise ValueError('请选择扫描取值方式')
    if isinstance(scalar(original), bool):
        raise ValueError(name + ' 是逻辑参数，请使用取值列表')
    start = parameter_value('扫描起点', settings['scan_start' + suffix], 0.0)
    end = parameter_value('扫描终点', settings['scan_end' + suffix], 0.0)
    count = parameter_value('扫描点数', settings['scan_count' + suffix], 1)
    if not 1 <= count <= 10000:
        raise ValueError('扫描点数需在 1–10000 之间')
    if mode == 'factor':
        if float(original) == 0:
            raise ValueError(name + ' 原值为 0，请使用实际值范围或取值列表')
        start, end = start * float(original), end * float(original)
    values = [start] if count == 1 else [start + (end - start) * i / (count - 1) for i in range(count)]
    return scan_values(name, values, original)


def plan(root, settings):
    if settings['source'] == 'radial':
        issues = radial_input_issues(root, settings)
        if issues:
            raise ValueError('；'.join(issues))
    rows = selected_rows(root, settings)
    if not rows:
        raise ValueError('请选择至少一个 TGLF 输入')
    mode = settings['mode']
    if mode not in MODES.values():
        raise ValueError('请选择计算方式')
    parallel = parameter_value('并发任务数', settings['parallel'], 1)
    if parallel < 1:
        raise ValueError('并发任务数必须大于 0')
    sources, axes, uq = [], [], []
    for row in rows:
        source = get(root, row['path'])
        values = numeric_parameters(source)
        for key in ('NS', 'KY'):
            if key not in values:
                raise ValueError(row['label'] + ' 缺少 ' + key)
        parameters = parameter_overrides(settings, source)
        values.update(parameters)
        names = [settings['parameter1']] if mode == '1d' else ([settings['parameter1'], settings['parameter2']] if mode == '2d' else [])
        if len(names) != len(set(names)):
            raise ValueError('两个扫描参数不能相同')
        axes = []
        for index, name in enumerate(names, 1):
            if name not in values or name == 'NS':
                raise ValueError(row['label'] + ' 缺少扫描参数 ' + name + '，或该参数不可扫描')
            axes.append(dict(name=name, values=axis_values(settings, index, name, values[name])))
        if mode == 'uq':
            count = parameter_value('UQ 参数数', settings['uq_count'], 1)
            if not 1 <= count <= 5:
                raise ValueError('UQ 参数数范围是 1–5')
            uq = []
            for index in range(count):
                item = settings['uq'].get(str(index), {})
                name = str(item.get('name', ''))
                if name not in values or isinstance(values[name], bool) or name in INTEGERS:
                    raise ValueError('UQ 请选择当前输入中的连续数值参数：' + name)
                mean = parameter_value(name, item.get('mean', None), float(values[name]))
                std = parameter_value('标准差', item.get('std', None), 0.0)
                if std <= 0:
                    raise ValueError(name + ' 标准差必须大于 0')
                uq.append(dict(name=name, mean=mean, std=std))
            if len({item['name'] for item in uq}) != len(uq):
                raise ValueError('UQ 参数不能重复')
        sources.append(dict(row, parameters=parameters, axes=copy.deepcopy(axes)))
    samples = parameter_value('样本数', settings['samples'], 1) if mode == 'uq' else 0
    if mode == 'uq' and samples < 1:
        raise ValueError('样本数必须大于 0')
    if mode == 'uq' and settings['sampling'] not in ('L', 'M'):
        raise ValueError('请选择采样方法')
    points = samples if mode == 'uq' else (len(axes[0]['values']) if axes else 1)
    if len(axes) == 2:
        points *= len(axes[1]['values'])
    return dict(mode=mode, sources=sources, axes=axes, uq=uq, samples=samples,
                sampling=settings['sampling'], parallel=parallel, single_Ti=bool(settings['single_Ti']),
                points_per_input=points, total=points * len(sources))
