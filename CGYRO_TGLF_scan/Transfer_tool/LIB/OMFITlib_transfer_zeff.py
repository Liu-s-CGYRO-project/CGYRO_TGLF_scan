"""Prescribed impurity collision effects with normalized hydrogenic main ions."""
from builtins import any, dict, float, int, len, list, max, min, str
from collections import OrderedDict
import math
import numpy as np
from scipy.interpolate import CubicSpline

ZEFF_RULE = 'normalized_main_prescribed_zeff_v1'
ZEFF_DEFAULTS = dict(zeff_collision_model=1)
ZEFF_COLLISIONS = OrderedDict([('1 Lorentz', 1), ('5 简化 Lorentz', 5)])


def zeff_options(options):
    values = {key: options.get(key, default) for key, default in ZEFF_DEFAULTS.items()}
    model = float(values['zeff_collision_model'])
    if model not in (1, 5):
        raise ValueError('指定 Zeff 需要 CGYRO 碰撞模型 1 或 5。')
    values['zeff_collision_model'] = int(model)
    values['zeff_rule'] = ZEFF_RULE
    return values


def zeff_profile(source, options, mains):
    """Capture original Zeff before particle deletion / native derived updates."""
    if any(not math.isclose(float(ion['charge']), 1.0, rel_tol=0, abs_tol=1e-8) for ion in mains):
        raise ValueError('主离子归一化 + Zeff 方案只适用于 Z=1 的 H/D/T 主离子。')
    values = zeff_options(options)
    x = np.asarray(source['rmin'], dtype=float)
    if x.ndim != 1 or len(x) < 2 or not np.all(np.isfinite(x)) or x[-1] <= 0 or np.any(np.diff(x) <= 0):
        raise ValueError('原剖面的 rmin 网格无效，无法生成 Zeff。')
    original = source.get('z_eff', None)
    used = 'profile'
    if original is None:
        original = source.calc_zeff()
        used = 'composition'
    original = np.asarray(original, dtype=float)
    if original.ndim == 0:
        original = np.full_like(x, float(original))
    if original.shape != x.shape or not np.all(np.isfinite(original)) or np.any(original < 1 - 1e-10):
        raise ValueError('原剖面的 Zeff 必须是与 rmin 对应且不小于 1 的有限数值。')
    return dict(rule=ZEFF_RULE, source='profile', original_source=used,
                collision_model=values['zeff_collision_model'],
                rmin_normalized=(x / x[-1]).tolist(), values=original.tolist())


def prescribe_local_zeff(value, kind, record):
    """Apply after charge closure; never store audit keys in a solver card."""
    if record.get('rule', '') != ZEFF_RULE:
        raise ValueError('Zeff 规则记录缺失，请重新运行 Transfer_tool。')
    x, y = np.asarray(record['rmin_normalized']), np.asarray(record['values'])
    radius = float(value['RMIN' if kind == 'cgyro' else 'RMIN_LOC'])
    if not math.isfinite(radius) or radius < x[0] - 1e-10 or radius > x[-1] + 1e-10:
        raise ValueError('局部输入半径超出 Zeff 剖面范围。')
    # Match expro_locsim's natural cubic spline in normalized minor radius.
    zeff = float(CubicSpline(x, y, bc_type='natural')(min(max(radius, x[0]), x[-1])))
    if not math.isfinite(zeff) or zeff < 1 - 1e-10:
        raise ValueError('Zeff 插值结果小于 1 或无效，请检查原剖面。')
    zeff = max(1.0, zeff)  # Roundoff at the physical lower boundary only.
    if kind == 'cgyro':
        value['Z_EFF'], value['Z_EFF_METHOD'] = zeff, 1
        value['COLLISION_MODEL'] = int(record['collision_model'])
    elif kind == 'tglf':
        value['ZEFF'] = zeff
    else:
        raise ValueError('不支持的 Zeff 局部输入类型。')
    return dict(rule=ZEFF_RULE, value=zeff, radius=radius, source=record['source'],
                collision_model=record['collision_model'] if kind == 'cgyro' else None)
