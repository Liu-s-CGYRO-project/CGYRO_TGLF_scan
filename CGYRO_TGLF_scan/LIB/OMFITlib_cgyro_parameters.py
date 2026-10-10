"""Scalar calculation settings shared by the workbench and CGYRO submitter."""
from builtins import any, bool, dict, float, hasattr, int, len, list, set, sorted, str, zip
from collections import OrderedDict
import math
import re

GROUPS = OrderedDict([('常用设置', 'common'), ('时间与收敛', 'time'),
                      ('网格与速度空间', 'grid'), ('场与碰撞', 'model'),
                      ('数值耗散与算法', 'algorithm'), ('平衡与剪切', 'geometry'),
                      ('输出选项', 'output'), ('其他输入参数', 'other'), ('全部参数', 'all')])
CORE_FIELDS = ('DELTA_T_METHOD', 'DELTA_T', 'ERROR_TOL', 'MAX_TIME', 'PRINT_STEP', 'FREQ_TOL')
# Fallbacks are explicit GUI reference values, not forced solver values.
# Nothing is written until the user edits a value or selects a scan axis.
FIELDS = OrderedDict([
    ('DELTA_T', ('时间步长', 'time', 0.01, 'float', True)),
    ('DELTA_T_METHOD', ('时间积分方法', 'time', 0, 'int', False)),
    ('ERROR_TOL', ('积分误差容限', 'time', 6e-5, 'float', True)),
    ('MAX_TIME', ('运行时长', 'time', 100.0, 'float', True)),
    ('PRINT_STEP', ('输出步数间隔', 'time', 100, 'int', True)),
    ('FREQ_TOL', ('频率收敛容限', 'time', 0.001, 'float', False)),
    ('N_RADIAL', ('径向网格', 'grid', 4, 'int', True)),
    ('N_THETA', ('极向网格', 'grid', 24, 'int', True)),
    ('N_ENERGY', ('能量网格', 'grid', 8, 'int', True)),
    ('N_XI', ('俯仰角网格', 'grid', 16, 'int', True)),
    ('E_MAX', ('能量上限', 'grid', 8.0, 'float', True)),
    ('BOX_SIZE', ('径向盒尺寸倍数', 'grid', 1, 'int', True)),
    ('N_FIELD', ('场数量', 'model', 1, 'int', True)),
    ('COLLISION_MODEL', ('碰撞模型', 'model', 4, 'int', True)),
    ('NU_EE', ('电子碰撞频率', 'model', 0.1, 'float', False)),
    ('NU_EE_SCALE', ('碰撞频率系数', 'model', 1.0, 'float', False)),
    ('COLLISION_FIELD_MODEL', ('碰撞场更新', 'model', 1, 'int', False)),
    ('COLLISION_MOM_RESTORE', ('碰撞动量守恒', 'model', 1, 'int', False)),
    ('COLLISION_ENE_RESTORE', ('碰撞能量守恒', 'model', 1, 'int', False)),
    ('COLLISION_ENE_DIFFUSION', ('碰撞能量扩散', 'model', 1, 'int', False)),
    ('COLLISION_KPERP', ('碰撞垂直波数项', 'model', 1, 'int', False)),
    ('BETAE_UNIT', ('电子 beta', 'model', 0.0, 'float', False)),
    ('BETAE_UNIT_SCALE', ('电子 beta 系数', 'model', 1.0, 'float', False)),
    ('BETA_STAR_SCALE', ('压力梯度系数', 'model', 1.0, 'float', False)),
    ('NUP_RADIAL', ('径向耗散阶数', 'algorithm', 3, 'int', True)),
    ('NUP_THETA', ('极向耗散阶数', 'algorithm', 3, 'int', True)),
    ('NUP_ALPHA', ('环向耗散阶数', 'algorithm', 3, 'int', True)),
    ('UP_RADIAL', ('径向耗散强度', 'algorithm', 1.0, 'float', False)),
    ('UP_THETA', ('极向耗散强度', 'algorithm', 1.0, 'float', False)),
    ('UP_ALPHA', ('环向耗散强度', 'algorithm', 0.0, 'float', False)),
    ('MPI_RANK_ORDER', ('MPI 分配顺序', 'algorithm', 2, 'int', True)),
    ('VELOCITY_ORDER', ('速度空间顺序', 'algorithm', 1, 'int', True)),
    ('Q', ('安全因子', 'geometry', 2.0, 'float', False)),
    ('S', ('磁剪切', 'geometry', 1.0, 'float', False)),
    ('RMIN', ('归一化小半径', 'geometry', 0.5, 'float', False)),
    ('RMAJ', ('归一化大半径', 'geometry', 3.0, 'float', True)),
    ('KAPPA', ('拉长比', 'geometry', 1.0, 'float', True)),
    ('DELTA', ('三角形变', 'geometry', 0.0, 'float', False)),
    ('SHIFT', ('磁轴偏移梯度', 'geometry', 0.0, 'float', False)),
    ('S_KAPPA', ('拉长比剪切', 'geometry', 0.0, 'float', False)),
    ('S_DELTA', ('三角形变剪切', 'geometry', 0.0, 'float', False)),
    ('PX0', ('气球模角参数', 'geometry', 0.0, 'float', False)),
    ('EQUILIBRIUM_MODEL', ('平衡模型', 'geometry', 2, 'int', True)),
    ('GAMMA_P', ('旋转剪切', 'geometry', 0.0, 'float', False)),
    ('MACH', ('旋转马赫数', 'geometry', 0.0, 'float', False)),
    ('FIELD_PRINT_FLAG', ('输出场数据', 'output', 0, 'int', False)),
    ('MOMENT_PRINT_FLAG', ('输出粒子矩', 'output', 0, 'int', False)),
    ('H_PRINT_FLAG', ('输出分布函数', 'output', 0, 'int', False)),
    ('SILENT_FLAG', ('精简终端输出', 'output', 0, 'int', False)),
])


