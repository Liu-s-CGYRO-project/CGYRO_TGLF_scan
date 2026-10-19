"""Read-only data selection for the Transfer_tool plot catalogue."""
from builtins import any, dict, enumerate, float, int, isinstance, iter, len, list, next, range, set, sorted, str, sum
from collections import OrderedDict
import math
import re
import numpy as np
from OMFITlib_transfer_particles import species

GROUPS = OrderedDict([('profiles', '剖面与粒子'), ('estimates', '解析估算'), ('transport', '平衡与输运')])
CATALOG = OrderedDict([
    ('profile', ('profiles', '剖面与梯度', '温度、密度、旋转、q、压力及局部梯度。')),
    ('fastion', ('profiles', '快离子', '按粒子类型识别快离子，查看密度、温度和压力贡献。')),
    ('normpara', ('profiles', '归一化与特征频率', '声速、回旋半径、Alfvén 速度和 Doppler 频移。')),
    ('printinfo', ('profiles', '局部参数表', '各生成半径的梯度、q、剪切、β 和碰撞参数。')),
    ('pltcrit', ('estimates', 'ITG / ETG 临界梯度', '沿用原解析模型，与生成输入的梯度对照。')),
    ('mtm', ('estimates', 'MTM 频率估算', '查看抗磁频率、实验室频移和环向模数。')),
    ('kbmbae', ('estimates', 'KBM / BAE 估算', '查看共振频率、压力梯度驱动与对应模数。')),
    ('view12', ('transport', '平衡与电流', '磁面、q、压力、电流组分和电场。')),
    ('source', ('transport', '加热与粒子源', '电子 / 离子加热、粒子源和力矩。')),
    ('powerbalance', ('transport', '功率平衡', '目标、新经典和剩余通量及输运系数。')),
])
PROFILE_FIELDS = ('rho', 'rmin', 'ne', 'Te', 'q', 'N_ION', 'IONS')
LOCAL_PLOTS = ('normpara', 'printinfo', 'pltcrit', 'mtm', 'kbmbae')
LOCAL_FIELDS = ('NS', 'Q_LOC', 'RMIN_LOC', 'RMAJ_LOC', 'BETAE', 'XNUE', 'RLTS_1', 'RLTS_2', 'RLNS_1')
TGYRO_FIELDS = ('rho', 'pflux_e_target', 'pflux_e_neo', 'eflux_e_target', 'eflux_e_neo',
                'eflux_i_target', 'Chi_GB', 'a/Lte', 'a/Lti1')


def get(root, path, default=None):
    value = root
    for key in path:
        if not hasattr(value, 'get') or key not in value:
            return default
        value = value[key]
    return value


def initialize(root):
    settings = root['SETTINGS'].setdefault('PLOT_OPTIONS', {})
    for key, value in dict(profile='generated', minimum=0.0, maximum=1.0, ky=0.1).items():
        settings.setdefault(key, value)
    choices = profile_choices(root)
    if choices and settings['profile'] not in choices.values():
        settings['profile'] = next(iter(choices.values()))
    return settings


def profile_choices(root):
    result = OrderedDict()
    for caption, key, path in (
            ('本轮生成剖面', 'generated', ('Transfer_file', 'input.gacode')),
            ('当前输入剖面', 'current', ('INPUTS', 'input.gacode'))):
        value = get(root, ('OUTPUTS', 'Particle_processing', 'plot_profile')) if key == 'generated' else None
        value = value if value is not None else get(root, path)
        if value is not None and (key != 'generated' or any(
                re.fullmatch(r'input\.tglf_\d+', str(name))
                for name in get(root, ('OUTPUTS', 'Profiles_gen'), {}).keys())):
            result[caption] = key
    return result


def selected_profile(root):
    choice = initialize(root)['profile']
    path = ('Transfer_file', 'input.gacode') if choice == 'generated' else ('INPUTS', 'input.gacode')
    paired = get(root, ('OUTPUTS', 'Particle_processing', 'plot_profile')) if choice == 'generated' else None
    return paired if paired is not None else get(root, path)


