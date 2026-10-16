"""Construct single-main-ion H/D/T cards without modifying their sources.

Species fields and defaults follow GACODE cgyro_parse.py. Effective curvature
conventions follow expro_locsim.f90, not second logarithmic derivatives.
"""
from builtins import any, dict, enumerate, float, hasattr, int, len, list, range, set, sorted, str, zip
import copy
import math
import re
from OMFITlib_cgyro_parameters import parameter_value, scan_parameter_names

SPECIES_DEFAULTS = dict(Z=1.0, MASS=1.0, DENS=0.0, TEMP=1.0, DLNNDR=1.0,
                        DLNTDR=1.0, SDLNNDR=0.0, SDLNTDR=0.0,
                        DLNNDR_SCALE=1.0, DLNTDR_SCALE=1.0)
MERGE_RULE = 'hdt_single_main_charge_pressure_gradients_v1'


def species_parameter(name):
    match = re.fullmatch(r'([A-Z][A-Z0-9_]*)_([1-9][0-9]*)', name)
    return (match.group(1), int(match.group(2))) if match and match.group(1) in SPECIES_DEFAULTS else None


def _number(source, name, default):
    value = float(source.get(name, default))
    if not math.isfinite(value):
        raise ValueError(name + ' 必须为有限数值。')
    return value


def _curvatures(rows, wn, wp, gn, gt, rhostar):
    # expro: raw_sn=-a*rhos*n''/n; raw_st=-a*rhos*T''/T.
    # Undo effective-curvature corrections, conserve n'' and p'', then restore.
    raw_n = [row['SDLNNDR'] - (1.5 * row['DLNTDR']**2 + row['DLNNDR']**2
             - row['DLNNDR'] * row['DLNTDR']) * rhostar for row in rows]
    raw_t = [row['SDLNTDR'] - row['DLNTDR']**2 * rhostar for row in rows]
    sn = math.fsum(weight * value for weight, value in zip(wn, raw_n))
    sp = math.fsum(weight * (n + t - 2 * row['DLNNDR'] * row['DLNTDR'] * rhostar)
                   for weight, n, t, row in zip(wp, raw_n, raw_t, rows))
    st = sp - sn + 2 * gn * gt * rhostar
    return sn + (1.5 * gt**2 + gn**2 - gn * gt) * rhostar, st + gt**2 * rhostar


