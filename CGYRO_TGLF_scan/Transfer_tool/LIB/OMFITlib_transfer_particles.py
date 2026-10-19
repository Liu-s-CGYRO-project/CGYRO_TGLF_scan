"""Species presets for OMFITinputgacode; densities in 1e19/m3, temperatures in keV.

Work on a duplicate. Electron density is fixed; automatically identified main
ions jointly close charge density and its derivative, retaining their ratios.
No slowing-down distribution is fitted.
"""
from builtins import abs, any, dict, enumerate, float, int, len, list, max, next, range, round, sorted, str, sum
from collections import OrderedDict
import math
import numpy as np
from OMFITlib_transfer_zeff import zeff_options, zeff_profile

PRESETS = OrderedDict([
    ('保留所有粒子', 'all'),
    ('慢化快离子（热化处理）', 'thermalize'),
    ('仅保留主离子和等效杂质', 'equivalent'),
    ('主离子 / 等效杂质 / 等效快粒子', 'separate_fast'),
    ('仅保留主离子和 Zeff', 'main_only'),
])
DESCRIPTIONS = {
    'all': '保留全部离子及热 / 快类型，所有主离子按原密度比例共同校正准中性。',
    'thermalize': '同种热杂质合并；对应任一主离子的快离子独立保留，温度、环向及极向流速采用所选热杂质的值。缺少所需热离子时停止。此为热化近似，压力会改变。',
    'equivalent': '主离子限定为平均 ni/ne > 30% 的热 H/D/T；快离子及少量氢同位素与其他非主离子一起合成等效辅助物种。各半径保持辅助组电荷、Zeff 贡献、质量及电荷密度梯度，主离子保留稀释份额。辅助温度可保留原总压力或跟随热主离子；后者会改变总压力。H/D/T 扫描再合并热主离子。',
    'separate_fast': '电子保留；平均 ni/ne > 30% 的热 H/D/T 合成一个主离子，其余 therm 粒子（含少量 H/D/T）合成等效热杂质，全部 fast 粒子合成独立等效快粒子。适用于原热杂质可近似与主离子热平衡的情形：热杂质温度及温度梯度随合并主离子，密度梯度保持其自身电荷密度梯度；各组保留电荷、Zeff 贡献和质量密度。快粒子独立保留本组压力及压力梯度。热杂质压力不再严格保持，记录总压力和总压力梯度差额，不通过其他物种或电子比压补偿。主离子保留稀释份额，H/D/T 扫描只改其质量。无密度的辅助组省略。等效快粒子使用温度描述，不拟合慢化分布或各向异性。',
    'main_only': '先对保留全部粒子的原始剖面副本做准中性校正，再计算完整组成的 Zeff（ΣniZi²/ne），不读取输入文件的 Zeff 字段。然后只保留电子及 Z=1 主离子，保持主离子比例并再次闭合电荷，局部归一化后主离子密度之和为 1。Zeff 仅表示杂质碰撞效应，不包含杂质响应或输运。CGYRO 使用所选 Lorentz 碰撞模型和 Z_EFF_METHOD=1。',
}
EQUIVALENT_TEMPERATURES = OrderedDict([
    ('保留原总压力', 'pressure'),
    ('温度随热主离子', 'main_ion'),
])
PARTICLE_DEFAULTS = {'particle_mode': 'all', 'thermal_reference_ion': 0,
                     'equivalent_temperature': 'pressure'}
MAIN_ION_THRESHOLD = 0.30
MAIN_ION_RULE = 'mean_ni_over_ne_after_source_neutrality_v2'
EQUIVALENT_RULE = 'thermal_hdt_auxiliary_local_moments_v2'
SEPARATE_FAST_RULE = 'merged_thermal_main_thermal_impurity_fast_pressure_v2'
LOCAL_EQUIVALENT_MODES = ('equivalent', 'separate_fast')
NEUTRALITY_RULE = 'source_first_fixed_ne_density_gradient_curvature_v3'
TOLERANCE = 1e-8
ROUND_OFF = 64 * np.finfo(float).eps