def local_rows(root):
    """Use saved physical radii; never invent a linspace from a point count."""
    branch = get(root, ('OUTPUTS', 'Profiles_gen'), {})
    metadata = get(root, ('OUTPUTS', 'Particle_processing', 'local_inputs'), {})
    rows = []
    for name in branch.keys():
        match = re.fullmatch(r'input\.tglf_(\d+)', str(name))
        if match:
            index = int(match.group(1))
            radius = metadata.get(name, {}).get('rho', None)
            rows.append(dict(index=index, name=str(name), rho=radius, input=branch[name]))
    if any(row['rho'] is None for row in rows):
        grid = get(root, ('OUTPUTS', 'TGYRO', 'rho'))
        radii = np.asarray(grid, dtype=float) if grid is not None else np.array([])
        if radii.ndim > 1:
            radii = radii[0]
        # TGYRO includes its boundary/reference point before local directories.
        radii = radii[1:] if radii.ndim == 1 else np.array([])
        for row in rows:
            if row['rho'] is None and 1 <= row['index'] <= len(radii):
                row['rho'] = float(radii[row['index'] - 1])
    return sorted(rows, key=lambda row: row['index'])


def local_ion_types(root, row):
    """Return native TGLF indices/types only when their ownership is known.

    Grouped cards can have a different order and species count at each radius.
    A fast ion's original profile index must not select an impurity after a merge.
    """
    report = get(root, ('OUTPUTS', 'Particle_processing'), {})
    if report.get('options', {}).get('particle_mode', '') == 'separate_fast':
        groups = report.get('local_inputs', {}).get(row['name'], {}).get('equivalent', {}).get('groups', {})
        if set(groups.keys()) != {'main', 'impurity', 'fast'}:
            return None
        result = []
        for name in ('main', 'impurity', 'fast'):
            record = groups[name]
            index = record.get('solver_index', None)
            if index is None:
                if name == 'main' or not record.get('omitted', False):
                    return None
                continue
            if not isinstance(index, int) or record.get('omitted', False):
                return None
            result.append(dict(index=index, kind='fast' if name == 'fast' else 'therm'))
        indices = [ion['index'] for ion in result]
        if sorted(indices) != list(range(2, int(row['input']['NS']) + 1)):
            return None
        return result
    ions = species(selected_profile(root))
    if int(row['input']['NS']) != len(ions) + 1:
        return None
    return [dict(index=ion['index'] + 1, kind=ion['kind']) for ion in ions]


def state_input(root):
    return get(root, ('INPUTS', 'statefile.nc'), get(root, ('INPUTS', 'statefile')))


def equilibrium_input(root):
    return get(root, ('INPUTS', 'gEQDSK'), get(root, ('INPUTS', 'gfile')))


