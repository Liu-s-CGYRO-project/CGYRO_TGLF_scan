"""Species presets for OMFITinputgacode; densities in 1e19/m3, temperatures in keV.

Work on a duplicate. Electron density is fixed; the selected main ion closes
charge density and its radial derivative. No slowing-down distribution is fitted.
"""
from builtins import abs, any, dict, float, int, len, list, max, min, next, range, round, str, sum
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
    'all': '保留全部离子及热 / 快类型，调整主离子满足准中性。',
    'thermalize': '同种热杂质合并；对应主离子的快离子独立保留，温度、环向及极向流速采用所选热杂质的值。缺少所需热离子时停止。此为热化近似，压力会改变。',
    'equivalent': '保留电子、主离子和一种等效杂质；保持准中性及初次准中性校正后的 Zeff，杂质温度和流速采用主离子值。',
    'main_only': '保留电子和选定主离子；电子密度不变，主离子密度设为 ne / Z，沿用主离子温度和流速。',
}
PARTICLE_DEFAULTS = {'particle_mode': 'all', 'main_ion': 0, 'equivalent_ion': 0, 'thermal_reference_ion': 0}
TOLERANCE = 1e-8
ROUND_OFF = 64 * np.finfo(float).eps


def particle_options(options):
    values = {key: options.get(key, default) for key, default in PARTICLE_DEFAULTS.items()}
    if values['particle_mode'] not in DESCRIPTIONS:
        raise ValueError('请选择有效的粒子处理方案。')
    for key in ('main_ion', 'equivalent_ion', 'thermal_reference_ion'):
        raw = float(values[key])
        if not math.isfinite(raw) or raw < 0 or int(raw) != raw:
            raise ValueError('粒子选择无效，请重新选择主离子、等效杂质或温度 / 流速来源。')
        values[key] = int(raw)
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


def ion_choices(profile, impurity=False):
    result = OrderedDict([('自动（选取电荷最高的杂质）' if impurity else '自动（最低电荷的首个热离子）', 0)])
    if profile is not None:
        for ion in species(profile):
            if impurity or ion['kind'] == 'therm':
                result[species_label(ion)] = ion['index']
    return result


def thermal_reference_choices(profile, selected_main=0):
    result = OrderedDict([('自动（剖面中的首个热杂质）', 0)])
    if profile is not None:
        ions = species(profile)
        main = ions[_main_index(ions, selected_main) - 1]
        for ion in ions:
            if ion['kind'] == 'therm' and ion['charge'] > main['charge']:
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


def _main_index(ions, selected):
    candidates = [ion for ion in ions if ion['kind'] == 'therm']
    if selected:
        candidates = [ion for ion in candidates if ion['index'] == selected]
    if not candidates:
        raise ValueError('没有可用的主热离子，请检查剖面或重新选择。')
    return min(candidates, key=lambda ion: (ion['charge'], ion['index']))['index']


def _close_density(profile):
    """Close against fixed ne, never invoke OMFIT's negative-density ne fallback."""
    ne = np.asarray(profile['ne'], dtype=float)
    ions = species(profile)
    other_charge = sum((ion['charge'] * profile['ni_' + str(ion['index'])] for ion in ions[1:]), np.zeros_like(ne))
    main = (ne - other_charge) / ions[0]['charge']
    if not np.all(np.isfinite(main)) or np.any(main < -ROUND_OFF * ne / ions[0]['charge']):
        raise ValueError('保持电子密度时，准中性校正将产生负的主离子密度；请检查杂质 / 快离子密度或选择其他主离子。')
    main = np.maximum(main, 0.0)  # Only cancellation at floating-point roundoff.
    profile['ni_1'] = main
    profile['z_eff'] = profile.calc_zeff()
    profile['ptot'] = profile.calc_ptot()
    residual = (ions[0]['charge'] * main + other_charge - ne) / ne
    if np.max(np.abs(residual)) > TOLERANCE:
        raise ValueError('粒子密度未通过准中性校正。')
    return float(np.max(np.abs(residual)))