def particle_options(options):
    values = {key: options.get(key, default) for key, default in PARTICLE_DEFAULTS.items()}
    if values['particle_mode'] == 'main_only_recomputed':
        values['particle_mode'] = 'main_only'  # Migrate saved settings and script arguments.
    if values['particle_mode'] not in DESCRIPTIONS:
        raise ValueError('请选择有效的粒子处理方案。')
    if values['particle_mode'] == 'main_only':
        values.update(zeff_options(options))
    for key in ('thermal_reference_ion',):
        raw = float(values[key])
        if not math.isfinite(raw) or raw < 0 or int(raw) != raw:
            raise ValueError('粒子选择无效，请重新选择温度 / 流速来源。')
        values[key] = int(raw)
    try:
        minimum, maximum = float(options['minimum']), float(options['maximum'])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('自动识别主离子需要本轮计算的起始和结束半径。')
    coordinate = options.get('coordinate', 'rho')
    if not math.isfinite(minimum) or not math.isfinite(maximum) or not 0 <= minimum < maximum <= 1:
        raise ValueError('半径范围需满足 0 ≤ 起始半径 < 结束半径 ≤ 1。')
    if coordinate not in ('rho', 'r/a'):
        raise ValueError('请选择 rho 或 r/a 坐标。')
    # Include the rule and interval in provenance, invalidating old/manual results.
    values.update(dict(minimum=minimum, maximum=maximum, coordinate=coordinate,
                  main_ion_rule=MAIN_ION_RULE, main_ion_threshold=MAIN_ION_THRESHOLD,
                  neutrality_rule=NEUTRALITY_RULE))
    if values['particle_mode'] == 'equivalent':
        values['equivalent_rule'] = EQUIVALENT_RULE
        if values['equivalent_temperature'] not in EQUIVALENT_TEMPERATURES.values():
            raise ValueError('请选择有效的等效辅助物种温度方案。')
    else:
        # An inactive UI choice must not invalidate other presets' old results.
        values.pop('equivalent_temperature')
    if values['particle_mode'] == 'separate_fast':
        values['equivalent_rule'] = SEPARATE_FAST_RULE
    return values


def species(profile):
    count = int(profile['N_ION'])
    if count < 1 or count != profile['N_ION'] or len(profile['IONS']) != count:
        raise ValueError('input.gacode 的 N_ION 与 IONS 不一致。')
    result = []
    for index in range(1, count + 1):
        name, charge, mass, kind = profile['IONS'][index]
        charge, mass = float(charge), float(mass)
        if not math.isfinite(charge) or charge <= 0 or not math.isfinite(mass) or mass <= 0:
            raise ValueError('第 {} 个离子的电荷和质量必须为有限正数。'.format(index))
        kind = str(kind).strip().lower()
        if kind not in ('therm', 'fast'):
            raise ValueError('第 {} 个离子的类型应为 therm 或 fast。'.format(index))
        result.append(dict(index=index, name=str(name), charge=charge, mass=mass, kind=kind))
    return result


def species_label(ion):
    return '{}：{} · Z={:g}，A={:g} · {}'.format(
        ion['index'], ion['name'], ion['charge'], ion['mass'],
        '原快离子（独立热化）' if ion.get('thermalized_fast', False) else ('快离子' if ion['kind'] == 'fast' else '热离子'))


def is_thermal_hydrogen(ion):
    """Use source type/Z/mass, not names or a guessed temperature threshold.

    input.gacode masses are in atomic mass units (not local CGYRO m/m_D).
    Accept integer and physical H/D/T masses; trace fuel is excluded later by
    the existing abundance threshold, so it remains in the auxiliary group.
    """
    return (ion['kind'] == 'therm' and math.isclose(ion['charge'], 1.0, rel_tol=0, abs_tol=1e-8)
            and any(abs(ion['mass'] - mass) < 0.05 for mass in (1, 2, 3)))


def thermal_reference_choices(profile, main_ions):
    result = OrderedDict([('自动（剖面中的首个热杂质）', 0)])
    if profile is not None:
        for ion in species(profile):
            if ion['kind'] == 'therm' and not any(_same_species(ion, main) for main in main_ions):
                result[species_label(ion)] = ion['index']
    return result


def _array(profile, key, shape=None, positive=False, nonnegative=False):
    # OMFIT returns zeros for missing ion fields; required quantities must exist.
    if key not in profile:
        raise ValueError('input.gacode 缺少 ' + key)
    value = np.array(profile[key], dtype=float, copy=True)
    if value.ndim != 1 or value.size < 2 or (shape is not None and value.shape != shape) or not np.all(np.isfinite(value)):
        raise ValueError(key + ' 的径向网格或数值无效。')
    if (positive and np.any(value <= 0)) or (nonnegative and np.any(value < 0)):
        raise ValueError(key + ' 包含无效的非正密度 / 温度。')
    return value


def _validate_profile(profile):
    ne = _array(profile, 'ne', positive=True)
    profile['ne'] = ne
    profile['Te'] = _array(profile, 'Te', ne.shape, positive=True)
    for ion in species(profile):
        suffix = str(ion['index'])
        profile['ni_' + suffix] = _array(profile, 'ni_' + suffix, ne.shape, nonnegative=True)
        profile['Ti_' + suffix] = _array(profile, 'Ti_' + suffix, ne.shape, positive=True)
        for key in ('vtor_', 'vpol_'):
            # These optional arrays are required by OMFIT's add/del_ion methods.
            profile[key + suffix] = (_array(profile, key + suffix, ne.shape)
                                     if key + suffix in profile else np.zeros_like(ne))
    return ne


