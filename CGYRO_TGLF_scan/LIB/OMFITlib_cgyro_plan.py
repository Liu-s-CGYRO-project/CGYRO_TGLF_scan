"""CGYRO source selection, isotope preparation and scan preflight.

This layer describes work without submitting it. Selection helpers may migrate
WORKBENCH settings; transformations always return independent solver inputs.
ProjectActions owns installation of prepared inputs and all execution effects.
"""
from builtins import abs, any, bool, dict, enumerate, float, int, len, list, next, range, set, sorted, str, sum
from collections import OrderedDict
import copy
import math
from OMFITlib_project_inputs import read, text_value, input_digest, pending_inputs, validate_input
from OMFITlib_transfer_particles import particle_options
from OMFITlib_cgyro_parameters import (FIELDS as CGYRO_FIELDS, apply_parameters,
    initialize_parameters, scan_parameter_names, validated_overrides, validate_zeff)
from OMFITlib_cgyro_scan_values import ky_values, scan_axes as configured_scan_axes
from OMFITlib_cgyro_isotopes import isotope_input, remap_physics

CGYRO_PATH = ('CGYRO_scan',)
ISOTOPE_MASSES = OrderedDict([('H', 0.5), ('D', 1.0), ('T', 1.5)])
ION_CASES = OrderedDict([('BASE', '原始'), ('H', 'H'), ('D', 'D'), ('T', 'T')])


def sync_cgyro_ion_cases(settings, factory=dict):
    """Create the unified original/H/D/T case selector and migrate old settings."""
    cases = settings.get('cgyro_ion_cases', None)
    if not hasattr(cases, 'keys'):
        cases = factory()
        settings['cgyro_ion_cases'] = cases
    if not cases:
        legacy_mode = settings.get('cgyro_scan_mode', 'isotope')
        legacy = settings.get('cgyro_isotopes', {})
        cases['BASE'] = legacy_mode == 'radius'
        for isotope in ISOTOPE_MASSES:
            cases[isotope] = legacy_mode != 'radius' and bool(legacy.get(isotope, True))
    for key in ION_CASES:
        cases.setdefault(key, False)
    for key in list(cases.keys()):
        if key not in ION_CASES:
            cases.pop(key)
    return cases


def cgyro_ion_mode(settings):
    cases = sync_cgyro_ion_cases(settings)
    selected = [key for key in ION_CASES if cases.get(key, False)]
    return 'original' if selected == ['BASE'] else ('hdt' if selected == ['H', 'D', 'T'] else 'custom')


def cgyro_scan_axes(root, source=None):
    """Resolve axes against an input; relative ranges follow each input's values."""
    node = read(root, CGYRO_PATH)
    if node is None:
        raise ValueError('工程缺少 CGYRO_scan 模块。')
    setup, physics = node['SETTINGS']['SETUP'], node['SETTINGS']['PHYSICS']
    dimensions = int(setup.get('idimrun', 1))
    if source is None:
        settings = read(root, ('SETTINGS', 'WORKBENCH'), {})
        rows = sync_cgyro_choices(root, settings)
        selected = [row for row in rows if settings.get('cgyro_radii', {}).get(row['key'], False)]
        source = read(root, (selected or rows)[0]['path'], {}) if rows else {}
    return dimensions, configured_scan_axes(physics, dimensions, source), ky_values(physics)


def cgyro_plan_summary(root):
    """Count input cases and flat scan tasks without opening result objects."""
    settings = read(root, ('SETTINGS', 'WORKBENCH'), {})
    rows = sync_cgyro_choices(root, settings)
    selected = [row for row in rows if bool(settings.get('cgyro_radii', {}).get(row['key'], False))]
    ion_cases = sum(1 for key in ION_CASES
                    if bool(sync_cgyro_ion_cases(settings).get(key, False)))
    dimensions, axes, ky = cgyro_scan_axes(root)
    points_per_case = len(ky)
    for axis in axes:
        points_per_case *= len(axis['values'])
    cases = len(selected) * ion_cases
    return dict(dimensions=dimensions, axes=axes, ky=len(ky), cases=cases,
                points_per_case=points_per_case, total_points=cases * points_per_case)


def _cgyro_case_id(row, ion_case):
    rho = 'unknown' if row.get('rho', None) is None else '{:.8g}'.format(float(row['rho']))
    return 'nr={}__rho={}__ion={}'.format(row['nr'], rho, ion_case)


def _cgyro_radius_number(name, fallback):
    try:
        value = int(str(name).rsplit('_', 1)[1])
        return value if value > 0 else fallback
    except (IndexError, TypeError, ValueError):
        return fallback


