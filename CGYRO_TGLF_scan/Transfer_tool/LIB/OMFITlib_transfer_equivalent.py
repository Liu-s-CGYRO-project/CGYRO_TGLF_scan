"""Replace non-main ions by an auxiliary species with an explicit thermal model.

Native input.gacode cannot store a radially varying species charge or mass.
Work on the generated local cards, after locpargen's integer-charge writer.
Each card retains its own density, temperature, mass and gradient units.
"""
from builtins import abs, any, dict, enumerate, float, int, len, list, max, range, str, zip
import math
import numpy as np
from OMFITlib_transfer_particles import (EQUIVALENT_RULE, EQUIVALENT_TEMPERATURES, TOLERANCE,
                                        close_local_input, is_thermal_hydrogen)


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


def equivalent_local_input(value, kind, main_count, expected_ions, rhostar=None, temperature_mode='pressure'):
    """Mutate a newly generated card, returning per-radius auditable provenance."""
    if kind not in SCHEMAS:
        raise ValueError('不支持的局部输入类型。')
    if temperature_mode not in EQUIVALENT_TEMPERATURES.values():
        raise ValueError('请选择有效的等效辅助物种温度方案。')
    if any(not is_thermal_hydrogen(ion) for ion in expected_ions[:main_count]):
        raise ValueError('等效方案的主离子必须为热 H/D/T，请重新生成输入。')
    # First enforce native-interpolation closure; preserve these main populations.
    closure = close_local_input(value, kind, main_count, expected_ions, rhostar)
    count_key, fields = SCHEMAS[kind]
    count = int(value[count_key])
    rows = [{name: float(value[prefix + str(index)]) for name, prefix in fields.items()}
            for index in range(1, count + 1)]
    if any(not math.isfinite(number) for row in rows for number in row.values()):
        raise ValueError('局部粒子参数包含非有限数值。')
    if any(row['mass'] <= 0 or row['t'] <= 0 for row in rows):
        raise ValueError('局部粒子质量和温度必须为正数。')
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
    charge, charge2 = before['charge'], before['zeff_numerator']
    effective = None
    if charge > 0:
        # Cauchy-Schwarz gives n_eq <= sum(n_i); ion number is not conserved.
        z = charge2 / charge
        n = charge / z
        mass = before['mass'] / n
        t = before['pressure'] / n
        gn = before['charge_gradient'] / charge
        gt = before['pressure_gradient'] / before['pressure'] - gn
        if reference is not None:
            t, gt = reference['t'], reference['gt']
        effective = dict(z=z, n=n, mass=mass, t=t, gn=gn, gt=gt)
        weights_q = np.array([row['n'] * row['z'] for row in impurities]) / charge
        weights_p = np.array([row['n'] * row['t'] for row in impurities]) / before['pressure']
        weights_m = np.array([row['n'] * row['mass'] for row in impurities]) / before['mass']
        if kind == 'cgyro':
            if reference is None:
                effective.update(_curvatures(impurities, weights_q, weights_p, gn, gt, rhostar))
            else:
                # Preserve auxiliary charge n''; its T'' now follows thermal
                # fuel. Copying the old effective sn would break charge closure
                # because sn contains gT-dependent corrections.
                raw_sn, _ = _raw_curvatures(impurities, rhostar)
                effective['sn'] = float(np.dot(weights_q, raw_sn)) + (1.5 * gt**2 + gn**2 - gn * gt) * rhostar
                effective['st'] = reference['st']
        else:
            # Native locpargen uses a common rotation; the mass weighting also
            # preserves the momentum moment if the populations differ.
            effective['v'] = float(np.dot(weights_m, [row['v'] for row in impurities]))
            effective['dv'] = float(np.dot(weights_m, [row['dv'] for row in impurities]))
        if any(not math.isfinite(number) for number in effective.values()):
            raise ValueError('等效杂质参数溢出，已停止生成。')
    else:
        record['note'] = '此半径的非主离子密度全部为零，不新增空杂质。'
    new_ions = mains + ([effective] if effective is not None else [])
    new_rows = new_ions + [electron] if kind == 'cgyro' else [electron] + new_ions
    # Delete only known species fields; geometry parameters must never be moved.
    for prefix in fields.values():
        for index in range(1, count + 1):
            del value[prefix + str(index)]
    value[count_key] = len(new_rows)
    for index, row in enumerate(new_rows, 1):
        for name, prefix in fields.items():
            value[prefix + str(index)] = float(row[name])
    closure = close_local_input(value, kind, main_count, [dict(charge=row['z']) for row in new_ions], rhostar)
    # Inspect final fields after closure and pressure-derivative synchronization.
    final_rows = [{name: float(value[prefix + str(index)]) for name, prefix in fields.items()}
                  for index in range(1, int(value[count_key]) + 1)]
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
