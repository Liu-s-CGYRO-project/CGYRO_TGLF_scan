"""Read CGYRO spectra once and prepare numeric scan data without making figures."""
from OMFITlib_cgyro_archive import catalog_runs, result_file
from builtins import IndexError, KeyError, OSError, TypeError, ValueError, any, dict, float, hasattr, int, len, list, max, str, tuple
import numpy as np
from OMFITlib_compare_core import cgyro_frequency_history, cgyro_frequency_stats, apply_divide_by_ky, normalize_if_needed, resolve_key
from OMFITlib_compare_cgyro_selection import maybe_abs_ky, maybe_abs_ky_list, parse_float_list_text
from OMFITlib_compare_state import stable_keys
from OMFITlib_cgyro_scan_view import coordinate_label, linear_node
from OMFITlib_cgyro_storage import result_view
from OMFITlib_cgyro_reference import is_native_file


def diagnostic(ctx, nr, para, value, message, ky=None):
    metadata = ctx.get('_cgyro_slices', {}).get((str(nr), str(para)), {})
    location = '{} / {} / {}'.format(ctx.get('runid', ''), nr, coordinate_label(metadata, value, para))
    if ky is not None:
        location += ' / ky={}'.format(ky)
    ctx.setdefault('_diagnostics', []).append(location + ': ' + str(message))


def _get_cgyro_lin_node(root, ctx, nr, para, value):
    view = ctx.get('_cgyro_views', {}).get(str(nr), None)
    if view is not None:
        return result_view(root.get('CGYRO_scan', {}), linear_node(view, para, value))
    node = catalog_runs(root.get('CGYRO_scan', {}))
    for token in (ctx.get('runid', ''), nr):
        if not hasattr(node, 'keys'):
            return None
        key = resolve_key(node, token)
        if key is None:
            return None
        node = node[key]
    return result_view(root.get('CGYRO_scan', {}), linear_node(node, para, value))


def _empty_series_arrays():
    return tuple(np.empty(0, dtype=float) for _ in (0, 1, 2, 3, 4, 5, 6))


def frequency_stats(data, window):
    """Keep the existing script API while sharing cross-model validation."""
    return cgyro_frequency_stats(data, window)


def compute_freq_stats(datadir, ave_window):
    """Compatibility helper for eigenmode selection, using the spectrum policy."""
    try:
        stats = frequency_stats(datadir, ave_window)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return {'omega_mean': stats[0][0], 'gamma_mean': stats[1][0],
            'omega_rel_err': stats[0][2], 'gamma_rel_err': stats[1][2]}


def _selection_input(data):
    """Read only generated input when display ky needs main-ion scaling.

    Selection must precede the OMFITcgyro mapping API: even asking that reader
    for input.cgyro.gen first parses frequency, field and flux arrays as well.
    Plain/custom in-memory mappings retain their existing input interface.
    """
    if not is_native_file(data):
        return data
    try:
        from omfit_classes.omfit_gacode import OMFITgacode
        return {'input.cgyro.gen': OMFITgacode(result_file(data, 'input.cgyro.gen'))}
    except (OSError, ValueError):
        return {}


def selected_linear_keys(linear, targets, ctx, normalized=False):
    """Select from saved ky coordinates before opening any science arrays.

    Signed coordinates remain distinct even when the display uses abs(ky).
    Empty targets mean the whole *selected spectrum*, never other scans.
    Non-numeric old keys may use their in-memory reader metadata as fallback.
    """
    keys = stable_keys(linear)
    if not len(targets):
        return keys
    candidates = []
    for key in keys:
        try:
            ky = float(key)
        except (TypeError, ValueError):
            data = linear[key]
            if is_native_file(data):
                raise ValueError('Missing numeric ky coordinate in saved result index: ' + str(key))
            ky = float(data['kyrhos'])
        if normalized and ctx.get('normalize_main_ion', False):
            ky, _, _ = normalize_if_needed(_selection_input(linear[key]), ky, 0., 0.,
                                           True)
        ky = float(maybe_abs_ky(ky, ctx))
        if np.isfinite(ky):
            candidates.append((key, ky))
    chosen = filter_single_ky(np.asarray([ky for _, ky in candidates]), targets)
    return [key for key, ky in candidates if ky in chosen]


