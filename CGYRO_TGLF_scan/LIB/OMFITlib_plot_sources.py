"""Read-only adapters from archived runs to the comparison plotting contract.

No result is copied into a legacy cache or attached to another OMFIT tree.
New backends can provide the same radius / parameter / value / payload view.
"""
from builtins import any, dict, enumerate, float, int, iter, len, list, next, range, set, sorted, str, tuple
from collections import OrderedDict
from collections.abc import Mapping
import numpy as np
from OMFITlib_tglf_records import record_summary


def run_choices(root):
    choices = OrderedDict()
    runs = root.get('TGLF_scan', {}).get('RUN_DB', {})
    for key in sorted(runs, key=str, reverse=True):
        record = runs[key]
        if not any(p.get('status', None) == 'complete' for p in record.get('points', {}).values()):
            continue
        caption = record_summary(record, key)
        label, repeat = caption, 1
        while label in choices:
            repeat += 1
            label = caption + '（{}）'.format(repeat)
        choices[label] = str(key)
    scan = root.get('TGLF_scan', {})
    for dimension in ('1D', '2D'):
        key = 'scanResults2D' if dimension == '2D' else 'scanResults'
        if scan.get(key, None) or scan.get(key + '_spectra', None):
            choices['旧版 ' + dimension + ' 扫描'] = 'legacy:' + dimension
    return choices


def source_dimension(root, source):
    if str(source).startswith('legacy:'):
        return str(source).split(':', 1)[1]
    record = root.get('TGLF_scan', {}).get('RUN_DB', {}).get(source, {})
    return '2D' if record.get('mode', record.get('plan', {}).get('mode', None)) == '2d' else '1D'


def selected_tglf_source(root, state, dimension=None, choices=None):
    """Resolve pre-run-record selections without changing their saved dimension.

    Older projects only saved spectra_mode. Both the GUI and readers must
    migrate that setting before selecting the first available run, otherwise
    opening a selector can turn a saved 2D comparison into 1D and prune axes.
    Explicit sources remain explicit; callers decide how to show missing runs.
    """
    source = state.get('result_source', '')
    if source:
        return source
    if choices is None:
        choices = run_choices(root)
    legacy = 'legacy:' + str(dimension or state.get('spectra_mode', '1D'))
    return legacy if legacy in choices.values() else next(iter(choices.values()), '')


def spectrum_arrays(spectrum):
    """Return mode-by-ky arrays from both native xarray and older named columns."""
    ky = np.asarray(spectrum['ky'], dtype=float).ravel()
    if 'gamma' in spectrum and 'freq' in spectrum:
        values = []
        for key in ('freq', 'gamma'):
            data = spectrum[key]
            if hasattr(data, 'dims') and 'mode_num' in data.dims and 'ky' in data.dims:
                data = data.transpose('mode_num', 'ky')
            values.append(np.atleast_2d(np.asarray(data, dtype=float)))
        omega, gamma = values
    else:
        modes = sorted(int(str(key)[6:-1]) for key in spectrum
                       if str(key).startswith('gamma(') and str(key).endswith(')'))
        if not modes:
            raise ValueError('结果中没有频率 / 增长率谱')
        omega = np.asarray([spectrum['freq({})'.format(i)] for i in modes], dtype=float)
        gamma = np.asarray([spectrum['gamma({})'.format(i)] for i in modes], dtype=float)
    if omega.shape != gamma.shape or omega.shape[1] != len(ky):
        raise ValueError('TGLF 谱的模态数或 ky 维度不一致')
    return ky, omega, gamma


class ResultView(Mapping):
    """Lazy payload view: opening a selector never parses output arrays."""
    def __init__(self, point):
        self.point = point
        self.result = point.get('result', {})

    def __iter__(self):
        return iter(dict.fromkeys(list(self.result.keys()) + ['input.tglf']))

    def __len__(self):
        return len(set(self.result.keys()) | {'input.tglf'})

    def __getitem__(self, key):
        if key == 'input.tglf':
            return self.point['input'] if 'input' in self.point else self.result.get('input.tglf', {})
        value = self.result[key]
        if key != 'eigenvalue_spectrum':
            return value
        ky, omega, gamma = spectrum_arrays(value)
        spec = {'ky': ky}
        for index in range(len(gamma)):
            spec['freq({})'.format(index + 1)] = omega[index]
            spec['gamma({})'.format(index + 1)] = gamma[index]
        return spec


def tglf_results(root, state, target='Spectra', dimension=None):
    """Resolve one explicit saved run, falling back to legacy only when selected."""
    scan = root.get('TGLF_scan', {})
    source = selected_tglf_source(root, state, dimension)
    if str(source).startswith('legacy:'):
        dimension = source_dimension(root, source)
        key = 'scanResults2D' if dimension == '2D' else 'scanResults'
        return scan.get(key + ('_spectra' if target == 'Spectra' else ''), {})
    record = scan.get('RUN_DB', {}).get(source, {})
    saved = record.get('plan', {})
    axes = saved.get('axes', [])
    sources = {tuple(s.get('path', ())): s for s in saved.get('sources', [])}
    # A repeated numeric radius from distinct inputs must not overwrite another.
    radius_owners = {}
    for path, item in sources.items():
        key = item.get('rho', None)
        if key is not None:
            radius_owners.setdefault(key, []).append(path)
    output = {}
    for index, (point_id, point) in enumerate(record.get('points', {}).items(), 1):
        if point.get('status', None) != 'complete':
            continue
        result = point.get('result', {})
        if target == 'Spectra' and 'eigenvalue_spectrum' not in result:
            continue
        source_path = tuple(point.get('source', ()))
        item = sources.get(source_path, {})
        radius = item.get('rho', None)
        if radius is None or len(radius_owners.get(radius, [])) > 1 or item.get('coordinate', 'rho') != 'rho':
            radius = point.get('label', '输入')
            # Include path identity for equally labelled imported inputs.
            if any(p != source_path and s.get('label', None) == radius for p, s in sources.items()):
                radius = str(radius) + ' / ' + '/'.join(str(k) for k in source_path)
        values = point.get('parameters', {})
        mode = record.get('mode', saved.get('mode', None))
        if mode == 'uq':
            names, coordinates = ['样本'], [index]
        elif axes:
            names = [axis['name'] for axis in axes]
            if any(name not in values for name in names):
                continue
            coordinates = [values[name] for name in names]
        else:
            names, coordinates = ['原值'], [0]
        node = output.setdefault(radius, {}).setdefault('+'.join(names), {})
        for coordinate in coordinates[:-1]:
            node = node.setdefault(coordinate, {})
        if coordinates[-1] in node:
            raise ValueError('运行记录存在重复计算点：' + str(point_id))
        node[coordinates[-1]] = ResultView(point)
    return output


def context_results(root, ctx, target='Spectra', dimension=None):
    """Build the metadata view once per plot/export, never once per curve."""
    state = ctx.get('tglf_state', {})
    key = (state.get('result_source', ''), target, dimension)
    cache = ctx.setdefault('_tglf_result_views', {})
    if key not in cache:
        cache[key] = tglf_results(root, state, target, dimension)
    return cache[key]
