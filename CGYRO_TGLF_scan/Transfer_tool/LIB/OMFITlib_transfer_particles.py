"""Species presets for OMFITinputgacode; densities in 1e19/m3, temperatures in keV.

Work on a duplicate. Electron density is fixed; automatically identified main
ions jointly close charge density and its derivative, retaining their ratios.
No slowing-down distribution is fitted.
"""
from builtins import abs, any, dict, enumerate, float, int, len, list, max, next, range, round, sorted, str, sum
from collections import OrderedDict
import math
import numpy as np

PRESETS = OrderedDict([
    ('保留所有粒子', 'all'),
    ('慢化快离子（热化处理）', 'thermalize'),
    ('仅保留主离子和等效杂质', 'equivalent'),
    ('仅保留主离子', 'main_only'),
])
DESCRIPTIONS = {
    'all': '保留全部离子及热 / 快类型，所有主离子按原密度比例共同校正准中性。',
    'thermalize': '同种热杂质合并；对应任一主离子的快离子独立保留，温度、环向及极向流速采用所选热杂质的值。缺少所需热离子时停止。此为热化近似，压力会改变。',
    'equivalent': '全部非主离子合成一种等效杂质，各半径分别计算 Z、密度和 MASS；保持总电荷、Zeff 贡献、总质量及压力。主离子全部保留，密度和密度梯度均满足准中性。',
    'main_only': '保留电子和全部主离子；各半径按原主离子密度比例补齐电荷，分别沿用各主离子的温度和流速。',
}
PARTICLE_DEFAULTS = {'particle_mode': 'all', 'thermal_reference_ion': 0}
MAIN_ION_THRESHOLD = 0.30
MAIN_ION_RULE = 'mean_ni_over_ne_in_radial_interval_v1'
EQUIVALENT_RULE = 'all_nonmain_local_charge_zeff_mass_pressure_v1'
TOLERANCE = 1e-8
ROUND_OFF = 64 * np.finfo(float).eps


def particle_options(options):
    values = {key: options.get(key, default) for key, default in PARTICLE_DEFAULTS.items()}
    if values['particle_mode'] not in DESCRIPTIONS:
        raise ValueError('请选择有效的粒子处理方案。')
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
    values.update(minimum=minimum, maximum=maximum, coordinate=coordinate,
                  main_ion_rule=MAIN_ION_RULE, main_ion_threshold=MAIN_ION_THRESHOLD)
    if values['particle_mode'] == 'equivalent':
        values['equivalent_rule'] = EQUIVALENT_RULE
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


def detect_main_ions(profile, options):
    """Classify original populations by the interval mean of ni/ne, before edits.

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
        raise ValueError('本轮半径范围内没有平均 ni/ne > 30% 的主离子（最高 {:.6g}%）；请检查剖面和半径范围。'.format(largest * 100))
    return sorted(candidates, key=lambda ion: (-ion['mean_fraction'], ion['index']))


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


def _close_density(profile, main_count):
    """Close against fixed ne, never invoke OMFIT's negative-density ne fallback."""
    ne = np.asarray(profile['ne'], dtype=float)
    ions = species(profile)
    charges = np.array([ion['charge'] for ion in ions])
    densities = np.array([profile['ni_' + str(ion['index'])] for ion in ions])
    densities, error = _close_densities(charges, densities, ne, main_count)
    for index in range(main_count):
        profile['ni_' + str(index + 1)] = densities[index]
    profile['z_eff'] = profile.calc_zeff()
    profile['ptot'] = profile.calc_ptot()
    return error


def _close_profile_gradient(profile, main_count):
    ne, ions = np.asarray(profile['ne'], dtype=float), species(profile)
    electron_gradient = _array(profile, 'dlnnedr', ne.shape)
    charges = np.array([ion['charge'] for ion in ions])
    densities = np.array([profile['ni_' + str(ion['index'])] for ion in ions])
    gradients = np.array([_array(profile, 'dlnnidr_' + str(ion['index']), ne.shape) for ion in ions])
    gradients, error = _close_gradients(charges, densities, gradients, ne, electron_gradient, main_count)
    for index in range(main_count):
        profile['dlnnidr_' + str(index + 1)] = gradients[index]
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