def _detect_main_ions(profile, options):
    """Classify the supplied full composition by the interval mean of ni/ne.

    Integrate the piecewise-linear fraction in the selected coordinate, including
    both interval endpoints. No volume weighting or output-grid dependence.
    """
    options = particle_options(options)
    ne = _array(profile, 'ne', positive=True)
    coordinate = options['coordinate']
    grid = _array(profile, 'rho' if coordinate == 'rho' else 'rmin', ne.shape)
    if coordinate == 'r/a':
        if grid[-1] <= 0:
            raise ValueError('r/a 坐标需要正的边界小半径。')
        grid /= grid[-1]
    if np.any(np.diff(grid) <= 0):
        raise ValueError('主离子识别需要严格递增的径向网格。')
    lower, upper = options['minimum'], options['maximum']
    if lower < grid[0] - ROUND_OFF or upper > grid[-1] + ROUND_OFF:
        raise ValueError('计算半径范围超出剖面 {} 网格 [{:g}, {:g}]，无法计算平均 ni/ne。'.format(
            coordinate, grid[0], grid[-1]))
    knots = np.concatenate(([lower], grid[(grid > lower) & (grid < upper)], [upper]))
    intervals = np.diff(knots) / (upper - lower)
    candidates, largest = [], 0.0
    for ion in species(profile):
        if options['particle_mode'] in LOCAL_EQUIVALENT_MODES and not is_thermal_hydrogen(ion):
            # Also applies during the source-first neutrality correction: fast
            # fuel must not absorb missing charge and become thermal main fuel.
            continue
        fraction = _array(profile, 'ni_' + str(ion['index']), ne.shape, nonnegative=True) / ne
        if not np.all(np.isfinite(fraction)):
            raise ValueError('离子 ni/ne 不是有限数值。')
        values = np.interp(knots, grid, fraction)
        average = float(np.sum(0.5 * (values[:-1] + values[1:]) * intervals))
        largest = max(largest, average)
        # Do not turn exactly 30% into a main ion through summation roundoff.
        if average - MAIN_ION_THRESHOLD > ROUND_OFF * max(1.0, abs(average)):
            candidates.append(dict(ion, mean_fraction=average))
    if not candidates:
        group = '热 H/D/T 主离子' if options['particle_mode'] in LOCAL_EQUIVALENT_MODES else '主离子'
        raise ValueError('本轮半径范围内没有平均 ni/ne > 30% 的{}（候选最高 {:.6g}%）；请检查剖面、粒子类型和半径范围。'.format(group, largest * 100))
    return sorted(candidates, key=lambda ion: (-ion['mean_fraction'], ion['index']))


def detect_main_ions(source, options):
    """Preview selection using the same neutral source copy as generation."""
    profile, _ = prepare_source_profile(source, options)
    return _detect_main_ions(profile, options)


def main_ion_label(ion):
    return '{} · 平均 ni/ne={:.4g}%'.format(species_label(ion), ion['mean_fraction'] * 100)


def _close_densities(charges, densities, ne, main_count):
    """Array contract: positive-ion arrays (species, radius); mains come first."""
    weighted = charges[:, None] * densities
    main_charge = np.sum(weighted[:main_count], axis=0)
    target = ne - np.sum(weighted[main_count:], axis=0)
    if not np.all(np.isfinite(target)) or np.any(target < -ROUND_OFF * ne):
        raise ValueError('非主离子电荷密度超过电子密度，准中性校正将产生负的主离子密度；请检查原始剖面。')
    target = np.maximum(target, 0.0)
    zero = main_charge == 0
    if np.any(zero & (target > ROUND_OFF * ne)):
        raise ValueError('主离子总密度为零处无法按原比例补齐电荷，请检查剖面。')
    factor = np.divide(target, main_charge, out=np.zeros_like(ne), where=~zero)
    densities = densities.copy()
    densities[:main_count] *= factor
    residual = (np.sum(charges[:, None] * densities, axis=0) - ne) / ne
    if not np.all(np.isfinite(densities)) or np.max(np.abs(residual)) > TOLERANCE:
        raise ValueError('粒子密度未通过准中性校正。')
    return densities, float(np.max(np.abs(residual)))


def _close_gradients(charges, densities, gradients, ne, electron_gradient, main_count):
    weighted = charges[:, None] * densities
    main_charge = np.sum(weighted[:main_count], axis=0)
    target = ne * electron_gradient - np.sum(weighted * gradients, axis=0)
    scale = np.maximum(ne, np.abs(ne * electron_gradient) + np.sum(np.abs(weighted * gradients), axis=0))
    zero = main_charge == 0
    if np.any(zero & (np.abs(target) > TOLERANCE * scale)):
        raise ValueError('主离子总密度为零处无法满足密度梯度准中性。')
    correction = np.divide(target, main_charge, out=np.zeros_like(ne), where=~zero)
    gradients = gradients.copy()
    # A common density multiplier gives a common logarithmic-gradient offset.
    gradients[:main_count] += correction
    residual = (np.sum(weighted * gradients, axis=0) - ne * electron_gradient) / scale
    if not np.all(np.isfinite(gradients)) or np.max(np.abs(residual)) > TOLERANCE:
        raise ValueError('密度梯度未通过准中性校正。')
    return gradients, float(np.max(np.abs(residual)))


