"""Input validation and stable comparison shared by project actions and planning.

No task execution, filesystem writes or input replacement belongs here. Readers
accept native OMFIT mappings as well as dicts; caller-owned inputs stay intact.
"""
from builtins import any, bool, float, int, isinstance, list, set, sorted, str, tuple
import ast
import hashlib
import json
import math
from OMFITlib_cgyro_parameters import parameter_value


def read(node, path, default=None):
    try:
        for key in path:
            node = node[key]
        return node
    except (KeyError, TypeError, AttributeError):
        return default


def text_value(node, key):
    try:
        value = node.get(key, None)
        return '' if value is None else str(value).strip()
    except Exception:
        return ''  # An invalid OMFITexpression is reported as unresolved.


def location(path):
    return 'root' + ''.join('[{!r}]'.format(key) for key in path)


def input_digest(value):
    def plain(item):
        if hasattr(item, 'keys'):
            return {str(key): plain(item[key]) for key in item.keys()}
        if hasattr(item, 'tolist'):
            return plain(item.tolist())
        if isinstance(item, (list, tuple)):
            return [plain(part) for part in item]
        return item
    payload = json.dumps(plain(value), sort_keys=True, ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def transfer_parameter_value(code, name, raw, original):
    """Parse a scalar input value without evaluating expressions."""
    text = str(raw).strip()
    if hasattr(original, 'tolist'):
        original = original.tolist()
    if isinstance(original, bool):
        booleans = {'true': True, '.true.': True, '.t.': True, '1': True,
                    'false': False, '.false.': False, '.f.': False, '0': False}
        if text.lower() not in booleans:
            raise ValueError(name + ' 请填写 true / false 或 1 / 0。')
        return booleans[text.lower()]
    if isinstance(original, str):
        value = ast.literal_eval(text) if text.startswith(('\"', "'")) else text
        if not isinstance(value, str) or any(char in value for char in '\n\r'):
            raise ValueError(name + ' 请填写单行文本。')
        return value
    if not isinstance(original, (int, float)):
        raise ValueError(name + ' 不是可直接编辑的标量参数。')
    text = text.replace('D', 'e').replace('d', 'e')
    if code == 'cgyro':
        return parameter_value(name, text)
    try:
        number = float(text)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(name + ' 请填写有效数值。')
    if not math.isfinite(number):
        raise ValueError(name + ' 必须为有限数值。')
    if (name in ('NS', 'NKY', 'NMODES', 'NBASIS_MIN', 'NBASIS_MAX', 'SAT_RULE')
            or name.endswith(('_FLAG', '_MODEL', '_METHOD'))) and not number.is_integer():
        raise ValueError(name + ' 必须为整数。')
    return int(number) if number.is_integer() else number


def pending_inputs(root, destination=None):
    return {key: value for key, value in read(root, ('PROJECT_STATE', 'activity'), {}).items()
            if value.get('status', None) == 'awaiting_choice' and
            (destination is None or value.get('destination', 'tglf') == destination)}


def input_difference(current, incoming):
    rows = []
    for key in sorted(set(current.keys()) | set(incoming.keys()), key=str):
        before, after = key in current, key in incoming
        if before and after and input_digest(current[key]) == input_digest(incoming[key]):
            continue
        rows.append((str(key), '变化' if before and after else ('新增' if after else '移除'),
                     str(current[key]) if before else '—', str(incoming[key]) if after else '—'))
    return rows


def validate_input(value, kind):
    required = ('N_SPECIES', 'N_RADIAL', 'N_THETA', 'Q', 'RMIN', 'RMAJ') if kind == 'cgyro' else ('NS', 'KY')
    missing = [key for key in required if key not in value.keys()]
    if missing:
        raise ValueError('input.{} 缺少：{}'.format(kind, ', '.join(missing)))
    for key in (('N_SPECIES', 'N_RADIAL', 'N_THETA') if kind == 'cgyro' else ('NS',)):
        number = float(value[key])
        if not math.isfinite(number) or number < 1 or int(number) != number:
            raise ValueError(key + ' 必须为正整数')
    input_digest(value)


def transfer_upstream_digest(root):
    values = {}
    for path in [('Transfer_file', 'input.gacode'), ('Transfer_file', 'input.tglf'),
                 ('INPUTS', 'input.gacode'), ('INPUTS', 'input.tglf'), ('INPUTS', 'input.tgyro'),
                 ('OUTPUTS', 'Profiles_gen', 'input.gacode'),
                 ('SETTINGS', 'PHYSICS', 'generation')]:
        value = read(root, ('Transfer_tool',) + path)
        if value is not None:
            values['/'.join(path)] = input_digest(value)
    return input_digest(values)