def cgyro_sources(root):
    """Return the complete radial CGYRO input set, in Transfer_tool order."""
    settings = read(root, ('SETTINGS', 'WORKBENCH'), {})
    mode = settings.get('cgyro_source_mode', 'generated')
    generated = read(root, ('Transfer_tool', 'OUTPUTS', 'Profiles_gen'), {})
    imported = read(root, ('Transfer_tool', 'Transfer_file'), {})
    branch, prefix = ({}, ())
    if mode == 'current':
        branch, prefix = read(root, CGYRO_PATH + ('INPUTS',), {}), CGYRO_PATH + ('INPUTS',)
    elif mode == 'imported' and 'input.cgyro' in imported:
        branch, prefix = imported, ('Transfer_tool', 'Transfer_file')
    elif mode == 'imported':
        return []
    elif any(str(key).startswith('input.cgyro_') for key in generated.keys()):
        branch, prefix = generated, ('Transfer_tool', 'OUTPUTS', 'Profiles_gen')
    elif 'input.cgyro' in imported:
        branch, prefix = imported, ('Transfer_tool', 'Transfer_file')
    else:
        inputs = read(root, ('Transfer_tool', 'INPUTS'), {})
        if 'input.cgyro' in inputs:
            branch, prefix = inputs, ('Transfer_tool', 'INPUTS')
    rows = []
    keys = [key for key in branch.keys()
            if str(key) == 'input.cgyro' or str(key).startswith('input.cgyro_')]
    keys = sorted(keys, key=lambda key: (_cgyro_radius_number(key, 1), str(key)))
    for fallback, key in enumerate(keys, 1):
        value = branch[key]
        nr = _cgyro_radius_number(key, fallback)
        if mode == 'current' and str(key) == 'input.cgyro':
            stored = read(root, CGYRO_PATH + ('SETTINGS', 'PHYSICS'), {})
            try:
                nr = int(stored.get('nr', nr))
            except (TypeError, ValueError):
                pass
            if nr < 1:
                nr = fallback
        try:
            rho_value = (read(root, ('Transfer_tool', 'OUTPUTS', 'Particle_processing', 'local_inputs',
                                    str(key), 'rho'))
                         if prefix == ('Transfer_tool', 'OUTPUTS', 'Profiles_gen') else None)
            if rho_value is None:
                rho_value = value.get('rho', None)  # Read legacy metadata before sanitizing the run copy.
            if mode == 'current' and str(key) == 'input.cgyro' and rho_value is None:
                rho_value = stored.get('rho', None)
            rho = float(rho_value)
            if not math.isfinite(rho):
                rho = None
        except (AttributeError, TypeError, ValueError, OverflowError):
            rho = None
        rows.append(dict(key=str(key), nr=nr, rho=rho, path=prefix + (key,)))
    return rows


def sync_cgyro_choices(root, settings, factory=dict):
    sync_cgyro_ion_cases(settings, factory)
    radii = settings.setdefault('cgyro_radii', factory())
    rows = cgyro_sources(root)
    available = [row['key'] for row in rows]
    for key in available:
        radii.setdefault(key, True)
    for key in list(radii.keys()):
        if key not in available:
            radii.pop(key)
    return rows


def _generated_particle_record(root):
    physics = read(root, ('Transfer_tool', 'SETTINGS', 'PHYSICS'), {})
    previous = read(root, ('Transfer_tool', 'OUTPUTS', 'Particle_processing', 'options'))
    if previous is None:
        return None, None
    return particle_options(physics.get('generation', {})), previous


def _cgyro_main_indices(root, source, source_path):
    count = int(float(source['N_SPECIES']))
    if source_path[:3] == ('Transfer_tool', 'OUTPUTS', 'Profiles_gen'):
        main_count = read(root, ('Transfer_tool', 'OUTPUTS', 'Particle_processing', 'main_count'))
        try:
            main_count = int(main_count)
        except (TypeError, ValueError):
            raise ValueError('Transfer_tool 结果缺少主离子记录，请重新运行。')
        if main_count < 1 or main_count >= count:
            raise ValueError('Transfer_tool 主离子记录无效，请重新运行。')
        return list(range(1, main_count + 1))
    electron_density = 1.0
    for index in range(1, count + 1):
        if float(source.get('Z_' + str(index), 0.0)) < 0:
            electron_density = float(source.get('DENS_' + str(index), 1.0))
            break
    if electron_density <= 0:
        raise ValueError('input.cgyro 的电子密度必须为正数。')
    result = [index for index in range(1, count + 1)
              if float(source.get('Z_' + str(index), 0.0)) > 0 and
              float(source.get('DENS_' + str(index), 0.0)) / electron_density > 0.30]
    if not result:
        raise ValueError('input.cgyro 中没有密度占电子密度 30% 以上的主离子。')
    return result


