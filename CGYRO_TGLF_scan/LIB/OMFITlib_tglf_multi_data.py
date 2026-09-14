"""Case records and validated inputs for multi-profile TGLF calculations."""
from builtins import all, any, bool, dict, enumerate, float, int, isinstance, len, list, max, min, range, set, sorted, str, tuple, zip
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import uuid

DEFAULTS = {
    'radii': '0.5', 'coordinate': 'rho', 'execution': 'local', 'environment': '',
    'tgyro_command': 'tgyro -t . -n {n_radii}', 'tglf_command': 'tglf -e .',
    'SAT_RULE': 0, 'NKY': 12, 'NMODES': 2, 'USE_BPER': False, 'USE_BPAR': False,
    'extra': '', 'continue_on_error': True, 'include_ions': 'all', 'status': '',
}
MODEL_KEYS = ('SAT_RULE', 'NKY', 'NMODES', 'USE_BPER', 'USE_BPAR')


def initialize(root, factory=dict):
    settings = root['SETTINGS'].setdefault('TGLF_MULTI', {})
    for key, value in DEFAULTS.items():
        settings.setdefault(key, copy.deepcopy(value))
    cases = root.setdefault('TGLF_CASES', factory())
    return settings, cases


def parse_radii(value):
    tokens = re.split(r'[,;\s]+', str(value).strip().strip('[]()'))
    try:
        radii = [float(token) for token in tokens if token]
    except ValueError as exc:
        raise ValueError('半径需要用逗号或空格分隔的数值，例如 0.3, 0.5, 0.7。') from exc
    if not radii or any(not math.isfinite(r) or not 0 < r < 1 for r in radii):
        raise ValueError('半径必须满足 0 < rho（或 r/a）< 1。')
    if len(radii) != len(set(radii)):
        raise ValueError('半径列表包含重复值。')
    return sorted(radii)


def parse_overrides(text):
    """Accept scalar GACODE assignments, never Python expressions."""
    result = {}
    for line in str(text).splitlines():
        for assignment in line.split('#', 1)[0].split(';'):
            if not assignment.strip():
                continue
            match = re.fullmatch(r'\s*([A-Z][A-Z0-9_]*)\s*=\s*(\S+)\s*', assignment)
            if not match:
                raise ValueError('参数格式应为 KEY=value；多项用分号或换行分隔。')
            key, raw = match.groups()
            if key in result:
                raise ValueError('参数重复：' + key)
            if key in ('USE_TRANSPORT_MODEL', 'NS', 'DIR'):
                raise ValueError(key + ' 由多输入工作流管理，不能在附加参数中覆盖。')
            if raw.lower() in ('.true.', 'true', '.false.', 'false'):
                value = raw.lower() in ('.true.', 'true')
            else:
                try:
                    value = float(re.sub('[dD]', 'e', raw))
                except ValueError as exc:
                    raise ValueError('参数必须为有限数值或布尔值：' + key) from exc
                if not math.isfinite(value):
                    raise ValueError('参数必须为有限数值：' + key)
                if re.fullmatch(r'[+-]?\d+', raw):
                    value = int(raw)
            result[key] = value
    return result


def profile_info(profile):
    import numpy as np
    required = ('rho', 'rmin', 'ne', 'Te', 'q', 'IONS')
    missing = [key for key in required if key not in profile]
    if missing:
        raise ValueError('input.gacode 缺少字段：' + ', '.join(missing))
    rho = np.asarray(profile['rho'], dtype=float)
    rmin = np.asarray(profile['rmin'], dtype=float)
    if rho.ndim != 1 or len(rho) < 3 or rmin.shape != rho.shape:
        raise ValueError('剖面的 rho / rmin 网格长度不匹配或少于 3 点。')
    if not np.all(np.isfinite(rho)) or not np.all(np.diff(rho) > 0):
        raise ValueError('剖面 rho 必须有限且严格递增。')
    if not np.all(np.isfinite(rmin)) or not np.all(np.diff(rmin) > 0) or rmin[-1] <= 0:
        raise ValueError('剖面 rmin 必须有限且严格递增，边界值必须为正。')
    ions = profile['IONS']
    if not ions or sorted(ions) != list(range(1, len(ions) + 1)) or len(ions) > 9:
        raise ValueError('IONS 需要从 1 连续编号；此工作流支持 1–9 个离子。')
    for key in ('ne', 'Te', 'q'):
        data = np.asarray(profile[key], dtype=float)
        if data.shape != rho.shape or not np.all(np.isfinite(data)):
            raise ValueError('剖面字段无效：' + key)
    if np.any(np.asarray(profile['ne']) <= 0) or np.any(np.asarray(profile['Te']) <= 0):
        raise ValueError('电子密度、温度必须为正。')
    for index, ion in ions.items():
        if len(ion) < 4 or not all(math.isfinite(float(v)) and float(v) > 0 for v in ion[1:3]):
            raise ValueError('IONS 电荷、质量或类型无效：' + str(index))
        for key in ('ni_' + str(index), 'Ti_' + str(index)):
            values = np.asarray(profile.get(key, []), dtype=float)
            if values.shape != rho.shape or not np.all(np.isfinite(values)) or np.any(values < 0):
                raise ValueError('离子剖面无效：' + key)
    return {'points': len(rho), 'ions': len(ions), 'rho_min': float(rho[0]),
            'rho_max': float(rho[-1]), 'ra_min': float(rmin[0] / rmin[-1])}