def _ordered_ions(profile, main_indices=None):
    ions = species(profile)
    if main_indices is None:
        return ions
    order = list(main_indices) + [ion['index'] for ion in ions if ion['index'] not in main_indices]
    return [ions[index - 1] for index in order]


def _close_density(profile, main_count, main_indices=None):
    """Close against fixed ne, never invoke OMFIT's negative-density ne fallback."""
    ne = np.asarray(profile['ne'], dtype=float)
    ions = _ordered_ions(profile, main_indices)
    charges = np.array([ion['charge'] for ion in ions])
    densities = np.array([profile['ni_' + str(ion['index'])] for ion in ions])
    densities, error = _close_densities(charges, densities, ne, main_count)
    for index in range(main_count):
        profile['ni_' + str(ions[index]['index'])] = densities[index]
    profile['z_eff'] = profile.calc_zeff()
    profile['ptot'] = profile.calc_ptot()
    return error


def _close_profile_gradient(profile, main_count, main_indices=None):
    ne, ions = np.asarray(profile['ne'], dtype=float), _ordered_ions(profile, main_indices)
    electron_gradient = _array(profile, 'dlnnedr', ne.shape)
    charges = np.array([ion['charge'] for ion in ions])
    densities = np.array([profile['ni_' + str(ion['index'])] for ion in ions])
    gradients = np.array([_array(profile, 'dlnnidr_' + str(ion['index']), ne.shape) for ion in ions])
    gradients, error = _close_gradients(charges, densities, gradients, ne, electron_gradient, main_count)
    for index in range(main_count):
        profile['dlnnidr_' + str(ions[index]['index'])] = gradients[index]
    # Keep the total pressure gradient consistent with the corrected species.
    weighted = ne * profile['Te'] * (electron_gradient + _array(profile, 'dlntedr', ne.shape))
    for ion in ions:
        suffix = str(ion['index'])
        weighted += profile['ni_' + suffix] * profile['Ti_' + suffix] * (
            profile['dlnnidr_' + suffix] + _array(profile, 'dlntidr_' + suffix, ne.shape))
    profile['dlnptotdr'] = weighted / _pressure_nt(profile)
    return error


def _same_species(left, right):
    if left['charge'] != right['charge']:
        return False
    if math.isclose(left['mass'], right['mass'], rel_tol=1e-6, abs_tol=1e-6):
        return True
    # Accept rounded isotope masses (e.g. D=2 or 2.014); never merge D with T
    # or infer that an effective DT mass of 2.5 identifies either isotope.
    mass_number = round(left['mass'])
    return (mass_number > 0 and round(right['mass']) == mass_number
            and abs(left['mass'] - mass_number) < 0.05 and abs(right['mass'] - mass_number) < 0.05)


def _thermal_reference(profile, options, ions, mains):
    """Snapshot the chosen thermal impurity before ion reordering/deletion."""
    if not any(ion['kind'] == 'fast' and any(_same_species(ion, main) for main in mains) for ion in ions):
        return None
    candidates = [ion for ion in ions if ion['kind'] == 'therm' and not any(_same_species(ion, main) for main in mains)]
    selected = options['thermal_reference_ion']
    if selected:
        candidates = [ion for ion in candidates if ion['index'] == selected]
    if not candidates:
        raise ValueError('对应主离子的快离子独立热化需要热杂质作为温度 / 流速来源；请选择不属于任何主离子种类的热离子或补充剖面。')
    reference = candidates[0]
    suffix = str(reference['index'])
    return dict(species=dict(reference), arrays={quantity: profile[quantity + suffix].copy()
                for quantity in ('Ti_', 'vtor_', 'vpol_')})


def _thermalize(profile, main_count, thermal_reference=None):
    changes = {'merged': [], 'kept_separate': []}
    mains = species(profile)[:main_count]
    # Recompute indices after each deletion; isotope identity is charge AND mass.
    while True:
        ions = species(profile)
        fast = next((ion for ion in ions if ion['kind'] == 'fast'
                     and not any(_same_species(ion, main) for main in mains)), None)
        if fast is None:
            break
        targets = [ion for ion in ions if ion['index'] > main_count
                   and ion['kind'] == 'therm' and _same_species(ion, fast)]
        if not targets:
            raise ValueError('{} 无相同电荷和质量的热离子，无法自动热化合并；请先补充同种热离子。'.format(species_label(fast)))
        target = targets[0]
        changes['merged'].append('{} → {}'.format(species_label(fast), species_label(target)))
        profile.del_ion(fast['index'], add_density_to_ion=target['index'], verbose=False)
    # Record independent populations only after deletions, so indices stay valid.
    for fast in species(profile):
        if fast['kind'] != 'fast':
            continue
        if thermal_reference is None:
            raise ValueError('缺少热杂质的温度 / 流速参考，已停止独立热化。')
        changes['kept_separate'].append(dict(index=fast['index'], source=species_label(fast),
            reference=species_label(thermal_reference['species']), reference_kind='thermal_impurity'))
        for quantity in ('Ti_', 'vtor_', 'vpol_'):
            profile[quantity + str(fast['index'])] = thermal_reference['arrays'][quantity].copy()
        profile['IONS'][fast['index']][3] = 'therm'
    return changes


