"""Merge local species groups while preserving their specified physical moments.

Native input.gacode cannot store a radially varying species charge or mass.
Work on the generated local cards, after locpargen's integer-charge writer.
Each card retains its own density, temperature, mass and gradient units.
"""
from builtins import abs, any, dict, enumerate, float, int, len, list, max, range, str, zip
import math
import numpy as np
from OMFITlib_transfer_particles import (EQUIVALENT_RULE, SEPARATE_FAST_RULE, EQUIVALENT_TEMPERATURES, TOLERANCE,
                                        JET_FUEL_RULE, close_local_input, is_thermal_hydrogen, jet_fuel_groups)


SCHEMAS = {
    'cgyro': ('N_SPECIES', dict(z='Z_', mass='MASS_', n='DENS_', t='TEMP_',
                              gn='DLNNDR_', gt='DLNTDR_', sn='SDLNNDR_', st='SDLNTDR_')),
    'tglf': ('NS', dict(z='ZS_', mass='MASS_', n='AS_', t='TAUS_',
                       gn='RLNS_', gt='RLTS_', v='VPAR_', dv='VPAR_SHEAR_')),
}


def locpargen_rhostar(path, cgyro):
    """Recover the native curvature scale from out.locpargen's banana width.

    Its sixth scalar is q*rhos/a*sqrt(Te/Ti1). TEMP_i in input.cgyro is Ti/Te.
    Use this native output instead of a second, potentially different profile
    interpolation or a guessed magnetic field/physical-constant convention.
    """
    with open(path, 'r') as stream:
        values = [float(token.replace('D', 'e').replace('d', 'e')) for token in stream.read().split()]
    if len(values) != 6 or not np.all(np.isfinite(values)) or values[0] == 0:
        raise ValueError('out.locpargen 的曲率归一化信息无效，无法构造等效杂质。')
    ion_temperature = float(cgyro['TEMP_1'])
    electron_temperature = float(cgyro['TEMP_' + str(int(cgyro['N_SPECIES']))])
    if not (math.isfinite(ion_temperature) and math.isfinite(electron_temperature)
            and ion_temperature > 0 and electron_temperature > 0):
        raise ValueError('局部温度无效，无法读取曲率归一化。')
    result = values[5] / values[0] * math.sqrt(ion_temperature / electron_temperature)
    if not math.isfinite(result) or result <= 0:
        raise ValueError('locpargen 的 rhos/a 必须为有限正数。')
    return result


def _raw_curvatures(rows, rhostar):
    """Undo CGYRO's effective gradient terms before summing physical moments."""
    if rhostar is None or not math.isfinite(rhostar) or rhostar <= 0:
        raise ValueError('等效杂质缺少原生 locpargen 的曲率归一化。')
    gn = np.array([row['gn'] for row in rows])
    gt = np.array([row['gt'] for row in rows])
    sn = np.array([row['sn'] for row in rows]) - (1.5 * gt**2 + gn**2 - gn * gt) * rhostar
    st = np.array([row['st'] for row in rows]) - gt**2 * rhostar
    return sn, st


def _curvatures(rows, charge_weights, pressure_weights, gn, gt, rhostar):
    """Preserve the local charge and pressure second derivatives.

    expro_util defines raw sn=-a*rhos*n''/n and st=-a*rhos*T''/T.
    expro_locsim adds gradient terms when writing CGYRO's effective curvatures.
    Undo those terms, sum the physical moments, then apply the same convention.
    Z and MASS of the pseudo-species are constant within each local calculation.
    """
    raw_sn, raw_st = _raw_curvatures(rows, rhostar)
    gni = np.array([row['gn'] for row in rows])
    gti = np.array([row['gt'] for row in rows])
    sn = float(np.dot(charge_weights, raw_sn))
    sp = float(np.dot(pressure_weights, raw_sn + raw_st - 2 * gni * gti * rhostar))
    st = sp - sn + 2 * gn * gt * rhostar
    return dict(sn=sn + (1.5 * gt**2 + gn**2 - gn * gt) * rhostar,
                st=st + gt**2 * rhostar)