def managed_parameter(name):
    return name in ('KY', 'NONLINEAR_FLAG', 'N_SPECIES', 'N_TOROIDAL') or bool(
        re.fullmatch(r'(MASS|Z|DENS|DLNNDR)_[0-9]+', name))


def numeric_source(source):
    result = {}
    for name in source.keys():
        name = str(name)
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', name) or managed_parameter(name):
            continue
        try:
            number = float(source[name])
            if math.isfinite(number):
                result[name] = int(number) if number.is_integer() else number
        except (TypeError, ValueError, OverflowError):
            continue
    return result


def field_spec(name):
    if name in FIELDS:
        label, group, value, kind, positive = FIELDS[name]
        return dict(label=label, group=group, reference=value, kind=kind, positive=positive)
    group = ('time' if name.startswith(('DELTA_T', 'PRINT_', 'TIME_')) else
             'model' if name.startswith(('COLLISION_', 'NU_')) else
             'algorithm' if name.startswith(('DISSIPATION', 'LINSOLVE', 'SOLVER', 'PRECISION')) else 'other')
    integer = name.startswith('N_') or name.endswith(('_FLAG', '_MODEL', '_METHOD', '_MODE'))
    return dict(label='数值', group=group, reference=None, kind='int' if integer else 'float', positive=False)


def parameter_catalog(sources):
    names = set(FIELDS)
    for source in sources:
        names.update(numeric_source(source))
    return OrderedDict((name, field_spec(name)) for name in list(FIELDS) + sorted(names - set(FIELDS)))


def scan_parameter_names(physics, dimensions):
    names = set()
    keys = {1: ('Para',), 2: ('Para_x', 'Para_y'), 3: ('Para_x', 'Para_y', 'Para_z')}.get(dimensions, ())
    group = physics.get(str(dimensions) + 'd', {})
    for key in keys:
        names.add(str(group.get(key, '')))
        index = 2
        while key + str(index) in group:
            names.add(str(group[key + str(index)]))
            index += 1
    return names


def initialize_parameters(physics, source, factory=dict):
    parameters = physics.setdefault('fixed_parameters', factory())
    if not hasattr(parameters, 'keys'):
        raise ValueError('固定参数配置必须是参数表。')
    if physics.get('scale_time_with_ky', None) is None:
        legacy = physics.get('time_scheme', [0, 0.01, 100.0])
        if hasattr(legacy, 'keys'):
            legacy = legacy.get('__ndarray_tolist__', [])
        try:
            scaling = float(legacy[0]) == 1
            if scaling:
                for name, value in zip(('DELTA_T', 'MAX_TIME'), legacy[1:3]):
                    item = parameters.setdefault(name, factory())
                    item.setdefault('enabled', True)
                    item.setdefault('value', float(value))
        except (IndexError, KeyError, TypeError, ValueError, OverflowError):
            scaling = False
        physics['scale_time_with_ky'] = scaling
    values = numeric_source(source)
    for name, spec in parameter_catalog([source]).items():
        item = parameters.setdefault(name, factory())
        if not hasattr(item, 'keys'):
            raise ValueError('固定参数 {} 缺少启用状态和数值。'.format(name))
        item.setdefault('enabled', False)
        item.setdefault('value', values.get(name, spec['reference']))
    return parameters


def validated_overrides(physics, sources, scan_names=()):
    parameters = physics.get('fixed_parameters', {})
    catalog = parameter_catalog(sources)
    overrides = {}
    for name, item in parameters.items():
        if not hasattr(item, 'keys'):
            raise ValueError('固定参数 {} 的配置无效。'.format(name))
        if not bool(item.get('enabled', False)) or name in scan_names:
            continue
        if name not in catalog or managed_parameter(name):
            raise ValueError('当前输入不支持固定参数 {}，请恢复该参数的输入值。'.format(name))
        if name not in FIELDS and any(name not in numeric_source(source) for source in sources):
            raise ValueError('部分所选输入没有参数 {}，请恢复输入值或分别编辑源输入。'.format(name))
        overrides[name] = parameter_value(name, item.get('value', None))
    if bool(physics.get('scale_time_with_ky', False)):
        if set(scan_names) & {'DELTA_T', 'MAX_TIME'}:
            raise ValueError('扫描时间步长或时长时，请关闭“按 ky 缩放时间”。')
        for source in sources:
            for name in ('DELTA_T', 'MAX_TIME'):
                if name not in source and name not in overrides:
                    raise ValueError('按 ky 缩放时间前，请显式设置 {}。'.format(name))
    return overrides


def parameter_value(name, raw):
    spec = field_spec(name)
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('{} 需要填写一个数值。'.format(name))
    if not math.isfinite(value):
        raise ValueError('{} 必须为有限数值。'.format(name))
    if spec['kind'] == 'int' and not value.is_integer():
        raise ValueError('{} 必须为整数。'.format(name))
    if name == 'DELTA_T_METHOD' and value not in (0, 1, 2, 3):
        raise ValueError('DELTA_T_METHOD 请选择 0（固定 RK4）或 1–3（自适应积分）。')
    if spec['positive'] and value <= 0:
        raise ValueError('{} 必须大于 0。'.format(name))
    return int(value) if value.is_integer() else value


def apply_parameters(source, physics, dimensions):
    names = scan_parameter_names(physics, dimensions)
    overrides = validated_overrides(physics, [source], names)
    for name, value in overrides.items():
        source[name] = value
    for name in names:
        if name in FIELDS and name not in source:
            source[name] = FIELDS[name][2]  # Each scan point replaces this reference.
    return overrides