def _pressure_nt(profile):
    # Only used in a dimensionless before/after ratio; no unit conversion needed.
    return profile['ne'] * profile['Te'] + sum(
        (profile['ni_' + str(i)] * profile['Ti_' + str(i)] for i in range(1, int(profile['N_ION']) + 1)),
        np.zeros_like(profile['ne']))


def prepare_source_profile(source, options):
    """Neutralize the full original composition before any preset or selection.

    Initial abundant populations only identify who balances charge; no ion is
    removed, reordered, merged or thermalized. The final selection is made from
    this corrected full composition, in both the GUI preview and generation.
    """
    options = particle_options(options)
    profile = source.duplicate()
    ne = _validate_profile(profile).copy()
    ions = species(profile)
    mains = _detect_main_ions(profile, options)
    indices = [ion['index'] for ion in mains]
    before = np.array([profile['ni_' + str(ion['index'])] for ion in ions])
    charges = np.array([ion['charge'] for ion in ions])
    electron_gradient = _array(profile, 'dlnnedr', ne.shape)
    pressure = _pressure_nt(profile)
    before_density = float(np.max(np.abs(np.sum(charges[:, None] * before, axis=0) / ne - 1.0)))
    density_error = _close_density(profile, len(mains), indices)
    gradient_error = _close_profile_gradient(profile, len(mains), indices)
    _validate_profile(profile)
    if not np.array_equal(np.asarray(profile['ne']), ne):
        raise ValueError('原始剖面准中性校正改变了电子密度，已停止生成。')
    if not np.array_equal(_array(profile, 'dlnnedr', ne.shape), electron_gradient):
        raise ValueError('原始剖面准中性校正改变了电子密度梯度，已停止生成。')
    after = np.array([profile['ni_' + str(ion['index'])] for ion in ions])
    residual = float(np.max(np.abs(np.sum(charges[:, None] * after, axis=0) / ne - 1.0)))
    if not math.isfinite(residual) or residual > TOLERANCE:
        raise ValueError('原始完整剖面未通过准中性检查，尚未执行粒子方案。')
    gradients = np.array([_array(profile, 'dlnnidr_' + str(ion['index']), ne.shape) for ion in ions])
    moments = charges[:, None] * after * gradients
    target = ne * electron_gradient
    scale = np.maximum(ne, np.abs(target) + np.sum(np.abs(moments), axis=0))
    residual_gradient = float(np.max(np.abs(np.sum(moments, axis=0) - target) / scale))
    if not math.isfinite(residual_gradient) or residual_gradient > TOLERANCE:
        raise ValueError('原始完整剖面的密度梯度未通过准中性检查，尚未执行粒子方案。')
    return profile, dict(rule=NEUTRALITY_RULE, stage='full_source_before_particle_selection',
                         fixed_electron_density=True, balancing_ions=[dict(ion) for ion in mains],
                         ion_count=len(ions), density_residual_before=before_density,
                         density_residual=max(density_error, residual), gradient_residual=max(gradient_error, residual_gradient),
                         max_relative_pressure_change=float(np.max(np.abs(_pressure_nt(profile) / pressure - 1.0))))