def _moments(rows):
    n = np.array([row['n'] for row in rows])
    z = np.array([row['z'] for row in rows])
    mass = np.array([row['mass'] for row in rows])
    t = np.array([row['t'] for row in rows])
    gn = np.array([row['gn'] for row in rows])
    gt = np.array([row['gt'] for row in rows])
    result = dict(charge=float(np.dot(n, z)), zeff_numerator=float(np.dot(n, z**2)),
                mass=float(np.dot(n, mass)), pressure=float(np.dot(n, t)),
                charge_gradient=float(np.dot(n * z, gn)),
                pressure_gradient=float(np.dot(n * t, gn + gt)))
    if any(not math.isfinite(number) for number in result.values()):
        raise ValueError('局部粒子电荷、质量、压力或梯度矩溢出。')
    return result


def _main_temperature(mains, kind, rhostar):
    """Temperature of the merged thermal fuel, consistent with H/D/T scans.

    T_m = sum(n_i*T_i)/sum(n_i). Its logarithmic gradient is the total
    pressure gradient minus the total density gradient, not a mean of gT_i.
    The same product rule determines T_m'' when CGYRO curvatures are active.
    """
    n = np.array([row['n'] for row in mains])
    p = n * np.array([row['t'] for row in mains])
    density, pressure = float(np.sum(n)), float(np.sum(p))
    if not math.isfinite(density) or not math.isfinite(pressure) or density <= 0 or pressure <= 0:
        raise ValueError('热主离子总密度和热压力必须为有限正数。')
    wn, wp = n / density, p / pressure
    gn = float(np.dot(wn, [row['gn'] for row in mains]))
    gt = float(np.dot(wp, [row['gn'] + row['gt'] for row in mains])) - gn
    result = dict(n=density, t=pressure / density, gn=gn, gt=gt)
    if kind == 'cgyro':
        result.update(_curvatures(mains, wn, wp, gn, gt, rhostar))
    if any(not math.isfinite(number) for number in result.values()):
        raise ValueError('热主离子合并温度或导数溢出。')
    return result


def _local_rows(value, kind, fields=None):
    count_key, all_fields = SCHEMAS[kind]
    if fields is None:
        fields = all_fields
    rows = [{name: float(value[prefix + str(index)]) for name, prefix in fields.items()}
            for index in range(1, int(value[count_key]) + 1)]
    if any(not math.isfinite(number) for row in rows for number in row.values()):
        raise ValueError('局部粒子参数包含非有限数值。')
    if any(row['mass'] <= 0 or row['t'] <= 0 for row in rows):
        raise ValueError('局部粒子质量和温度必须为正数。')
    return rows


def _jet_ion_audit(ions, electron):
    moments = _moments(ions)
    return dict(charge_residual=moments['charge'] - electron['n'],
                zeff=moments['zeff_numerator'] / electron['n'],
                pressure=moments['pressure'], pressure_gradient=moments['pressure_gradient'])


def jet_fuel_local_input(card, source_ions):
    """Apply JET 96482 command box 14 to one uncorrected, native local CGYRO card."""
    if float(card.get('GLOBAL_FLAG', 0)) != 0:
        raise ValueError('JET 96482 方案只适用于 GLOBAL_FLAG=0 的局部 CGYRO 卡。')
    _, schema = SCHEMAS['cgyro']
    fields = {name: schema[name] for name in ('z', 'mass', 'n', 't', 'gn', 'gt')}
    rows = _local_rows(card, 'cgyro', fields)
    ions = [row for row in rows if row['z'] > 0]
    electrons = [row for row in rows if row['z'] == -1]
    if (len(electrons) != 1 or len(ions) != len(source_ions) or len(rows) != len(ions) + 1
            or electrons[0]['n'] <= 0 or any(row['n'] < 0 for row in ions)):
        raise ValueError('CGYRO 全物种卡须包含与源剖面一致的离子、唯一的电子和有效密度。')
    for row, ion in zip(ions, source_ions):
        # locpargen writes ions in input.gacode order and rounds MASS=A/2 to six significant digits.
        if (row['z'] != ion['charge']
                or not math.isclose(row['mass'], ion['mass'] / 2, rel_tol=5e-6)):
            raise ValueError('局部 CGYRO 卡与源剖面的离子顺序或身份不符：' + ion['name'])
    main_index, fuel_indices, impurity_indices = jet_fuel_groups(source_ions)
    fuel = [ions[i] for i in fuel_indices]
    impurities = [ions[i] for i in impurity_indices]
    density = math.fsum(row['n'] for row in fuel)
    s0 = math.fsum(row['n'] for row in impurities)
    if density <= 0 or s0 <= 0:
        raise ValueError('快氢并入方案需要正的燃料组总密度和热杂质组总密度。')
    main = dict(ions[main_index], n=density, gn=math.fsum(row['n'] * row['gn'] for row in fuel) / density)
    s1 = math.fsum(row['z'] * row['n'] for row in impurities)
    s2 = math.fsum(row['z']**2 * row['n'] for row in impurities)
    impurity = {key: math.fsum(row['n'] * row[key] for row in impurities) / s0 for key in ('t', 'gn', 'gt')}
    impurity['z'] = s2 / s1
    impurity['n'] = s1 / impurity['z']
    impurity['mass'] = math.fsum(row['z'] * row['n'] * row['mass'] for row in impurities) / s1
    electron = dict(electrons[0], z=-1.0, n=1.0, t=1.0)
    audit = dict(rule=JET_FUEL_RULE, before=_jet_ion_audit(ions, electrons[0]),
                 after=_jet_ion_audit([main, impurity], electron))
    species_fields = {prefix[:-1] for prefix in fields.values()} | {'DLNNDR_SCALE', 'DLNTDR_SCALE'}
    for key in list(card.keys()):
        prefix, _, suffix = key.rpartition('_')
        curvature = suffix.isdigit() and prefix in ('SDLNNDR', 'SDLNTDR')
        stale_slot = suffix.isdigit() and prefix in species_fields and int(suffix) > 3
        if key == 'SBETA' or curvature or stale_slot:
            del card[key]
    card['N_SPECIES'] = 3
    for index, row in enumerate((main, impurity, electron), 1):
        for field, prefix in fields.items():
            card[prefix + str(index)] = row[field]
    return dict(main_count=1, equivalent=audit)