def prepare_particles(source, options):
    """Return (processed OMFITinputgacode, compact provenance), preserving source."""
    options = particle_options(options)
    profile = source.duplicate()
    ne_before = _validate_profile(profile).copy()
    before = species(profile)
    pressure_before = _pressure_nt(profile)
    mains = detect_main_ions(profile, options)
    main_indices = [ion['index'] for ion in mains]
    main_count = len(mains)
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
    if mode == 'equivalent' and zeff_error > TOLERANCE * max(1.0, float(np.max(reference_zeff))):
        raise ValueError('等效杂质处理未能保持 Zeff。')
    after = species(profile)
    for index, ion in enumerate(after):
        ion['is_main'] = index < main_count
        if ion['is_main']:
            ion.update(source_index=mains[index]['index'], mean_fraction=mains[index]['mean_fraction'])
        elif mode == 'equivalent':
            ion['source_index'] = [original['index'] for original in before
                                   if original['index'] not in main_indices][index - main_count]
    for item in changes['kept_separate']:
        after[item['index'] - 1]['thermalized_fast'] = True
    report = dict(options=options, before=before, after=after, main_ions=mains, main_count=main_count,
                  equivalent_stage='local_inputs' if mode == 'equivalent' else None,
                  thermal_reference=thermal_reference['species'] if thermal_reference is not None else None,
                  density_residual=density_error, gradient_residual=gradient_error,
                  main_ratio_residual=ratio_error,
                  max_zeff_change=zeff_error,
                  max_relative_pressure_change=float(np.max(np.abs(_pressure_nt(profile) / pressure_before - 1.0))))
    report.update(changes)
    return profile, report


def close_local_input(value, kind, main_count, expected_ions):
    """Close both density and logarithmic gradients after radial interpolation.

    For CGYRO use DENS, Z, DLNNDR; for TGLF use AS, ZS, RLNS.
    All gradients share the same radial normalization within each local input.
    """
    if kind == 'cgyro':
        count_key, density_key, charge_key, gradient_key = 'N_SPECIES', 'DENS_', 'Z_', 'DLNNDR_'
    elif kind == 'tglf':
        count_key, density_key, charge_key, gradient_key = 'NS', 'AS_', 'ZS_', 'RLNS_'
    else:
        raise ValueError('不支持的局部输入类型。')
    count = int(value[count_key])
    if count < 2 or count != value[count_key]:
        raise ValueError('局部输入需要电子和至少一种离子。')
    indices = list(range(1, count + 1))
    charges = np.array([float(value[charge_key + str(i)]) for i in indices])
    densities = np.array([float(value[density_key + str(i)]) for i in indices])
    gradients = np.array([float(value[gradient_key + str(i)]) for i in indices])
    if not np.all(np.isfinite(charges)) or not np.all(np.isfinite(densities)) or not np.all(np.isfinite(gradients)):
        raise ValueError('局部输入包含非有限的密度、电荷或密度梯度。')
    electrons, ions = np.flatnonzero(charges < 0), np.flatnonzero(charges > 0)
    if len(electrons) != 1 or len(ions) + 1 != count or np.any(densities < 0):
        raise ValueError('局部输入的粒子组成或密度无效。')
    if int(main_count) != main_count or not 1 <= main_count <= len(ions):
        raise ValueError('缺少有效的主离子识别记录，请重新运行 Transfer_tool。')
    main_count = int(main_count)
    if len(expected_ions) != len(ions) or any(
            not math.isclose(charges[ions[index]], ion['charge'], rel_tol=1e-10, abs_tol=1e-12)
            for index, ion in enumerate(expected_ions)):
        raise ValueError('局部输入的离子组成与本轮粒子记录不一致，已停止发布。')
    electron = int(electrons[0])
    electron_charge = -charges[electron] * densities[electron]
    if electron_charge <= 0:
        raise ValueError('局部输入的电子密度必须为正数。')
    ne = np.array([electron_charge])
    ni, density_error = _close_densities(charges[ions], densities[ions, None], ne, main_count)
    gi, gradient_error = _close_gradients(charges[ions], ni, gradients[ions, None], ne,
                                         np.array([gradients[electron]]), main_count)
    for index in range(main_count):
        position = int(ions[index])
        densities[position] = ni[index, 0]
        value[density_key + str(position + 1)] = float(ni[index, 0])
        value[gradient_key + str(position + 1)] = float(gi[index, 0])
    zeff_key = 'Z_EFF' if kind == 'cgyro' else 'ZEFF'
    if zeff_key in value:
        value[zeff_key] = float(np.dot(charges[ions] ** 2, densities[ions]) / electron_charge)
    return dict(main_count=main_count, density_residual=density_error, gradient_residual=gradient_error)