def prepare_particles(source, options):
    """Return (processed OMFITinputgacode, compact provenance), preserving source."""
    options = particle_options(options)
    profile, source_neutrality = prepare_source_profile(source, options)
    ne_before = np.asarray(profile['ne']).copy()
    before = species(profile)
    pressure_before = _pressure_nt(profile)
    mains = _detect_main_ions(profile, options)
    main_indices = [ion['index'] for ion in mains]
    main_count = len(mains)
    prescribed_zeff = zeff_profile(profile, options, mains) if options['particle_mode'] == 'main_only' else None
    thermal_reference = (_thermal_reference(profile, options, before, mains)
                         if options['particle_mode'] == 'thermalize' else None)
    profile.reorder_ions(main_indices + [ion['index'] for ion in before if ion['index'] not in main_indices], verbose=False)
    # Native del_ion adds removed charge to ion 1. Restore these ratios afterwards.
    main_densities = np.array([profile['ni_' + str(i)] for i in range(1, main_count + 1)], copy=True)
    _close_density(profile, main_count)
    reference_zeff = np.array(profile.calc_zeff(), dtype=float, copy=True)
    changes = {'merged': [], 'kept_separate': []}
    mode = options['particle_mode']
    if mode == 'thermalize':
        changes = _thermalize(profile, main_count, thermal_reference)
    elif mode == 'main_only':
        for index in range(int(profile['N_ION']), main_count, -1):
            profile.del_ion(index, add_density_to_ion=1, verbose=False)
        for index in range(main_count):
            profile['ni_' + str(index + 1)] = main_densities[index].copy()
    # A profile has one scalar Z/MASS per species. Keep its full composition for
    # native locpargen; collapse impurities separately in each generated input.
    # This also avoids add_ion/locpargen truncating an effective fractional Z.
    if int(profile['N_ION']) > 9:
        raise ValueError('当前 Transfer_tool 的 TGYRO 接口最多支持 9 种离子；等效方案在局部输入阶段合成，请先简化源剖面。')
    density_error = _close_density(profile, main_count)
    # Rebuild OMFIT/GACODE derived fields after deleting/reordering ion arrays.
    profile.consistent_derived()
    if not np.array_equal(np.asarray(profile['ne']), ne_before):
        raise ValueError('派生量更新改变了电子密度，已停止生成。')
    _validate_profile(profile)
    for item in changes['kept_separate']:
        for quantity in ('Ti_', 'vtor_', 'vpol_'):
            if not np.allclose(profile[quantity + str(item['index'])], thermal_reference['arrays'][quantity], rtol=1e-12, atol=0):
                raise ValueError('派生量更新未保留所选热杂质的温度 / 流速，已停止独立热化。')
    density_error = max(density_error, _close_density(profile, main_count))
    original_total = np.sum(main_densities, axis=0)
    processed_mains = np.array([profile['ni_' + str(i)] for i in range(1, main_count + 1)])
    processed_total = np.sum(processed_mains, axis=0)
    populated = (original_total > 0) & (processed_total > 0)
    expected_ratios = np.divide(main_densities, original_total, out=np.zeros_like(main_densities), where=populated)
    actual_ratios = np.divide(processed_mains, processed_total, out=np.zeros_like(processed_mains), where=populated)
    ratio_error = float(np.max(np.abs(actual_ratios - expected_ratios)))
    if ratio_error > TOLERANCE:
        raise ValueError('派生量更新改变了主离子密度比例，已停止生成。')
    gradient_error = _close_profile_gradient(profile, main_count)
    zeff_error = float(np.max(np.abs(profile['z_eff'] - reference_zeff)))
    if mode in LOCAL_EQUIVALENT_MODES and zeff_error > TOLERANCE * max(1.0, float(np.max(reference_zeff))):
        raise ValueError('等效杂质处理未能保持 Zeff。')
    after = species(profile)
    for index, ion in enumerate(after):
        ion['is_main'] = index < main_count
        if ion['is_main']:
            ion.update(dict(source_index=mains[index]['index'], mean_fraction=mains[index]['mean_fraction']))
        elif mode in LOCAL_EQUIVALENT_MODES:
            ion['source_index'] = [original['index'] for original in before
                                   if original['index'] not in main_indices][index - main_count]
    for item in changes['kept_separate']:
        after[item['index'] - 1]['thermalized_fast'] = True
    report = dict(options=options, before=before, after=after, main_ions=mains, main_count=main_count,
                  source_neutrality=source_neutrality,
                  equivalent_stage='local_inputs' if mode in LOCAL_EQUIVALENT_MODES else None,
                  thermal_reference=thermal_reference['species'] if thermal_reference is not None else None,
                  density_residual=density_error, gradient_residual=gradient_error,
                  main_ratio_residual=ratio_error,
                  max_zeff_change=zeff_error,
                  max_relative_pressure_change=float(np.max(np.abs(_pressure_nt(profile) / pressure_before - 1.0))))
    report.update(changes)
    if prescribed_zeff is not None:
        report['prescribed_zeff'] = prescribed_zeff
    return profile, report