def jet_fuel_audit_lines(local_records):
    lines = []
    for entry in local_records.values():
        record = entry.get('equivalent', {})
        if record.get('rule', '') == JET_FUEL_RULE:
            values = ['{} {:.9g} → {:.9g}'.format(label, record['before'][field], record['after'][field])
                      for field, label in (('charge_residual', 'ΣZn−ne'), ('zeff', 'Zeff'),
                                           ('pressure', 'ΣnT'), ('pressure_gradient', 'ΣnT(gn+gT)'))]
            lines.append('ρ={:g}  {}'.format(entry['rho'], '，'.join(values)))
    return lines


def _equivalent_species(rows, before, kind, rhostar, reference=None):
    """One local pseudo-species; optional thermal reference is a model change.

    Match C1=sum(n*Z) and C2=sum(n*Z**2), hence Z=C2/C1 and n=C1**2/C2.
    Mass density and pressure then fix MASS and TEMP. Z/MASS are local constants,
    so logarithmic gradients follow the charge and pressure moments rather than
    numerical differences between neighboring pseudo-species' parameters.
    """
    charge, charge2 = before['charge'], before['zeff_numerator']
    if charge <= 0:
        return None  # Empty groups must not add zero-density solver species.
    if charge2 <= 0 or before['mass'] <= 0 or before['pressure'] <= 0:
        raise ValueError('等效粒子的电荷二阶矩、质量密度和压力必须为正数。')
    z = charge2 / charge
    n = charge / z
    if not math.isfinite(z) or not math.isfinite(n) or n <= 0:
        raise ValueError('等效粒子的电荷或密度溢出。')
    mass = before['mass'] / n
    t = before['pressure'] / n
    gn = before['charge_gradient'] / charge
    gt = before['pressure_gradient'] / before['pressure'] - gn
    if reference is not None:
        t, gt = reference['t'], reference['gt']
    effective = dict(z=z, n=n, mass=mass, t=t, gn=gn, gt=gt)
    weights_q = np.array([row['n'] * row['z'] for row in rows]) / charge
    weights_p = np.array([row['n'] * row['t'] for row in rows]) / before['pressure']
    if kind == 'cgyro':
        if reference is None:
            effective.update(_curvatures(rows, weights_q, weights_p, gn, gt, rhostar))
        else:
            # Changing auxiliary gT also changes effective sn. Preserve raw
            # charge curvature before restoring CGYRO's gradient corrections.
            raw_sn, _ = _raw_curvatures(rows, rhostar)
            effective['sn'] = float(np.dot(weights_q, raw_sn)) + (1.5 * gt**2 + gn**2 - gn * gt) * rhostar
            effective['st'] = reference['st']
    else:
        weights_m = np.array([row['n'] * row['mass'] for row in rows]) / before['mass']
        effective['v'] = float(np.dot(weights_m, [row['v'] for row in rows]))
        effective['dv'] = float(np.dot(weights_m, [row['dv'] for row in rows]))
    if any(not math.isfinite(number) for number in effective.values()):
        raise ValueError('等效粒子参数溢出，已停止生成。')
    return effective