def collect_value_series(root, ctx, nr, para, value, selected_ky=()):
    """Return sorted ky, omega, gamma, relative fluctuations and absolute std.

    Raw signed means precede display /ky scaling. Invalid samples are reported;
    a convergence filter is applied to both relative fluctuations together.
    The seven-array return contract is retained for existing OMFIT scripts.
    """
    linear = _get_cgyro_lin_node(root, ctx, nr, para, value)
    if linear is None or not len(linear):
        diagnostic(ctx, nr, para, value, 'No saved linear spectrum')
        return _empty_series_arrays()
    rows, rejected = [], 0
    for key in selected_linear_keys(linear, selected_ky, ctx, normalized=True):
        try:
            data = linear[key]
            stats = frequency_stats(data, ctx.get('ave_window', .02))
            ky, omega, gamma = normalize_if_needed(
                data, float(data['kyrhos']), np.asarray(stats[0][:2]), np.asarray(stats[1][:2]),
                ctx.get('normalize_main_ion', False))
            ky = float(maybe_abs_ky(ky, ctx))
            if not np.all(np.isfinite([ky, *omega, *gamma])):
                raise ValueError('Non-finite normalized spectrum')
            if ctx.get('error_filter', False) and any(
                    stat[2] > ctx.get('error_tolerance', .01) for stat in stats):
                rejected += 1
                continue
            rows.append((ky, omega[0], gamma[0], stats[0][2], stats[1][2], omega[1], gamma[1]))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            diagnostic(ctx, nr, para, value, exc, ky=key)
    if rejected:
        diagnostic(ctx, nr, para, value, '{} point(s) excluded by the fluctuation filter'.format(rejected))
    if not rows:
        return _empty_series_arrays()
    values = np.asarray(rows, dtype=float)
    values = values[np.argsort(values[:, 0], kind='stable')]
    return tuple(values[:, column] for column in (0, 1, 2, 3, 4, 5, 6))


def collect_time_series(root, ctx, nr, para, value):
    """Read selected ky histories directly, including unconverged points.

    Snap requested ky within each selected scan value's saved grid. Repeated
    targets select a point once; signed ky and unequal time grids stay intact.
    """
    linear = _get_cgyro_lin_node(root, ctx, nr, para, value)
    if linear is None or not len(linear):
        diagnostic(ctx, nr, para, value, 'No saved linear histories')
        return []
    traces = []
    for key in selected_linear_keys(linear, ctx.get('selected_time_ky', []), ctx):
        try:
            data = linear[key]
            ky = float(data['kyrhos'])
            if not np.isfinite(ky):
                raise ValueError('Non-finite saved ky')
            times, omega, gamma = cgyro_frequency_history(data)
            traces.append(dict(ky=ky, time=times, omega=omega, gamma=gamma))
        except (KeyError, IndexError, OSError, TypeError, ValueError) as exc:
            diagnostic(ctx, nr, para, value, exc, ky=key)
    return traces