def _close_profile_gradient(profile):
    ne, ions = np.asarray(profile['ne'], dtype=float), species(profile)
    electron_gradient = _array(profile, 'dlnnedr', ne.shape)
    other = np.zeros_like(ne)
    scale = np.abs(ne * electron_gradient)
    for ion in ions[1:]:
        suffix = str(ion['index'])
        term = ion['charge'] * profile['ni_' + suffix] * _array(profile, 'dlnnidr_' + suffix, ne.shape)
        other += term
        scale += np.abs(term)
    target = ne * electron_gradient - other
    main_charge = ions[0]['charge'] * profile['ni_1']
    zero = main_charge == 0
    if np.any(zero & (np.abs(target) > TOLERANCE * np.maximum(scale, ne))):
        raise ValueError('主离子密度为零处无法满足密度梯度准中性。')
    gradient = np.divide(target, main_charge, out=np.zeros_like(ne), where=~zero)
    if not np.all(np.isfinite(gradient)):
        raise ValueError('主离子密度梯度不是有限数值。')
    profile['dlnnidr_1'] = gradient
    residual = (main_charge * gradient + other - ne * electron_gradient) / np.maximum(scale, ne)
    if np.max(np.abs(residual)) > TOLERANCE:
        raise ValueError('剖面密度梯度未通过准中性校正。')
    # Keep the total pressure gradient consistent with the corrected species.
    weighted = ne * profile['Te'] * (electron_gradient + _array(profile, 'dlntedr', ne.shape))
    for ion in ions:
        suffix = str(ion['index'])
        weighted += profile['ni_' + suffix] * profile['Ti_' + suffix] * (
            profile['dlnnidr_' + suffix] + _array(profile, 'dlntidr_' + suffix, ne.shape))
    profile['dlnptotdr'] = weighted / _pressure_nt(profile)
    return float(np.max(np.abs(residual)))


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


def _thermal_reference(profile, options, ions, main):
    """Snapshot the chosen thermal impurity before ion reordering/deletion."""
    if not any(ion['kind'] == 'fast' and _same_species(ion, main) for ion in ions):
        return None
    candidates = [ion for ion in ions if ion['kind'] == 'therm' and ion['charge'] > main['charge']]
    selected = options['thermal_reference_ion']
    if selected:
        candidates = [ion for ion in candidates if ion['index'] == selected]
    if not candidates:
        raise ValueError('对应主离子的快离子独立热化需要热杂质作为温度 / 流速来源；请选择电荷高于主离子的热杂质或补充该剖面。')
    reference = candidates[0]
    suffix = str(reference['index'])
    return dict(species=dict(reference), arrays={quantity: profile[quantity + suffix].copy()
                for quantity in ('Ti_', 'vtor_', 'vpol_')})