def _write_local_species(value, kind, new_ions, electron, main_count, rhostar):
    """Replace known species fields only, preserving geometry and solver options."""
    count_key, fields = SCHEMAS[kind]
    count = int(value[count_key])
    new_rows = new_ions + [electron] if kind == 'cgyro' else [electron] + new_ions
    for prefix in fields.values():
        for index in range(1, count + 1):
            del value[prefix + str(index)]
    value[count_key] = len(new_rows)
    for index, row in enumerate(new_rows, 1):
        for name, prefix in fields.items():
            value[prefix + str(index)] = float(row[name])
    closure = close_local_input(value, kind, main_count, [dict(charge=row['z']) for row in new_ions], rhostar)
    return closure, _local_rows(value, kind)


def equivalent_local_input(value, kind, main_count, expected_ions, rhostar=None, temperature_mode='pressure'):
    """Mutate a newly generated card, returning per-radius auditable provenance."""
    if kind not in SCHEMAS:
        raise ValueError('不支持的局部输入类型。')
    if temperature_mode not in EQUIVALENT_TEMPERATURES.values():
        raise ValueError('请选择有效的等效辅助物种温度方案。')
    if any(not is_thermal_hydrogen(ion) for ion in expected_ions[:main_count]):
        raise ValueError('等效方案的主离子必须为热 H/D/T，请重新生成输入。')
    # First enforce native-interpolation closure; preserve these main populations.
    close_local_input(value, kind, main_count, expected_ions, rhostar)
    rows = _local_rows(value, kind)
    ions = [row for row in rows if row['z'] > 0]
    electron = [row for row in rows if row['z'] < 0][0]
    mains, impurities = ions[:main_count], ions[main_count:]
    before = _moments(impurities)
    total_pressure_before = _moments(rows)['pressure']
    reference = _main_temperature(mains, kind, rhostar) if temperature_mode == 'main_ion' else None
    record = dict(rule=EQUIVALENT_RULE, sources=[dict(ion, local=dict(row))
                  for ion, row in zip(expected_ions[main_count:], impurities)],
                  before=before, parameters=None, stage='local_input',
                  temperature_mode=temperature_mode, thermal_main_reference=reference,
                  mass_units='deuterium_reference_mass', density_units='local_reference_density',
                  temperature_units='local_reference_temperature',
                  gradient_units='native_local_normalization', rhostar=rhostar)
    effective = _equivalent_species(impurities, before, kind, rhostar, reference)
    if effective is None:
        record['note'] = '此半径的非主离子密度全部为零，不新增空杂质。'
    new_ions = mains + ([effective] if effective is not None else [])
    # Inspect final fields after closure and pressure-derivative synchronization.
    closure, final_rows = _write_local_species(value, kind, new_ions, electron, main_count, rhostar)
    final_auxiliary = [row for row in final_rows if row['z'] > 0][main_count:]
    after = _moments(final_auxiliary)
    # Thermalizing the auxiliary group intentionally changes pressure. Do not
    # mistake that model choice for a failed conservation check or hide it.
    conserved = list(before) if reference is None else ['charge', 'zeff_numerator', 'mass', 'charge_gradient']
    residuals = {name: abs(after[name] - before[name]) / max(1.0, abs(before[name])) for name in conserved}
    if any(error > TOLERANCE for error in residuals.values()):
        raise ValueError('等效辅助物种未满足所选方案的守恒约束，已停止生成。')
    total_pressure_after = _moments(final_rows)['pressure']
    pressure_change = dict(before=total_pressure_before, after=total_pressure_after,
                           relative=total_pressure_after / total_pressure_before - 1.0)
    record.update(dict(after=after, residuals=residuals, conserved_moments=conserved,
                       parameters=dict(final_auxiliary[0]) if final_auxiliary else None,
                       total_pressure_change=pressure_change, output_ion_count=len(new_ions)))
    closure['equivalent'] = record
    return closure