def build_param_cloud(root, ctx, nr, para, para_values):
    """Gather finite displayed samples for single-ky curves and 3D scans."""
    chunks = []
    for value in para_values:
        numeric_value = float(value)
        if not np.isfinite(numeric_value):
            raise ValueError('Scan-axis values must be finite numbers: {}'.format(para))
        targets = ctx.get('selected_single_ky', []) if ctx.get('single_ky', False) else []
        ky, omega, gamma, *_ = collect_value_series(root, ctx, nr, para, value, selected_ky=targets)
        omega, gamma, _, _ = apply_divide_by_ky(
            ky, omega, gamma, ctx['divide_by_ky'], ctx.get('divide_by_ky2', False))
        valid = np.isfinite(ky) & np.isfinite(omega) & np.isfinite(gamma)
        if np.any(valid):
            chunks.append(np.column_stack((ky[valid], np.full(np.count_nonzero(valid), numeric_value),
                                           omega[valid], gamma[valid])))
    if not chunks:
        return tuple(np.empty(0) for _ in (0, 1, 2, 3))
    points = np.concatenate(chunks)
    return tuple(points[:, column] for column in (0, 1, 2, 3))


def filter_single_ky(unique_ky, selected_single_ky):
    """Snap requested ky to available points, deterministically removing repeats."""
    available = np.unique(unique_ky)
    if not len(selected_single_ky) or not len(available):
        return available
    indices = [int(np.argmin(np.abs(available - value))) for value in selected_single_ky]
    return np.unique(available[indices])


def grid_scan_points(ky, parameter, omega, gamma, parameter_values=None):
    """Group coordinates once, accumulate duplicates, and leave missing cells as NaN."""
    x, xi = np.unique(ky, return_inverse=True)
    y, yi = np.unique(parameter, return_inverse=True)
    if parameter_values is not None:
        y = np.unique(np.concatenate((y, np.asarray(parameter_values, dtype=float))))
        yi = np.searchsorted(y, parameter)
    shape = (len(y), len(x))
    count = np.zeros(shape, dtype=int)
    np.add.at(count, (yi, xi), 1)
    grids = []
    for values in (omega, gamma):
        total = np.zeros(shape)
        np.add.at(total, (yi, xi), values)
        result = np.full(shape, np.nan)
        np.divide(total, count, out=result, where=count > 0)
        grids.append(result)
    return x, y, grids[0], grids[1]


def parse_gamma_ref_ky_values(ctx):
    return maybe_abs_ky_list(parse_float_list_text(ctx.get('gamma_ref_ky_values', '')), ctx)


def get_gamma_ratio_curve(root, ctx, nr, para, para_values):
    """Use raw gamma, with a blank reference selecting the first valid scan value."""
    reference = ctx.get('gamma_ref_value', '')
    reference = None if reference is None or str(reference).strip() == '' else float(reference)
    if reference is not None and not np.isfinite(reference):
        raise ValueError('Reference scan value must be finite')
    single = ctx.get('gamma_ref_mode', None) == 'single ky'
    targets = parse_gamma_ref_ky_values(ctx) if single else []
    if single and not targets:
        raise ValueError('Enter at least one ky value for the growth-rate ratio')
    gamma_map = {}
    for value in para_values:
        numeric_value = float(value)
        if not np.isfinite(numeric_value):
            raise ValueError('Scan-axis values must be finite numbers: {}'.format(para))
        ky, _, gamma, *_ = collect_value_series(root, ctx, nr, para, value, selected_ky=targets)
        if not len(gamma):
            continue
        if single:
            indices = np.unique([int(np.argmin(np.abs(ky - target))) for target in targets])
            gamma_map[numeric_value] = float(np.mean(gamma[indices]))
        else:
            gamma_map[numeric_value] = float(np.max(gamma))
    if not gamma_map:
        return None
    available = np.asarray(list(gamma_map))
    reference = float(available[0] if reference is None else available[np.argmin(np.abs(available - reference))])
    denominator = gamma_map[reference]
    if denominator == 0:
        diagnostic(ctx, nr, para, reference, 'Reference gamma is zero; ratio is undefined')
        return None
    x = np.sort(available)
    with np.errstate(over='ignore', invalid='ignore'):
        ratio = np.asarray([gamma_map[value] / denominator for value in x])
    if not np.all(np.isfinite(ratio)):
        diagnostic(ctx, nr, para, reference, 'Non-finite growth-rate ratio')
        return None
    return x, ratio, reference