def _thermalize(profile, thermal_reference=None):
    changes = {'merged': [], 'kept_separate': []}
    # Recompute indices after each deletion; isotope identity is charge AND mass.
    while True:
        ions = species(profile)
        fast = next((ion for ion in ions if ion['kind'] == 'fast'), None)
        if fast is None:
            return changes
        targets = [ion for ion in ions if ion['kind'] == 'therm' and _same_species(ion, fast)]
        if not targets:
            raise ValueError('{} 无相同电荷和质量的热离子，无法自动热化合并；请先补充同种热离子。'.format(species_label(fast)))
        target = targets[0]
        if target['index'] == 1:
            # Keep main-isotope fast ions as separate thermalized populations.
            # Only Ti/vtor/vpol are copied, from the selected thermal impurity.
            if thermal_reference is None:
                raise ValueError('缺少热杂质的温度 / 流速参考，已停止独立热化。')
            changes['kept_separate'].append(dict(index=fast['index'], source=species_label(fast),
                reference=species_label(thermal_reference['species']), reference_kind='thermal_impurity'))
            for quantity in ('Ti_', 'vtor_', 'vpol_'):
                profile[quantity + str(fast['index'])] = thermal_reference['arrays'][quantity].copy()
            profile['IONS'][fast['index']][3] = 'therm'
        else:
            changes['merged'].append('{} → {}'.format(species_label(fast), species_label(target)))
            profile.del_ion(fast['index'], add_density_to_ion=target['index'], verbose=False)


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
    main_index = _main_index(before, options['main_ion'])
    main = before[main_index - 1]
    thermal_reference = (_thermal_reference(profile, options, before, main)
                         if options['particle_mode'] == 'thermalize' else None)
    representative = None
    if options['particle_mode'] == 'equivalent':
        candidates = [ion for ion in before if ion['charge'] > main['charge']]
        if options['equivalent_ion']:
            candidates = [ion for ion in candidates if ion['index'] == options['equivalent_ion']]
            if not candidates:
                raise ValueError('等效杂质的电荷必须高于主离子，请重新选择。')
        if candidates:
            representative = max(candidates, key=lambda ion: (ion['charge'], -ion['index']))
    profile.reorder_ions([main_index] + [ion['index'] for ion in before if ion['index'] != main_index], verbose=False)
    _close_density(profile)
    reference_zeff = np.array(profile.calc_zeff(), dtype=float, copy=True)
    changes = {'merged': [], 'kept_separate': []}
    mode = options['particle_mode']
    if mode == 'thermalize':
        changes = _thermalize(profile, thermal_reference)
    elif mode in ('main_only', 'equivalent'):
        for index in range(int(profile['N_ION']), 1, -1):
            profile.del_ion(index, add_density_to_ion=1, verbose=False)
        _close_density(profile)
        if mode == 'equivalent' and representative is not None:
            z_main, z_eq = main['charge'], representative['charge']
            if int(z_eq) != z_eq:
                raise ValueError('OMFIT add_ion 要求等效杂质为整数电荷，请选择其他杂质。')
            density = ne_before * (reference_zeff - z_main) / (z_eq * (z_eq - z_main))
            remaining = (ne_before - z_eq * density) / z_main
            if (not np.all(np.isfinite(density)) or np.any(density < -ROUND_OFF * ne_before / z_eq)
                    or np.any(remaining < -ROUND_OFF * ne_before / z_main)):
                raise ValueError('所选等效杂质无法同时保持 Zeff 和非负密度，请选择电荷更高的杂质。')
            density = np.minimum(np.maximum(density, 0.0), ne_before / z_eq)
            profile.add_ion(2, representative['name'], z_eq, representative['mass'], ni=density,
                            thermal=True, remove_density_from_ion=1, temperature_and_velocities_from_ion=1, verbose=False)
    if int(profile['N_ION']) > 9:
        raise ValueError('当前 Transfer_tool 的 TGYRO 接口最多支持 9 种离子，请选择粒子简化方案。')
    density_error = _close_density(profile)
    # Rebuild OMFIT/GACODE derived fields after deleting/reordering ion arrays.
    profile.consistent_derived()
    if not np.array_equal(np.asarray(profile['ne']), ne_before):
        raise ValueError('派生量更新改变了电子密度，已停止生成。')
    _validate_profile(profile)
    for item in changes['kept_separate']:
        for quantity in ('Ti_', 'vtor_', 'vpol_'):
            if not np.allclose(profile[quantity + str(item['index'])], thermal_reference['arrays'][quantity], rtol=1e-12, atol=0):
                raise ValueError('派生量更新未保留所选热杂质的温度 / 流速，已停止独立热化。')
    density_error = max(density_error, _close_density(profile))
    gradient_error = _close_profile_gradient(profile)
    zeff_error = float(np.max(np.abs(profile['z_eff'] - reference_zeff)))
    if mode == 'equivalent' and zeff_error > TOLERANCE * max(1.0, float(np.max(reference_zeff))):
        raise ValueError('等效杂质处理未能保持 Zeff。')
    after = species(profile)
    for item in changes['kept_separate']:
        after[item['index'] - 1]['thermalized_fast'] = True
    report = dict(options=options, before=before, after=after,
                  thermal_reference=thermal_reference['species'] if thermal_reference is not None else None,
                  density_residual=density_error, gradient_residual=gradient_error,
                  max_zeff_change=zeff_error,
                  max_relative_pressure_change=float(np.max(np.abs(_pressure_nt(profile) / pressure_before - 1.0))))
    report.update(changes)
    return profile, report


def close_local_input(value, kind):
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
    electron, main = int(electrons[0]), int(ions[0])
    electron_charge = -charges[electron] * densities[electron]
    if electron_charge <= 0:
        raise ValueError('局部输入的电子密度必须为正数。')
    other = [i for i in range(count) if i != main]
    densities[main] = -float(np.dot(charges[other], densities[other])) / charges[main]
    if not math.isfinite(float(densities[main])) or densities[main] < -ROUND_OFF * electron_charge / charges[main]:
        raise ValueError('局部准中性校正会产生负主离子密度，已停止发布本轮输入。')
    densities[main] = max(0.0, float(densities[main]))
    target = -float(np.dot(charges[other] * densities[other], gradients[other]))
    scale = max(electron_charge, float(np.sum(np.abs(charges * densities * gradients))))
    if densities[main] == 0:
        if abs(target) > TOLERANCE * scale:
            raise ValueError('局部主离子密度为零，无法满足密度梯度准中性。')
        gradients[main] = 0.0
    else:
        gradients[main] = target / (charges[main] * densities[main])
    density_error = abs(float(np.dot(charges, densities))) / electron_charge
    gradient_error = abs(float(np.dot(charges * densities, gradients))) / scale
    if not np.all(np.isfinite(gradients)) or density_error > TOLERANCE or gradient_error > TOLERANCE:
        raise ValueError('局部输入的密度或密度梯度准中性校正失败。')
    value[density_key + str(main + 1)] = float(densities[main])
    value[gradient_key + str(main + 1)] = float(gradients[main])
    zeff_key = 'Z_EFF' if kind == 'cgyro' else 'ZEFF'
    if zeff_key in value:
        value[zeff_key] = float(np.dot(charges[ions] ** 2, densities[ions]) / electron_charge)
    return dict(density_residual=density_error, gradient_residual=gradient_error)