def profile_digest(profile):
    def encode(value):
        if hasattr(value, 'items'):
            return [(repr(key), encode(item)) for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))]
        if hasattr(value, 'tolist'):
            return encode(value.tolist())
        if isinstance(value, (list, tuple)):
            return [encode(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise ValueError('无法记录剖面字段类型：' + type(value).__name__)
    return hashlib.sha256(json.dumps(encode(profile), ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def import_files(root, paths, loader, factory=dict):
    settings, cases = initialize(root, factory)
    added, errors = [], []
    for filename in dict.fromkeys(str(p) for p in paths):
        path = Path(filename).expanduser().resolve()
        try:
            raw = path.read_bytes()
            if not raw:
                raise ValueError('文件为空')
            profile = loader(str(path), GACODEtype='gacode')
            info = profile_info(profile)  # Force lazy loading before taking the snapshot.
            case_id = 'case_' + uuid.uuid4().hex[:12]
            record = factory()
            label = path.parent.name if path.name == 'input.gacode' else path.name
            record.update(dict(label=label, enabled=True, source=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                          info=info, radii='', extra='', runs=factory(), selected_run=''))
            record['input.gacode'] = copy.deepcopy(profile)
            cases[case_id] = record
            added.append(case_id)
        except Exception as exc:
            errors.append(str(path) + ': ' + str(exc))
    settings['status'] = '已导入 {} 个案例。'.format(len(added)) + ('\n' + '\n'.join(errors) if errors else '')
    return added, errors


def duplicate_case(root, case_id, factory=dict):
    _, cases = initialize(root, factory)
    source = cases[case_id]
    duplicate = factory()
    duplicate.update({key: copy.deepcopy(value) for key, value in source.items()
                      if key not in ('runs', 'selected_run')})
    duplicate.update(dict(label=source['label'] + ' (copy)', enabled=True, runs=factory(), selected_run=''))
    key = 'case_' + uuid.uuid4().hex[:12]
    cases[key] = duplicate
    return key


def case_plan(settings, case):
    radii = parse_radii(case.get('radii', None) or settings['radii'])
    coordinate = settings['coordinate']
    if coordinate not in ('rho', 'r/a'):
        raise ValueError('未知半径坐标。')
    info = profile_info(case['input.gacode'])
    lower, upper = (info['rho_min'], info['rho_max']) if coordinate == 'rho' else (info['ra_min'], 1.)
    if radii[0] < lower or radii[-1] > upper:
        raise ValueError('选择的半径超出该 input.gacode 的范围。')
    parameters = {key: settings[key] for key in MODEL_KEYS}
    parameters.update(parse_overrides(settings['extra']))
    parameters.update(parse_overrides(case['extra']))
    for key in ('SAT_RULE', 'NKY', 'NMODES'):
        value = parameters[key]
        if isinstance(value, bool) or int(value) != value or value < (0 if key == 'SAT_RULE' else 1):
            raise ValueError(key + ' 必须是有效的整数。')
        parameters[key] = int(value)
    for key in ('USE_BPER', 'USE_BPAR'):
        if not isinstance(parameters[key], bool):
            raise ValueError(key + ' 必须为 true 或 false。')
    parameters['USE_TRANSPORT_MODEL'] = True
    if settings['include_ions'] not in ('all', 'thermal'):
        raise ValueError('未知离子选择。')
    return {'radii': radii, 'coordinate': coordinate, 'parameters': parameters, 'bounds': [lower, upper],
            'include_ions': settings['include_ions']}


def dump_grid(radii, bounds=(0., 1.)):
    """TGYRO setup uses at least two locations; the auxiliary point is not a requested run."""
    if len(radii) == 1:
        lower, upper = bounds
        radius = radii[0]
        auxiliary = (lower + radius) / 2. if radius > lower else (radius + upper) / 2.
        if auxiliary == radius or not 0 < auxiliary < 1:
            raise ValueError('剖面范围不足以生成辅助转换半径。')
        return sorted([auxiliary, radius])
    return list(radii)


def tgyro_input(profile, plan):
    grid = dump_grid(plan['radii'], plan['bounds'])
    settings = {
        'TGYRO_MODE': 1, 'TGYRO_RELAX_ITERATIONS': 0, 'TGYRO_ITERATION_METHOD': 1,
        'LOC_RESTART_FLAG': 0, 'LOC_LOCK_PROFILE_FLAG': 1, 'TGYRO_NEO_METHOD': 0,
        'TGYRO_PED_MODEL': 0, 'TGYRO_TGLF_DUMP_FLAG': 1, 'TGYRO_TGLF_REVISION': 0,
        'TGYRO_USE_RHO': int(plan['coordinate'] == 'rho'), 'TGYRO_RMIN': min(grid),
        'TGYRO_RMAX': max(grid), 'LOC_N_ION': len(profile['IONS']),
        'LOC_TE_FEEDBACK_FLAG': 1, 'LOC_TI_FEEDBACK_FLAG': 1, 'LOC_ER_FEEDBACK_FLAG': 0,
        'TGYRO_DEN_METHOD0': 1,
    }
    for index in range(1, 10):
        ion = profile['IONS'].get(index, None)
        thermal = ion is not None and 'fast' not in str(ion[3]).lower()
        settings['TGYRO_CALC_FLAG' + str(index)] = int(ion is not None and (plan['include_ions'] == 'all' or thermal))
        settings['TGYRO_THERM_FLAG' + str(index)] = int(thermal)
    if not any(settings['TGYRO_CALC_FLAG' + str(i)] for i in range(1, 10)):
        raise ValueError('所选离子规则没有留下参与计算的离子。')
    lines = ['DIR TGLF{} 1 X={:.12g}'.format(i + 1, radius) for i, radius in enumerate(grid)]
    lines.extend('{}={}'.format(key, value) for key, value in settings.items())
    return '\n'.join(lines) + '\n', grid


def tglf_text(parameters):
    return '\n'.join('{}={}'.format(key, '.true.' if value is True else '.false.' if value is False else value)
                     for key, value in parameters.items()) + '\n'