def _local_arrays(value, kind):
    """Read signed charges, densities and gradients without changing the card."""
    if kind == 'cgyro':
        count_key, density_key, charge_key, gradient_key = 'N_SPECIES', 'DENS_', 'Z_', 'DLNNDR_'
    elif kind == 'tglf':
        count_key, density_key, charge_key, gradient_key = 'NS', 'AS_', 'ZS_', 'RLNS_'
    else:
        raise ValueError('不支持的局部输入类型。')
    raw_count = float(value[count_key])
    if not math.isfinite(raw_count) or raw_count < 2 or int(raw_count) != raw_count:
        raise ValueError('局部输入需要电子和至少一种离子。')
    count = int(raw_count)
    indices = list(range(1, count + 1))
    charges = np.array([float(value[charge_key + str(i)]) for i in indices])
    densities = np.array([float(value[density_key + str(i)]) for i in indices])
    gradients = np.array([float(value[gradient_key + str(i)]) for i in indices])
    if not np.all(np.isfinite(charges)) or not np.all(np.isfinite(densities)) or not np.all(np.isfinite(gradients)):
        raise ValueError('局部输入包含非有限的密度、电荷或密度梯度。')
    electrons, ions = np.flatnonzero(charges < 0), np.flatnonzero(charges > 0)
    if len(electrons) != 1 or len(ions) + 1 != count or np.any(densities < 0):
        raise ValueError('局部输入的粒子组成或密度无效。')
    electron = int(electrons[0])
    if not math.isclose(charges[electron], -1.0, rel_tol=0, abs_tol=1e-12) or densities[electron] <= 0:
        raise ValueError('局部输入的电子电荷必须为 -1，电子密度必须为正数。')
    return density_key, gradient_key, charges, densities, gradients, electron, ions


def _raw_local_curvatures(value, gradients, rhostar):
    """Undo expro_locsim's effective-curvature terms, using its native rhos/a."""
    if rhostar is None or not math.isfinite(float(rhostar)) or float(rhostar) <= 0:
        raise ValueError('CGYRO 准中性曲率校正缺少原生 rhos/a，请重新运行 Transfer_tool。')
    count = len(gradients)
    gt = np.array([float(value['DLNTDR_' + str(i)]) for i in range(1, count + 1)])
    sn = np.array([float(value['SDLNNDR_' + str(i)]) for i in range(1, count + 1)])
    if not np.all(np.isfinite(gt)) or not np.all(np.isfinite(sn)):
        raise ValueError('CGYRO 局部输入包含非有限的温度梯度或密度曲率。')
    raw = sn - (1.5 * gt**2 + gradients**2 - gradients * gt) * float(rhostar)
    if not np.all(np.isfinite(raw)):
        raise ValueError('CGYRO 密度曲率换算溢出。')
    return raw, gt


def _moment_residual(charges, densities, moment, electron, ions):
    ne = -charges[electron] * densities[electron]
    ion_moment = charges[ions] * densities[ions] * moment[ions]
    target = ne * moment[electron]
    scale = max(ne, abs(target) + float(np.sum(np.abs(ion_moment))))
    return abs(float(np.sum(ion_moment)) - target) / scale


def _sync_local_pressure(value, kind, densities, gradients, electron, rhostar):
    """Refresh native pressure derivatives after the particle fields change."""
    pressure_key = 'SBETA' if kind == 'cgyro' else 'P_PRIME_LOC'
    if pressure_key not in value:
        return
    tkey, gtkey = ('TEMP_', 'DLNTDR_') if kind == 'cgyro' else ('TAUS_', 'RLTS_')
    temperatures = np.array([float(value[tkey + str(i)]) for i in range(1, len(densities) + 1)])
    gt = np.array([float(value[gtkey + str(i)]) for i in range(1, len(densities) + 1)])
    beta = float(value['BETAE_UNIT' if kind == 'cgyro' else 'BETAE'])
    if (not np.all(np.isfinite(temperatures)) or np.any(temperatures <= 0)
            or not np.all(np.isfinite(gt)) or not math.isfinite(beta) or beta < 0):
        raise ValueError('局部温度、温度梯度或电子比压无效，无法同步压力导数。')
    pressure_weights = densities * temperatures
    normalization = densities[electron] * temperatures[electron]
    if kind == 'cgyro':
        sn, _ = _raw_local_curvatures(value, gradients, rhostar)
        st = np.array([float(value['SDLNTDR_' + str(i)]) for i in range(1, len(densities) + 1)]) - gt**2 * float(rhostar)
        moment = sn + st - 2 * gradients * gt * float(rhostar)
        result = beta * float(np.dot(pressure_weights, moment)) / normalization
    else:
        q, radius = float(value['Q_LOC']), float(value['RMIN_LOC'])
        if not math.isfinite(q) or not math.isfinite(radius) or radius <= 0:
            raise ValueError('TGLF 局部 q 或小半径无效，无法同步压力梯度。')
        beta_star = beta * float(np.dot(pressure_weights, gradients + gt)) / normalization
        result = -abs(q) / radius * beta_star / (8 * math.pi)
    if not math.isfinite(result):
        raise ValueError('准中性校正后的压力导数溢出。')
    value[pressure_key] = result


