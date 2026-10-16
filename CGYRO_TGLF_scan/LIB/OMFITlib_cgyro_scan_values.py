"""Resolve the same CGYRO value definitions for previews and submitted inputs."""
from builtins import bool, dict, float, int, isinstance, len, list, range, set, str
from collections import OrderedDict
import math
import re
from OMFITlib_cgyro_parameters import FIELDS, parameter_value

AXIS_KEYS = {0: (), 1: (('Para', 'Range'),),
             2: (('Para_x', 'Range_x'), ('Para_y', 'Range_y')),
             3: (('Para_x', 'Range_x'), ('Para_y', 'Range_y'), ('Para_z', 'Range_z'))}
VALUE_MODES = OrderedDict([('列表 / 表达式', 'list'), ('实际值范围', 'range'),
                           ('原值倍数', 'factor'), ('沿用输入', 'original')])
KY_MODES = OrderedDict([('列表 / 表达式', 'list'), ('线性范围', 'range'), ('对数范围', 'log')])
MAX_VALUES = 10000


def value_list(raw, caption):
    if hasattr(raw, 'tolist'):
        raw = raw.tolist()
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        raw = [raw]
    if isinstance(raw, (str, bytes)) or hasattr(raw, 'keys'):
        raise ValueError(caption + ' 请填写数值列表或生成数组的表达式。')
    try:
        values = list(raw)
    except TypeError:
        raise ValueError(caption + ' 请填写数值、列表或生成数组的表达式。')
    if not 1 <= len(values) <= MAX_VALUES:
        raise ValueError(caption + ' 的点数需在 1–10000 之间。')
    return values


def range_values(spec, caption, logarithmic=False):
    try:
        start, end = float(spec['start']), float(spec['end'])
        count = float(spec['count'])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError(caption + ' 的起点、终点和点数必须是有效数值。')
    if not math.isfinite(start) or not math.isfinite(end):
        raise ValueError(caption + ' 的起点和终点必须是有限数值。')
    if not math.isfinite(count) or not count.is_integer() or not 1 <= count <= MAX_VALUES:
        raise ValueError(caption + ' 的点数需为 1–10000 之间的整数。')
    count = int(count)
    if logarithmic and (start <= 0 or end <= 0):
        raise ValueError(caption + ' 的对数范围起点和终点必须大于 0。')
    if count == 1:
        return [start]
    if logarithmic:
        first, last = math.log(start), math.log(end)
        values = [math.exp(first + (last - first) * index / (count - 1)) for index in range(count)]
    elif start.is_integer() and end.is_integer() and (int(end) - int(start)) % (count - 1) == 0:
        # Preserve exact grid integers instead of introducing interpolation noise.
        step = (int(end) - int(start)) // (count - 1)
        values = [int(start) + step * index for index in range(count)]
    else:
        values = [start * (1 - index / (count - 1)) + end * (index / (count - 1)) for index in range(count)]
    values[0], values[-1] = start, end
    return values


def ky_values(physics):
    spec = physics.get('ky_spec', {})
    mode = spec.get('mode', 'list')
    if mode == 'list':
        raw = physics.get('kyarr', [])
    elif mode in ('range', 'log'):
        raw = range_values(spec, 'ky', logarithmic=mode == 'log')
    else:
        raise ValueError('请选择 ky 取值方式。')
    values = []
    for raw_value in value_list(raw, 'ky'):
        if hasattr(raw_value, 'item'):
            raw_value = raw_value.item()
        try:
            value = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError('ky 必须是有限正数。')
        if isinstance(raw_value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError('ky 必须是有限正数。')
        values.append(value)
    if len(set(values)) != len(values):
        raise ValueError('ky 取值重复，请检查列表或范围。')
    return values


def _parameter_values(group, range_key, name, source):
    spec = group.get('value_specs', {}).get(range_key, {})
    mode = spec.get('mode', 'list')
    if mode == 'list':
        raw = group.get(range_key, [])
    elif mode == 'range':
        raw = range_values(spec, name)
    elif mode == 'factor':
        raw = range_values(spec.get('factor', spec), name)
    elif mode == 'original':
        raw = [1]
    else:
        raise ValueError(name + ' 的取值方式无效。')
    if mode in ('factor', 'original'):
        if name in source:
            original = parameter_value(name, source[name])
        elif name in FIELDS:
            original = parameter_value(name, FIELDS[name][2])
        else:
            raise ValueError('输入中没有参数 ' + name + '，无法沿用或计算原值倍数。')
        if mode == 'factor' and original == 0:
            raise ValueError(name + ' 原值为 0，请使用实际值范围或指定列表。')
        raw = [original * value for value in raw]
    values = []
    for value in value_list(raw, name):
        if hasattr(value, 'item'):
            value = value.item()
        if isinstance(value, bool):
            raise ValueError(name + ' 请填写数值。')
        values.append(parameter_value(name, value))
    if len(set(values)) != len(values):
        raise ValueError(name + ' 取值重复，请检查列表或范围。')
    return values


def scan_axes(physics, dimensions, source):
    if dimensions not in AXIS_KEYS:
        raise ValueError('参数轴数量只能是 0、1、2 或 3。')
    group = physics.get(str(dimensions) + 'd', {})
    axes, names = [], set()
    for parameter_key, range_key in AXIS_KEYS[dimensions]:
        linked, index = [], 1
        while index == 1 or parameter_key + str(index) in group or range_key + str(index) in group:
            suffix = '' if index == 1 else str(index)
            pkey, rkey = parameter_key + suffix, range_key + suffix
            mode = group.get('value_specs', {}).get(rkey, {}).get('mode', 'list')
            if pkey not in group or (mode == 'list' and rkey not in group):
                raise ValueError('扫描参数的名称或取值缺失。')
            name = str(group[pkey]).strip()
            if not re.fullmatch(r'[A-Z][A-Z0-9_]*', name) or name == 'KY':
                raise ValueError('扫描参数名无效：' + (name or '空'))
            if name in names:
                raise ValueError('扫描参数重复：' + name)
            names.add(name)
            values = _parameter_values(group, rkey, name, source)
            item = dict(name=name, values=values)
            if index == 1:
                axis = item
            elif len(values) != len(axis['values']):
                raise ValueError('联动取值必须与主参数等长：' + name)
            else:
                linked.append(item)
            index += 1
        axis['linked'] = linked
        axes.append(axis)
    return axes