def _group_moments(rows, kind, rhostar):
    """Audit group derivatives as physical moments, not effective curvatures."""
    result = _moments(rows)
    if kind == 'cgyro':
        sn, st = _raw_curvatures(rows, rhostar)
        gni, gti = np.array([row['gn'] for row in rows]), np.array([row['gt'] for row in rows])
        result['charge_curvature'] = float(np.dot([row['n'] * row['z'] for row in rows], sn))
        result['pressure_curvature'] = float(np.dot([row['n'] * row['t'] for row in rows],
                                                   sn + st - 2 * gni * gti * rhostar))
    else:
        weights = np.array([row['n'] * row['mass'] for row in rows])
        result['parallel_momentum'] = float(np.dot(weights, [row['v'] for row in rows]))
        result['mass_weighted_flow_shear'] = float(np.dot(weights, [row['dv'] for row in rows]))
    if any(not math.isfinite(number) for number in result.values()):
        raise ValueError('粒子分组的局部导数矩溢出。')
    return result


def _moment_change(before, after):
    """Record a signed change without inventing a percentage at a zero baseline."""
    delta = after - before
    if not math.isfinite(delta):
        raise ValueError('粒子处理前后的压力或压力梯度差值溢出。')
    relative = delta / abs(before) if before != 0 else None
    if relative is not None and not math.isfinite(relative):
        relative = None
    return dict(before=before, after=after, delta=delta, relative=relative,
                relative_definition='(after-before)/abs(before)')


def pressure_audit_lines(local_inputs):
    """Readable per-radius pressure audit shared by the console and GUI help.

    Prefer CGYRO records to avoid listing both solver normalizations twice.
    Old records without the gradient audit remain readable but cannot supply it.
    """
    records = [(name, item['equivalent']) for name, item in local_inputs.items()
               if item.get('equivalent', {}).get('total_pressure_gradient_change', None) is not None]
    cgyro = [(name, item) for name, item in records if str(name).startswith('input.cgyro_')]
    lines = []
    for name, record in cgyro or records:
        parts = []
        for key, label in (('total_pressure_change', 'P'), ('total_pressure_gradient_change', 'G')):
            change = record[key]
            relative = change['relative']
            percent = '{:+.3%}'.format(relative) if relative is not None else '比例未定义'
            parts.append('{} {:.6g} → {:.6g}，Δ={:+.6g}（{}）'.format(
                label, change['before'], change['after'], change['delta'], percent))
        lines.append(str(name) + '：' + '；'.join(parts))
    return lines


