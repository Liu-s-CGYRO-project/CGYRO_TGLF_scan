"""Offline TGLF input catalog. References never change an input by themselves.

Defaults checked against GACODE tglf/bin/tglf_defaults.py on 2026-10-27
(Git blob 56136c7d8756e6ff9e111adf728e3257dcc21049). Keep physics defaults
separate from the explicit OMFIT scenario presets. Extend this catalog, rather
than a GUI-only whitelist, when adding parameters supported by a newer solver.
"""
from builtins import bool, float, hasattr, int, isinstance, min, range, str
from collections import OrderedDict
import re

GROUPS = OrderedDict([('常用参数', 'common'), ('模型与饱和', 'model'), ('网格与模态', 'grid'),
    ('碰撞与电磁', 'field'), ('粒子与梯度', 'species'), ('流与剪切', 'flow'),
    ('局部几何', 'geometry'), ('s-alpha 几何', 'sa'), ('算法与输出', 'expert'),
    ('当前输入的扩展参数', 'other'), ('全部参数', 'all')])

# name: (parser default, Chinese label, display group). Integer versus real
# types follow the parser, not whether an experimental value happens to be 1.
FIELDS = OrderedDict([
    ('NS', (2, '粒子种类数', 'species')),
    ('USE_TRANSPORT_MODEL', (True, '输运模型', 'model')),
    ('GEOMETRY_FLAG', (1, '几何模型', 'geometry')),
    ('SAT_RULE', (0, '饱和规则', 'model')),
    ('KYGRID_MODEL', (1, 'ky 网格模型', 'grid')),
    ('KY', (0.3, '归一化极向波数', 'grid')),
    ('NKY', (12, 'ky 网格点数', 'grid')),
    ('NMODES', (2, '保留模态数', 'grid')),
    ('NBASIS_MIN', (2, '最少基函数', 'grid')),
    ('NBASIS_MAX', (4, '最多基函数', 'grid')),
    ('NXGRID', (16, '积分节点数', 'grid')),
    ('WIDTH', (1.65, '模态宽度上限', 'grid')),
    ('WIDTH_MIN', (0.3, '模态宽度下限', 'grid')),
    ('NWIDTH', (21, '宽度搜索点数', 'grid')),
    ('FIND_WIDTH', (True, '搜索模态宽度', 'grid')),
    ('USE_BISECTION', (True, '二分宽度搜索', 'grid')),
    ('IBRANCH', (-1, '模态排序', 'grid')),
    ('USE_AVE_ION_GRID', (False, '平均离子网格', 'grid')),
    ('USE_BPER', (False, 'A 平行扰动', 'field')),
    ('USE_BPAR', (False, 'B 平行扰动', 'field')),
    ('BETAE', (0.0, '电子 beta', 'field')),
    ('XNUE', (0.0, '电子离子碰撞频率', 'field')),
    ('ZEFF', (1.0, '有效电荷数', 'field')),
    ('XNU_MODEL', (2, '碰撞模型', 'field')),
    ('XNU_FACTOR', (1.0, '碰撞项倍率', 'field')),
    ('DEBYE', (0.0, 'Debye 长度比', 'field')),
    ('DEBYE_FACTOR', (1.0, 'Debye 长度倍率', 'field')),
    ('USE_MHD_RULE', (True, '忽略曲率漂移中的压力梯度项', 'model')),
    ('ADIABATIC_ELEC', (False, '绝热电子', 'model')),
    ('USE_INBOARD_DETRAPPED', (False, '内侧鼓包去俘获', 'model')),
    ('THETA_TRAPPED', (0.7, '俘获粒子模型参数', 'model')),
    ('WDIA_TRAPPED', (0.0, '俘获粒子抗磁漂移参数', 'model')),
    ('ALPHA_ZF', (1.0, '带状流混合系数', 'model')),
    ('ETG_FACTOR', (1.25, 'ETG 饱和指数', 'model')),
    ('RLNP_CUTOFF', (18.0, '压力梯度截断值', 'model')),
    ('VPAR_MODEL', (0, '平行流模型', 'flow')),
    ('VPAR_SHEAR_MODEL', (1, '旧版平行流剪切模型', 'flow')),
    ('VEXB', (0.0, '旧版 ExB 速度', 'flow')),
    ('VEXB_SHEAR', (0.0, 'ExB 剪切', 'flow')),
    ('ALPHA_MACH', (0.0, '平行流倍率', 'flow')),
    ('ALPHA_E', (1.0, 'ExB 剪切倍率', 'flow')),
    ('ALPHA_P', (1.0, '平行流剪切倍率', 'flow')),
    ('ALPHA_QUENCH', (0.0, '剪切抑制模型', 'flow')),
    ('SIGN_BT', (1.0, '环向磁场方向', 'geometry')),
    ('SIGN_IT', (1.0, '环向电流方向', 'geometry')),
    ('RMIN_LOC', (0.5, '归一化小半径', 'geometry')),
    ('RMAJ_LOC', (3.0, '归一化大半径', 'geometry')),
    ('ZMAJ_LOC', (0.0, '磁面中心高度', 'geometry')),
    ('DRMINDX_LOC', (1.0, '小半径坐标导数', 'geometry')),
    ('DRMAJDX_LOC', (0.0, '大半径位移导数', 'geometry')),
    ('DZMAJDX_LOC', (0.0, '垂直位移导数', 'geometry')),
    ('KAPPA_LOC', (1.0, '拉长比', 'geometry')),
    ('S_KAPPA_LOC', (0.0, '拉长比剪切', 'geometry')),
    ('DELTA_LOC', (0.0, '三角形变', 'geometry')),
    ('S_DELTA_LOC', (0.0, '三角形变剪切', 'geometry')),
    ('ZETA_LOC', (0.0, '方形度', 'geometry')),
    ('S_ZETA_LOC', (0.0, '方形度剪切', 'geometry')),
    ('Q_LOC', (2.0, '安全因子绝对值', 'geometry')),
    ('Q_PRIME_LOC', (16.0, '归一化磁剪切', 'geometry')),
    ('P_PRIME_LOC', (0.0, '归一化压力梯度', 'geometry')),
    ('BETA_LOC', (0.0, '局部平衡 beta', 'geometry')),
    ('KX0_LOC', (0.0, '鼓包偏移', 'geometry')),
    ('RMIN_SA', (0.5, 's-alpha 小半径', 'sa')),
    ('RMAJ_SA', (3.0, 's-alpha 大半径', 'sa')),
    ('Q_SA', (2.0, 's-alpha 安全因子', 'sa')),
    ('SHAT_SA', (1.0, 's-alpha 磁剪切', 'sa')),
    ('ALPHA_SA', (0.0, 's-alpha 压力梯度', 'sa')),
    ('XWELL_SA', (0.0, '磁阱参数', 'sa')),
    ('THETA0_SA', (0.0, 's-alpha 鼓包角', 'sa')),
    ('B_MODEL_SA', (1, '垂直波数磁场因子', 'sa')),
    ('FT_MODEL_SA', (1, '俘获份额模型', 'sa')),
    ('NEW_EIKONAL', (True, '重新计算程函', 'geometry')),
    ('PARK', (1.0, '平行梯度项倍率', 'expert')),
    ('GHAT', (1.0, '曲率漂移闭合项倍率', 'expert')),
    ('GCHAT', (1.0, '曲率漂移不可约项倍率', 'expert')),
    ('WD_ZERO', (0.1, '曲率漂移截断', 'expert')),
    ('LINSKER_FACTOR', (0.0, 'Linsker 项倍率', 'expert')),
    ('GRADB_FACTOR', (0.0, '磁场梯度项倍率', 'expert')),
    ('FILTER', (2.0, '非漂移波过滤阈值', 'expert')),
    ('DAMP_PSI', (0.0, 'PSI 阻尼接口参数', 'expert')),
    ('DAMP_SIG', (0.0, 'SIG 阻尼接口参数', 'expert')),
    ('IFLUX', (True, '准线性权重与振幅', 'expert')),
    ('WRITE_WAVEFUNCTION_FLAG', (0, '本征函数输出', 'expert')),
    ('NN_MAX_ERROR', (-1.0, '神经网络误差阈值', 'expert')),
])