def data_issues(root, name):
    problems = []
    if name not in CATALOG:
        return ['未知绘图功能']
    if name in ('profile', 'fastion') + LOCAL_PLOTS:
        profile = selected_profile(root)
        if profile is None:
            return ['请先载入或生成 input.gacode']
        missing = [key for key in PROFILE_FIELDS if key not in profile]
        if missing:
            return ['剖面缺少 ' + ', '.join(missing)]
        try:
            ions = species(profile)
        except (KeyError, ValueError, TypeError) as exc:
            return [str(exc)]
        if name == 'fastion' and not any(ion['kind'] == 'fast' for ion in ions):
            problems.append('所选剖面不含快离子')
        if name in LOCAL_PLOTS:
            if initialize(root)['profile'] != 'generated':
                problems.append('请选择与半径输入对应的“本轮生成剖面”')
            try:
                rows = local_rows(root)
                if not rows:
                    problems.append('请先运行 Transfer_tool 生成半径输入')
                for row in rows:
                    if row['rho'] is None or not math.isfinite(float(row['rho'])):
                        problems.append('生成输入缺少实际半径，请重新生成')
                        break
                    fields = LOCAL_FIELDS
                    if name in ('normpara', 'mtm', 'kbmbae'):
                        fields += ('KAPPA_LOC', 'S_KAPPA_LOC', 'DRMAJDX_LOC', 'MASS_2', 'TAUS_2', 'ZS_2', 'ZEFF')
                    missing = [key for key in fields if key not in row['input']]
                    if missing:
                        problems.append(row['name'] + ' 缺少 ' + ', '.join(missing))
                        break
            except (KeyError, ValueError, TypeError) as exc:
                problems.append('半径输入无效：' + str(exc))
        required = ('rmaj', 'z_eff', 'kappa') if name == 'pltcrit' else (
            ('BT_EXP', 'omega0') if name in ('normpara', 'mtm', 'kbmbae') else ())
        missing = [key for key in required if key not in profile]
        if missing:
            problems.append('剖面缺少 ' + ', '.join(missing))
        if name in ('normpara', 'mtm', 'kbmbae'):
            try:
                ky = float(initialize(root)['ky'])
                if not math.isfinite(ky) or ky <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                problems.append('ky 必须为正数')
        if name in ('pltcrit', 'kbmbae') and initialize(root)['profile'] == 'generated':
            try:
                mode = get(root, ('OUTPUTS', 'Particle_processing', 'options', 'particle_mode'), '')
                if name == 'pltcrit' and mode == 'separate_fast':
                    problems.append('原 ITG / ETG 估算使用单个源热离子的剖面；分组合并后请使用保留粒子的生成结果进行此项估算')
                elif any(local_ion_types(root, row) is None for row in local_rows(root)):
                    problems.append('此解析模型需要保留粒子的半径输入，不能拆分等效杂质中的热 / 快离子')
            except (KeyError, TypeError, ValueError):
                problems.append('局部粒子数量无效')
    elif name == 'view12':
        if equilibrium_input(root) is None:
            problems.append('请先载入平衡文件 gfile')
        if state_input(root) is None and get(root, ('INPUTS', 'trpltout.nc')) is None:
            problems.append('还需要 statefile 或 trpltout.nc 的电流数据')
    elif name == 'source':
        if state_input(root) is None:
            problems.append('需要 statefile 的加热和粒子源数据')
        if get(root, ('INPUTS', 'input.profiles')) is None:
            problems.append('需要 input.profiles 的积分源项')
    elif name == 'powerbalance':
        result = get(root, ('OUTPUTS', 'TGYRO'), {})
        missing = [key for key in TGYRO_FIELDS if key not in result]
        if missing:
            problems.append('需要已收集的 TGYRO 输运结果')
        elif not any(re.fullmatch(r'eflux_i\d+_neo', str(key)) for key in result.keys()):
            problems.append('TGYRO 结果缺少离子新经典通量')
    try:
        options = initialize(root)
        lower, upper = float(options['minimum']), float(options['maximum'])
        if not math.isfinite(lower + upper) or not 0 <= lower < upper <= 1:
            raise ValueError()
    except (TypeError, ValueError):
        problems.append('绘图范围需满足 0 ≤ 起始 < 结束 ≤ 1')
    return problems


def vector(value, key, size=None):
    if key not in value:
        raise ValueError('数据缺少 ' + key)
    result = np.array(value[key], dtype=float, copy=True)
    if result.ndim != 1 or result.size < 2 or (size is not None and result.size != size):
        raise ValueError(key + ' 的径向网格长度不一致')
    if not np.all(np.isfinite(result)):
        raise ValueError(key + ' 包含无效数值')
    return result


def local_values(rows, key):
    try:
        result = np.array([float(row['input'][key]) for row in rows])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('半径输入缺少或无法读取 ' + key) from exc
    if not np.all(np.isfinite(result)):
        raise ValueError(key + ' 包含无效数值')
    return result


def shear(row):
    value = row['input']
    if 'Q_PRIME_LOC' in value:
        return float(value['Q_PRIME_LOC']) * float(value['RMIN_LOC']) ** 2 / float(value['Q_LOC']) ** 2
    return float(value['SHAT_SA'])


def alpha(row):
    value = row['input']
    pressure = sum(float(value['AS_' + str(i)]) * float(value['TAUS_' + str(i)]) *
                   (float(value['RLNS_' + str(i)]) + float(value['RLTS_' + str(i)]))
                   for i in range(1, int(value['NS']) + 1))
    return pressure * float(value['Q_LOC']) ** 2 * float(value['RMAJ_LOC']) * float(value['BETAE'])


def parameter_rows(root):
    result = []
    for row in local_rows(root):
        value = row['input']
        result.append([row['index'], row['rho']] + [value[key] for key in
                      ('RLTS_2', 'RLTS_1', 'RLNS_1')] + [shear(row), value['Q_LOC'],
                      value['BETAE'], value['XNUE'], alpha(row)])
    return result