def validate_local_neutrality(value, kind, rhostar=None):
    """Independently check the final solver fields; Zeff is not a charge species."""
    _, _, charges, densities, gradients, electron, ions = _local_arrays(value, kind)
    ne = -charges[electron] * densities[electron]
    density_error = abs(float(np.dot(charges, densities))) / ne
    gradient_error = _moment_residual(charges, densities, gradients, electron, ions)
    record = dict(rule=NEUTRALITY_RULE, density_residual=density_error, gradient_residual=gradient_error)
    if kind == 'cgyro':
        if np.any(densities <= 0):
            raise ValueError('CGYRO 要求每种保留粒子的密度为正数；此半径存在零密度，请调整半径或粒子方案。')
        raw, _ = _raw_local_curvatures(value, gradients, rhostar)
        record['curvature_residual'] = _moment_residual(charges, densities, raw, electron, ions)
    if any(not math.isfinite(error) or error > TOLERANCE for key, error in record.items() if key.endswith('_residual')):
        raise ValueError('最终 {} 输入未通过密度、密度梯度或密度曲率准中性检查；已停止生成。'.format(kind.upper()))
    return record


def close_local_input(value, kind, main_count, expected_ions, rhostar=None):
    """Close density, its first derivative, and native CGYRO second derivative.

    Electron quantities and non-main species remain fixed. A common multiplier
    for all mains preserves their density ratios and derivative differences.
    """
    density_key, gradient_key, charges, densities, gradients, electron, ions = _local_arrays(value, kind)
    if int(main_count) != main_count or not 1 <= main_count <= len(ions):
        raise ValueError('缺少有效的主离子识别记录，请重新运行 Transfer_tool。')
    main_count = int(main_count)
    if len(expected_ions) != len(ions) or any(
            not math.isclose(charges[ions[index]], ion['charge'], rel_tol=1e-10, abs_tol=1e-12)
            for index, ion in enumerate(expected_ions)):
        raise ValueError('局部输入的离子组成与本轮粒子记录不一致，已停止发布。')
    electron_charge = -charges[electron] * densities[electron]
    before_density = abs(float(np.dot(charges, densities))) / electron_charge
    before_gradient = _moment_residual(charges, densities, gradients, electron, ions)
    raw, gt = _raw_local_curvatures(value, gradients, rhostar) if kind == 'cgyro' else (None, None)
    ne = np.array([electron_charge])
    ni, density_error = _close_densities(charges[ions], densities[ions, None], ne, main_count)
    gi, gradient_error = _close_gradients(charges[ions], ni, gradients[ions, None], ne,
                                         np.array([gradients[electron]]), main_count)
    record = dict(rule=NEUTRALITY_RULE, main_count=main_count,
                  density_residual_before=before_density, gradient_residual_before=before_gradient,
                  density_residual=density_error, gradient_residual=gradient_error)
    if raw is not None:
        record['curvature_residual_before'] = _moment_residual(charges, densities, raw, electron, ions)
        corrected = raw[ions].copy()
        # n_new = alpha*n_old: -a*rhos*n_new''/n_new contains the common
        # -a*rhos*alpha''/alpha and the species-dependent cross derivative.
        delta = gi[:main_count, 0] - gradients[ions[:main_count]]
        corrected[:main_count] -= 2 * float(rhostar) * gradients[ions[:main_count]] * delta
        weighted = charges[ions] * ni[:, 0]
        main_charge = float(np.sum(weighted[:main_count]))
        target = electron_charge * raw[electron] - float(np.dot(weighted, corrected))
        scale = max(electron_charge, abs(electron_charge * raw[electron]) + float(np.sum(np.abs(weighted * corrected))))
        if main_charge <= 0:
            if abs(target) > TOLERANCE * scale:
                raise ValueError('主离子总密度为零处无法满足密度曲率准中性。')
        else:
            corrected[:main_count] += target / main_charge
        curvature_error = abs(float(np.dot(weighted, corrected)) - electron_charge * raw[electron]) / scale
        if not np.all(np.isfinite(corrected)) or not math.isfinite(curvature_error) or curvature_error > TOLERANCE:
            raise ValueError('密度曲率未通过准中性校正。')
        record['curvature_residual'] = curvature_error
        for index in range(main_count):
            position = int(ions[index])
            gn, gti = gi[index, 0], gt[position]
            effective = corrected[index] + (1.5 * gti**2 + gn**2 - gn * gti) * float(rhostar)
            if not math.isfinite(effective):
                raise ValueError('CGYRO 校正后的有效密度曲率溢出。')
            value['SDLNNDR_' + str(position + 1)] = float(effective)
    for index in range(main_count):
        position = int(ions[index])
        densities[position] = ni[index, 0]
        gradients[position] = gi[index, 0]
        value[density_key + str(position + 1)] = float(ni[index, 0])
        value[gradient_key + str(position + 1)] = float(gi[index, 0])
    _sync_local_pressure(value, kind, densities, gradients, electron, rhostar)
    zeff_key = 'Z_EFF' if kind == 'cgyro' else 'ZEFF'
    if zeff_key in value:
        value[zeff_key] = float(np.dot(charges[ions] ** 2, densities[ions]) / electron_charge)
    return record