def isotope_input(source, mass, main_indices, rhostar=None, global_curvature=False):
    """Return (independent card, provenance); merge only identified Z=1 mains."""
    count = _number(source, 'N_SPECIES', 0)
    if count < 1 or int(count) != count:
        raise ValueError('N_SPECIES 必须为正整数。')
    count = int(count)
    selected = sorted(set(int(index) for index in main_indices))
    if any(index < 1 or index > count for index in selected):
        raise ValueError('主离子编号超出 N_SPECIES。')
    selected = [index for index in selected if math.isclose(
        _number(source, 'Z_' + str(index), 1.0), 1.0, rel_tol=0, abs_tol=1e-8)]
    if not selected:
        raise ValueError('主离子中没有 Z=1 粒子，不能建立 H/D/T 扫描。')
    if _number(source, 'PROFILE_MODEL', 1) != 1:
        raise ValueError('H/D/T 扫描需要局部输入（PROFILE_MODEL=1）；请先用 Transfer_tool 生成半径输入。')
    value = source.duplicate() if hasattr(source, 'duplicate') else copy.deepcopy(source)
    mapping = {str(index): index for index in range(1, count + 1)}
    record = dict(rule=MERGE_RULE, merged=len(selected) > 1, source_main_species=selected,
                  species_before=count, species_after=count, index_map=mapping, main_species=selected[0])
    if len(selected) == 1:
        value['MASS_' + str(selected[0])] = mass
        return value, record
    rows = [{field: _number(source, field + '_' + str(index), default)
             for field, default in SPECIES_DEFAULTS.items()} for index in selected]
    if any(row['DENS'] < 0 or row['TEMP'] <= 0 or row['MASS'] <= 0 for row in rows):
        raise ValueError('待合并主离子的密度必须非负，温度和质量必须为正数。')
    if any(row[field] != 1 for row in rows for field in ('DLNNDR_SCALE', 'DLNTDR_SCALE')):
        raise ValueError('合并主离子前，请将非 1 的密度 / 温度梯度倍率折算进源输入。')
    n = math.fsum(row['DENS'] for row in rows)
    p = math.fsum(row['DENS'] * row['TEMP'] for row in rows)
    if not math.isfinite(n) or not math.isfinite(p) or n <= 0 or p <= 0:
        raise ValueError('待合并主离子的总密度和总热压必须为有限正数。')
    wn = [row['DENS'] / n for row in rows]
    wp = [row['DENS'] * row['TEMP'] / p for row in rows]
    gn = math.fsum(weight * row['DLNNDR'] for weight, row in zip(wn, rows))
    gt = math.fsum(weight * (row['DLNNDR'] + row['DLNTDR']) for weight, row in zip(wp, rows)) - gn
    merged = dict(Z=1.0, MASS=mass, DENS=n, TEMP=p / n, DLNNDR=gn, DLNTDR=gt,
                  DLNNDR_SCALE=1.0, DLNTDR_SCALE=1.0)
    if rhostar is not None:
        rhostar = float(rhostar)
        if not math.isfinite(rhostar) or rhostar <= 0:
            raise ValueError('主离子合并所需的原生曲率归一化无效，请重新生成半径输入。')
        sn, st = _curvatures(rows, wn, wp, gn, gt, rhostar)
        curvature_rule = 'native_density_pressure_second_derivatives'
    else:
        if global_curvature:
            raise ValueError('全局 H/D/T 扫描缺少原生曲率归一化，请用新版 Transfer_tool 重新生成半径输入。')
        # N_GLOBAL=0 ignores these fields. Preserve a documented local fallback;
        # never silently use it for a global calculation.
        sn = math.fsum(weight * row['SDLNNDR'] for weight, row in zip(wn, rows))
        st = math.fsum(weight * row['SDLNTDR'] for weight, row in zip(wp, rows))
        curvature_rule = 'inactive_local_weighted_fields'
    merged.update(dict(SDLNNDR=sn, SDLNTDR=st))
    if any(not math.isfinite(number) for number in merged.values()):
        raise ValueError('主离子合并后的参数溢出。')
    # Snapshot before removal. Only native species keys move; SHAPE_COS* etc.
    # are geometry, and must not be mistaken for species-indexed parameters.
    remaining = [index for index in range(1, count + 1) if index not in selected[1:]]
    output = []
    for new_index, old_index in enumerate(remaining, 1):
        mapping[str(old_index)] = new_index
        output.append(merged if old_index == selected[0] else {
            field: _number(source, field + '_' + str(old_index), default)
            for field, default in SPECIES_DEFAULTS.items()})
    target = mapping[str(selected[0])]
    for old_index in selected:
        mapping[str(old_index)] = target
    for name in list(value.keys()):
        if species_parameter(str(name)):
            del value[name]
    value['N_SPECIES'] = len(output)
    for index, row in enumerate(output, 1):
        for field, number in row.items():
            value[field + '_' + str(index)] = number
    record.update(dict(species_after=len(output), main_species=target, parameters=dict(merged),
                       rhostar=rhostar, curvature_rule=curvature_rule))
    return value, record


def remap_physics(physics, dimensions, mapping):
    """Remap original species targets; reject incompatible merged controls."""
    def renamed(name):
        parsed = species_parameter(str(name))
        if parsed and str(parsed[1]) in mapping:
            return parsed[0] + '_' + str(mapping[str(parsed[1])])
        return name

    value = {key: physics[key] for key in physics.keys()}
    group_name = str(dimensions) + 'd'
    group = {key: physics[group_name][key] for key in physics.get(group_name, {}).keys()}
    targets = set()
    for key in list(group.keys()):
        if not re.fullmatch(r'Para(?:_[xyz])?(?:[2-9]|[1-9][0-9]+)?', str(key)):
            continue
        name = renamed(group[key])
        if name in targets:
            raise ValueError('H/D/T 合并后，多个扫描轴或联动参数都指向 {}，请只保留一项。'.format(name))
        group[key] = name
        targets.add(name)
    value[group_name] = group
    parameters, originals = {}, {}
    scanned = scan_parameter_names(physics, dimensions)
    for name, item in physics.get('fixed_parameters', {}).items():
        if not hasattr(item, 'keys'):
            raise ValueError('固定参数 {} 的配置无效。'.format(name))
        if species_parameter(str(name)) and (not item.get('enabled', False) or name in scanned):
            continue
        new_name = renamed(name)
        if new_name in parameters and parameter_value(new_name, item.get('value', None)) != parameter_value(
                new_name, parameters[new_name].get('value', None)):
            raise ValueError('H/D/T 合并后 {} 与 {} 指向同一主离子，固定数值不一致。'.format(originals[new_name], name))
        parameters[new_name] = {key: item[key] for key in item.keys()}
        originals[new_name] = name
    value['fixed_parameters'] = parameters
    return value