for _harmonic in ['COS' + str(i) for i in range(7)] + ['SIN' + str(i) for i in range(3, 7)]:
    for _shear in ('', 'S_'):
        FIELDS['SHAPE_' + _shear + _harmonic] = (0.0, '形状谐波' + ('剪切 ' if _shear else ' ') + _harmonic, 'geometry')

# Species fallbacks follow the native parser. Do not manufacture extra species:
# only 1..NS are offered, including an input's explicit newer-version fields.
SPECIES = OrderedDict([
    ('ZS', ((-1.0, 1.0, 0.0), '电荷数', 'species')),
    ('MASS', ((2.723e-4, 1.0, 0.0), '质量比', 'species')),
    ('AS', ((1.0, 1.0, 0.0), '密度比', 'species')),
    ('TAUS', ((1.0, 1.0, 0.0), '温度比', 'species')),
    ('RLNS', ((1.0, 1.0, 0.0), '密度逆梯度长度', 'species')),
    ('RLTS', ((3.0, 3.0, 0.0), '温度逆梯度长度', 'species')),
    ('VPAR', ((0.0, 0.0, 0.0), '平行流', 'flow')),
    ('VPAR_SHEAR', ((0.0, 0.0, 0.0), '平行流剪切', 'flow')),
    ('VNS_SHEAR', ((0.0, 0.0, 0.0), '密度剖面剪切接口', 'flow')),
    ('VTS_SHEAR', ((0.0, 0.0, 0.0), '温度剖面剪切接口', 'flow')),
])
SPECIES_PATTERN = re.compile(r'(' + '|'.join(SPECIES) + r')_([1-9][0-9]*)$')
MANAGED = {'NS', 'USE_TRANSPORT_MODEL'}
CHOICES = {'SAT_RULE': [0, 1, 2, 3], 'KYGRID_MODEL': [0, 1, 2, 3, 4, 5]}
INTEGERS = {name for name, (value, _, _) in FIELDS.items() if isinstance(value, int) and not isinstance(value, bool)}
COMMON_NAMES = ('SAT_RULE', 'KYGRID_MODEL', 'KY', 'NKY', 'NMODES', 'NBASIS_MIN', 'NBASIS_MAX',
    'NXGRID', 'WIDTH', 'WIDTH_MIN', 'NWIDTH', 'FIND_WIDTH', 'USE_BPER', 'USE_BPAR', 'XNU_MODEL',
    'USE_MHD_RULE', 'ADIABATIC_ELEC', 'USE_BISECTION', 'IBRANCH', 'VPAR_MODEL', 'VPAR_SHEAR_MODEL',
    'ALPHA_E', 'ALPHA_P', 'ALPHA_QUENCH', 'ETG_FACTOR', 'ALPHA_ZF', 'WDIA_TRAPPED', 'USE_AVE_ION_GRID')
