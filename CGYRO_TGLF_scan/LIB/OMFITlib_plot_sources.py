"""Read-only adapters from archived runs to the comparison plotting contract.

No result is copied into a legacy cache or attached to another OMFIT tree.
New backends can provide the same radius / parameter / value / payload view.
"""
from builtins import any, dict, enumerate, float, int, iter, len, list, next, range, set, sorted, str, tuple
from collections import OrderedDict
from collections.abc import Mapping
import numpy as np
from OMFITlib_tglf_records import point_current, point_result, record_summary, run_records


def native_sources(scan):
    scopes = [('', scan, True), ('TGLF', scan.get('TGLF', {}), False)]
    scopes.extend(('source:' + str(key), value, False) for key, value in scan.get('sourceResults', {}).items())
    sources = {}
    for scope, node, radial in scopes:
        for dimension, key in (('1D', 'scanResults'), ('2D', 'scanResults2D'), ('3D', 'scanResults3D')):
            if node.get(key, None) or node.get(key + '_spectra', None):
                token = 'legacy:' + dimension if not scope else 'native:' + scope + ':' + dimension
                sources[token] = (node, radial, key, dimension)
    return sources


def run_choices(root):
    choices = OrderedDict()
    scan = root.get('TGLF_scan', {})
    runs = run_records(scan)
    for key in sorted(runs, key=str, reverse=True):
        record = runs[key]
        if not any(point_current(scan, p) for p in record.get('points', {}).values()):
            continue
        caption = record_summary(record, key)
        if record.get('mode', None) == '3d':
            caption += ' · 3D（按第三轴分片）'
        label, repeat = caption, 1
        while label in choices:
            repeat += 1
            label = caption + '（{}）'.format(repeat)
        choices[label] = str(key)
    for token, (_, radial, _, dimension) in native_sources(scan).items():
        caption = ('原生径向' if radial else token.split(':', 1)[1].rsplit(':', 1)[0]) + ' ' + dimension + ' 扫描'
        choices[caption + ('（按第三轴分片）' if dimension == '3D' else '')] = token
    return choices


def source_dimension(root, source):
    if str(source).startswith(('legacy:', 'native:')):
        return '2D' if str(source).rsplit(':', 1)[1] in ('2D', '3D') else '1D'
    record = run_records(root.get('TGLF_scan', {})).get(source, {})
    return '2D' if record.get('mode', record.get('plan', {}).get('mode', None)) in ('2d', '3d') else '1D'


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
    def __init__(self, point, module=None):
        self.point = point
        self.module = module
        self._result = None
        self._spectrum = None

    @property
    def result(self):
        if self._result is None:
            self._result = point_result(self.module, self.point) if self.module is not None else self.point.get('result', {})
        return self._result

    def __iter__(self):
        return iter(dict.fromkeys(list(self.result.keys()) + ['input.tglf']))

    def __len__(self):
        return len(set(self.result.keys()) | {'input.tglf'})

    def __getitem__(self, key):
        if key == 'input.tglf':
            return self.point['input'] if 'input' in self.point else self.result.get('input.tglf', {})
        if key == 'eigenvalue_spectrum' and self._spectrum is not None:
            return self._spectrum
        value = self.result[key]
        if key != 'eigenvalue_spectrum':
            return value
        ky, omega, gamma = spectrum_arrays(value)
        spec = {'ky': ky}
        for index in range(len(gamma)):
            spec['freq({})'.format(index + 1)] = omega[index]
            spec['gamma({})'.format(index + 1)] = gamma[index]
        # ResultView is a disposable per-operation view. Mode 1/2 and paired
        # comparison pages share this decode, without a saved array cache.
        self._spectrum = spec
        return spec


class NativeView(Mapping):
    """Descend native coordinate keys lazily; wrap only requested spectra."""
    def __init__(self, node, depth, target):
        self.node, self.depth, self.target = node, depth, target
        self.children = {}

    def __iter__(self):
        return iter(self.node)

    def __len__(self):
        return len(self.node)

    def __getitem__(self, key):
        if key in self.children:
            return self.children[key]
        value = self.node[key]
        if self.depth > 1:
            value = NativeView(value, self.depth - 1, self.target)
        elif self.target == 'Spectra':
            value = ResultView({'result': value})
        self.children[key] = value
        return value


def native_results(scan, source, target):
    selected = native_sources(scan).get(source, None)
    if selected is None:
        return {}
    node, radial, key, dimension = selected
    data = node.get(key + ('_spectra' if target == 'Spectra' else ''), {})
    if not radial:
        data = {source.split(':', 1)[1].rsplit(':', 1)[0]: data}
    if dimension != '3D':
        return NativeView(data, int(dimension[0]) + 2, target)
    # Existing 2D plotting controls show an explicit slice label for axis 3.
    # No third coordinate is discarded or combined with another slice.
    slices = {}
    for radius in data:
        for name, planes in data[radius].items():
            names = str(name).split('+')
            for value in planes:
                label = '{} · {}={}'.format(radius, names[0], value)
                slices.setdefault(label, {})['+'.join(names[1:])] = NativeView(planes[value], 2, target)
    return slices


def tglf_results(root, state, target='Spectra', dimension=None):
    """Resolve one explicit saved run, falling back to legacy only when selected."""
    scan = root.get('TGLF_scan', {})
    source = selected_tglf_source(root, state, dimension)
    if str(source).startswith(('legacy:', 'native:')):
        return native_results(scan, source, target)
    record = run_records(scan).get(source, {})
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
        if not point_current(scan, point):
            continue
        if target == 'Spectra' and 'result_path' not in point and 'eigenvalue_spectrum' not in point.get('result', {}):
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
        if mode == '3d':
            radius = '{} · {}={}'.format(radius, names[2], coordinates[2])
            names, coordinates = names[:2], coordinates[:2]
        node = output.setdefault(radius, {}).setdefault('+'.join(names), {})
        for coordinate in coordinates[:-1]:
            node = node.setdefault(coordinate, {})
        if coordinates[-1] in node:
            raise ValueError('运行记录存在重复计算点：' + str(point_id))
        node[coordinates[-1]] = ResultView(point, scan)
    return output


def context_results(root, ctx, target='Spectra', dimension=None):
    """Build the metadata view once per plot/export, never once per curve."""
    state = ctx.get('tglf_state', {})
    key = (state.get('result_source', ''), target, dimension)
    cache = ctx.setdefault('_tglf_result_views', {})
    if key not in cache:
        cache[key] = tglf_results(root, state, target, dimension)
    return cache[key]