def _cgyro_case_input(root, row, source, ion_case, physics, dimensions):
    """Use the same transformed card and settings for preflight and submission."""
    provenance = None
    case_physics = physics
    if ion_case in ISOTOPE_MASSES:
        local = read(root, ('Transfer_tool', 'OUTPUTS', 'Particle_processing', 'local_inputs', row['key']), {})
        scale = (local.get('rhostar', local.get('equivalent', {}).get('rhostar', None))
                 if row['path'][:3] == ('Transfer_tool', 'OUTPUTS', 'Profiles_gen') else None)
        scanned = scan_parameter_names(physics, dimensions)
        overrides = validated_overrides(physics, [source], scanned)
        global_values = [parameter['values'] for axis in configured_scan_axes(physics, dimensions, source)
                         for parameter in [axis] + axis.get('linked', []) if parameter['name'] == 'GLOBAL_FLAG']
        global_curvature = (any(number > 0 for number in global_values[0]) if global_values else
                            float(overrides.get('GLOBAL_FLAG', source.get('GLOBAL_FLAG', 0))) > 0)
        value, provenance = isotope_input(source, ISOTOPE_MASSES[ion_case],
            _cgyro_main_indices(root, source, row['path']), scale, global_curvature)
        case_physics = remap_physics(physics, dimensions, provenance['index_map'])
    else:
        value = source.duplicate() if hasattr(source, 'duplicate') else copy.deepcopy(source)
    if 'rho' in value:
        del value['rho']
    fixed = apply_parameters(value, case_physics, dimensions)
    return value, case_physics, provenance, fixed


def _original_ion_label(source, main_indices):
    labels = []
    known = ((0.5, 'H'), (1.0, 'D'), (1.5, 'T'))
    for index in main_indices:
        if abs(float(source.get('Z_' + str(index), 0.0)) - 1.0) > 1e-8:
            continue
        mass = float(source.get('MASS_' + str(index), 0.0))
        label = next((name for value, name in known if abs(mass - value) <= 0.08), None)
        label = label or 'M{:g}'.format(mass)
        if label not in labels:
            labels.append(label)
    return '+'.join(labels) if labels else 'BASE'


def cgyro_plan_issues(root):
    settings = read(root, ('SETTINGS', 'WORKBENCH'), {})
    runid = text_value(read(root, CGYRO_PATH + ('SETTINGS', 'EXPERIMENT'), {}), 'runid')
    if not runid:
        return ['请填写结果集名称']
    rows = sync_cgyro_choices(root, settings)
    if not rows:
        return ['请生成半径输入、导入文件或选择 CGYRO 当前输入']
    if not any(bool(settings['cgyro_radii'].get(row['key'], False)) for row in rows):
        return ['至少选择一个 nr']
    ion_cases = sync_cgyro_ion_cases(settings)
    if not any(bool(ion_cases.get(key, False)) for key in ION_CASES):
        return ['至少选择一个主离子方案']
    try:
        dimensions = int(read(root, CGYRO_PATH + ('SETTINGS', 'SETUP', 'idimrun'), 1))
        selected = [row for row in rows if settings['cgyro_radii'].get(row['key'], False)]
        # BATCH_INPUTS is keyed by nr, not filename. Aliases such as _1 and _01
        # must not silently replace one another while retaining two plan rows.
        radial_ids = [row['nr'] for row in selected]
        if len(set(radial_ids)) != len(radial_ids):
            raise ValueError('所选输入的 nr 编号重复，请保留一个输入或修改文件的半径编号。')
        sources = [read(root, row['path']) for row in selected]
        physics = read(root, CGYRO_PATH + ('SETTINGS', 'PHYSICS'))
        initialize_parameters(physics, sources[0])
        validated_overrides(physics, sources, scan_parameter_names(physics, dimensions))
        chosen, previous = _generated_particle_record(root)
        if rows[0]['path'][:3] == ('Transfer_tool', 'OUTPUTS', 'Profiles_gen'):
            if previous is None or input_digest(chosen) != input_digest(previous):
                raise ValueError('粒子方案或半径设置已变化，请重新运行 Transfer_tool。')
        for row in selected:
            source = read(root, row['path'])
            for ion_case in ION_CASES:
                if not ion_cases.get(ion_case, False):
                    continue
                effective, case_physics, _, fixed = _cgyro_case_input(root, row, source, ion_case, physics, dimensions)
                case_axes = configured_scan_axes(case_physics, dimensions, effective)
                scan_names = scan_parameter_names(case_physics, dimensions)
                for axis in case_axes:
                    for parameter in [axis] + axis.get('linked', []):
                        if parameter['name'] not in effective and parameter['name'] not in CGYRO_FIELDS:
                            raise ValueError('nr={} 的 {} 输入没有参数 {}。'.format(row['nr'], ion_case, parameter['name']))
                        effective[parameter['name']] = parameter['values'][0]
                validate_input(effective, 'cgyro')
                validate_zeff(effective, set(fixed) | scan_names,
                              prescribed=float(source.get('Z_EFF_METHOD', 2)) == 1)
        ky_values(physics)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        return [str(exc)]
    return []


def cgyro_input_issues(root):
    if pending_inputs(root, 'transfer'):
        return ['请先处理 Transfer tool 的 TGLF 输入覆盖选择']
    return cgyro_plan_issues(root)