COMMON = OrderedDict((name, FIELDS[name][:2]) for name in COMMON_NAMES)


def scalar(value):
    return value.tolist() if hasattr(value, 'tolist') else value


def numeric_parameters(source):
    """Read one input mapping, never output files or a whole result tree."""
    result = OrderedDict()
    for name, value in source.items():
        if name in ('rho', 'USE_TRANSPORT_MODEL') or str(name).startswith('__'):
            continue
        value = scalar(value)
        if isinstance(value, (int, float, bool)):
            result[str(name)] = value
    return result


def field_spec(name):
    if name in FIELDS:
        return FIELDS[name]
    species = SPECIES_PATTERN.fullmatch(name)
    if species:
        values, label, group = SPECIES[species[1]]
        index = int(species[2])
        return values[min(index - 1, 2)], label + ' · 粒子 ' + str(index), group
    return 0.0, '输入扩展参数', 'other'


def parameter_catalog(source):
    """Merge scalar parser references with this input; no defaults are applied."""
    explicit = numeric_parameters(source)
    catalog = OrderedDict((name, spec) for name, spec in FIELDS.items() if name not in MANAGED)
    try:
        species_count = int(scalar(source.get('NS', 0)))
    except (TypeError, ValueError, OverflowError):
        species_count = 0  # Invalid NS is diagnosed when preparing a run.
    for index in range(1, min(species_count, 7) + 1):
        for family in SPECIES:
            name = family + '_' + str(index)
            catalog[name] = field_spec(name)
    for name, value in explicit.items():
        species = SPECIES_PATTERN.fullmatch(name)
        if name in MANAGED or (species and int(species[2]) > species_count):
            continue
        _, label, group = field_spec(name)
        catalog[name] = value, label, group
    return catalog


def parameter_values(source):
    return OrderedDict((name, spec[0]) for name, spec in parameter_catalog(source).items())