def separate_fast_local_input(value, kind, main_count, expected_ions, rhostar=None):
    """Generate electron + merged thermal fuel + impurity + fast populations.

    The source profile is already neutral. Repeat closure after locpargen's
    interpolation, then keep the three positive-charge groups disjoint. Native
    cards have no therm/fast flag: retain the group identity in provenance.
    Thermal impurities follow the merged fuel temperature and its derivatives;
    only that group's pressure may change. Fast pressure remains independent.
    """
    if kind not in SCHEMAS:
        raise ValueError('不支持的局部输入类型。')
    if any(not is_thermal_hydrogen(ion) for ion in expected_ions[:main_count]):
        raise ValueError('分组主离子必须为热 H/D/T，请重新生成输入。')
    if any(ion['kind'] not in ('therm', 'fast') for ion in expected_ions):
        raise ValueError('粒子分组缺少原始 therm / fast 类型。')
    source_closure = close_local_input(value, kind, main_count, expected_ions, rhostar)
    rows = _local_rows(value, kind)
    ions = [row for row in rows if row['z'] > 0]
    electron = [row for row in rows if row['z'] < 0][0]
    reference = _main_temperature(ions[:main_count], kind, rhostar)
    beta_key = 'BETAE_UNIT' if kind == 'cgyro' else 'BETAE'
    beta_before = value.get(beta_key, None)
    grouped = {'main': [], 'impurity': [], 'fast': []}
    for index, (ion, row) in enumerate(zip(expected_ions, ions)):
        group = 'main' if index < main_count else 'fast' if ion['kind'] == 'fast' else 'impurity'
        grouped[group].append(dict(ion, local=dict(row)))
    new_ions, groups = [], {}
    for group, sources in grouped.items():
        group_rows = [source['local'] for source in sources]
        before = _group_moments(group_rows, kind, rhostar)
        # Only the thermal impurity group changes thermal model. Its density
        # derivative still comes from its own charge moment, not the fuel's.
        effective = _equivalent_species(group_rows, before, kind, rhostar,
                                         reference=reference if group == 'impurity' else None)
        if group == 'main' and effective is None:
            raise ValueError('此半径的热主离子密度为零，无法生成合并主离子。')
        solver_index = None
        if effective is not None:
            new_ions.append(effective)
            solver_index = len(new_ions) + (0 if kind == 'cgyro' else 1)
        groups[group] = dict(sources=sources, before=before, solver_index=solver_index,
                             omitted=effective is None, parameters=None)
    # Exactly one main ion remains. This count belongs to this final card,
    # independently of the original profile's number of abundant D/T species.
    closure, final_rows = _write_local_species(value, kind, new_ions, electron, 1, rhostar)
    final_electron = final_rows[-1] if kind == 'cgyro' else final_rows[0]
    if final_electron != electron or value.get(beta_key, None) != beta_before:
        raise ValueError('粒子分组合并不应修改电子参数或电子比压，已停止生成。')
    for group, record in groups.items():
        index = record['solver_index']
        final = [final_rows[index - 1]] if index is not None else []
        after = _group_moments(final, kind, rhostar)
        before = record['before']
        # Thermal equilibrium intentionally changes impurity pressure. Preserve
        # its charge derivatives, but do not misreport its pressure as conserved.
        changed = ('pressure', 'pressure_gradient', 'pressure_curvature') if group == 'impurity' else ()
        conserved = [name for name in before if name not in changed]
        residuals = {name: abs(after[name] - before[name]) / max(1.0, abs(before[name])) for name in conserved}
        if any(error > TOLERANCE for error in residuals.values()):
            raise ValueError('粒子分组 {} 未满足该组的守恒约束，已停止生成。'.format(group))
        temperature_residuals = {}
        if final and group in ('main', 'impurity'):
            # Matching the same T profile also matches T'' in global CGYRO.
            fields = ('t', 'gt', 'st') if kind == 'cgyro' else ('t', 'gt')
            temperature_residuals = {name: abs(final[0][name] - reference[name]) / max(1.0, abs(reference[name]))
                                     for name in fields}
            if any(error > TOLERANCE for error in temperature_residuals.values()):
                raise ValueError('热杂质和主离子的温度及其导数未满足同温约定，已停止生成。')
        record.update(dict(after=after, residuals=residuals, conserved_moments=conserved,
                           temperature_residuals=temperature_residuals,
                           pressure_change=_moment_change(before['pressure'], after['pressure']),
                           pressure_gradient_change=_moment_change(before['pressure_gradient'], after['pressure_gradient']),
                           parameters=dict(final[0]) if final else None))
    before_total, after_total = _moments(rows), _moments(final_rows)
    pressure_change = _moment_change(before_total['pressure'], after_total['pressure'])
    gradient_change = _moment_change(before_total['pressure_gradient'], after_total['pressure_gradient'])
    # Every total-pressure change must be attributable to the impurity model,
    # rather than a hidden adjustment to main ions, fast pressure, or beta_e.
    budget_residuals = {}
    for name, change in (('pressure', pressure_change), ('pressure_gradient', gradient_change)):
        impurity = groups['impurity']
        expected = impurity['after'][name] - impurity['before'][name]
        budget_residuals[name] = abs(change['delta'] - expected) / max(1.0, abs(before_total[name]), abs(expected))
    if any(error > TOLERANCE for error in budget_residuals.values()):
        raise ValueError('总压力或梯度变化超出热杂质同温处理的差额，已停止生成。')
    closure['equivalent'] = dict(rule=SEPARATE_FAST_RULE, groups=groups, stage='local_input',
        source_main_count=main_count, output_main_count=1, output_ion_count=len(new_ions),
        source_neutrality=source_closure, rhostar=rhostar, temperature_mode='thermal_impurity_main_ion_fast_pressure',
        thermal_main_reference=reference, pressure_budget_residuals=budget_residuals,
        electron_beta=dict(parameter=beta_key, before=beta_before, after=value.get(beta_key, None)),
        mass_units='deuterium_reference_mass', density_units='local_reference_density',
        temperature_units='local_reference_temperature', gradient_units='native_local_normalization',
        pressure_definition='sum(n*T)', pressure_gradient_definition='sum(n*T*(gn+gt))',
        total_pressure_change=pressure_change, total_pressure_gradient_change=gradient_change)
    return closure
