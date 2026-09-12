"""CGYRO self-comparison spectra, export and eigenfunctions.

Shared presentation/statistics live in the comparison style/core libraries.
"""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    ImportError,
    KeyError,
    RuntimeWarning,
    TypeError,
    ValueError,
    abs,
    all,
    bool,
    complex,
    dict,
    enumerate,
    float,
    getattr,
    hasattr,
    int,
    isinstance,
    len,
    list,
    max,
    min,
    object,
    open,
    print,
    range,
    repr,
    set,
    slice,
    sorted,
    str,
    sum,
    tuple,
)
import ast
import hashlib
import numpy as np
import os
import matplotlib.pyplot as plt
import re
import tempfile
import warnings
from numpy import (
    argmax,
    argmin,
    argsort,
    array,
    errstate,
    full,
    gradient,
    imag,
    interp,
    iscomplexobj,
    isfinite,
    linspace,
    mean,
    nan,
    nanmax,
    ones,
    pi,
    real,
    sqrt,
    tile,
    unique,
    zeros,
)
from OMFITlib_compare_style import (
    _default_color_cycle,
    _sort_label_handle_pairs,
    apply_figure_layout,
    finalize_axis_legend,
    style_2d_axes,
)
from OMFITlib_compare_core import (
    _tail_frequency_stats,
    apply_divide_by_ky,
    divide_title,
)
from OMFITlib_compare_state import (
    STYLE_DEFAULTS,
    stable_keys,
    selection_check,
)


DEFAULT_FIGSIZE_2X2 = (12.5, 6.5)


DEFAULT_FIGSIZE_1X2 = (13.0, 5.6)


DEFAULT_FIGSIZE_GAMMA_RATIO = (9.0, 5.4)


DEFAULT_FIGSIZE_EIGEN = (12.5, 6.5)


DEFAULT_FIGSIZE_3D = (14.0, 5.9)




def parse_float_list_text(text):
    """Parse comma-separated float text from GUI settings."""
    if not isinstance(text, str) or len(text.strip()) == 0:
        return []
    try:
        return [float(x.strip()) for x in text.split(',') if len(x.strip()) > 0]
    except Exception:
        return []


def _parse_gui_value_text(text):
    """Parse OMFIT Entry text that may look like comma text or a Python list."""
    if not isinstance(text, str):
        return []
    text = text.strip()
    if len(text) == 0:
        return []

    quoted_tokens = re.findall(r"['\"]([^'\"]+)['\"]", text)
    if len(quoted_tokens) > 1:
        return quoted_tokens

    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple, set)):
            return list(parsed)
        return [parsed]
    except Exception:
        pass

    float_vals = parse_float_list_text(text)
    if len(float_vals) > 0:
        return float_vals

    return [t.strip().strip('"').strip("'") for t in re.split(r'[\s,]+', text) if len(t.strip()) > 0]


def parse_single_ky_values(root):
    """Read user-selected single-ky values for 'Plot single ky' mode."""
    text = root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO'].get('single_ky_values', '')
    return parse_float_list_text(text)


def parse_eigen_ky_values(root):
    """Read user-selected ky values for eigen-ball plotting."""
    text = root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO'].get('eigen_ky_values', '')
    return parse_float_list_text(text)


def maybe_abs_ky(ky, ctx):
    """Return ky or |ky| according to the CGYRO-vs-CGYRO plot option."""
    if not ctx.get('abs_ky', False):
        return ky
    try:
        return abs(array(ky, dtype=float))
    except Exception:
        try:
            return abs(float(ky))
        except Exception:
            return ky


def maybe_abs_ky_list(values, ctx):
    """Apply abs ky to parsed GUI ky target lists."""
    if not ctx.get('abs_ky', False):
        return values
    out = []
    for item in values:
        try:
            out.append(abs(float(item)))
        except Exception:
            pass
    return out


def _color_group_label(label):
    """
    Return the case key used for color assignment.

    Eigen-ball pages draw Re/Im (or |.|) entries as separate legend lines,
    but those entries belong to one case and must share one color.  Ordinary
    plot labels are returned unchanged.
    """
    text = str(label)
    for suffix in (', Re', ', Im', ', |.|'):
        if text.endswith(suffix):
            return text[:-len(suffix)]
    return text


def apply_color_order_to_axes(axes_obj, ctx):
    """
    Re-assign colors by configured legend order across a page's axes.

    The mapping is based on unique case labels, so repeated labels in error
    and omega/gamma panels stay synchronized.  Eigen-ball Re/Im lines use a
    shared case key via ``_color_group_label``.
    """
    try:
        axes_list = list(array(axes_obj, dtype=object).ravel())
    except Exception:
        axes_list = [axes_obj]
    axes_list = [axi for axi in axes_list if axi is not None]

    groups_in_plot_order = []
    group_to_representative = {}
    for axi in axes_list:
        for ln in axi.get_lines():
            label = str(ln.get_label())
            if label.startswith('_'):
                continue
            group = _color_group_label(label)
            if group not in group_to_representative:
                groups_in_plot_order.append(group)
                group_to_representative[group] = label

    if len(groups_in_plot_order) == 0:
        return

    representative_labels = [group_to_representative[group] for group in groups_in_plot_order]
    sorted_pairs = _sort_label_handle_pairs(
        representative_labels,
        groups_in_plot_order,
        ctx,
    )
    sorted_groups = [pair[1] for pair in sorted_pairs]
    colors = _default_color_cycle()
    group_to_color = {
        group: colors[idx % len(colors)]
        for idx, group in enumerate(sorted_groups)
    }

    for axi in axes_list:
        for ln in axi.get_lines():
            label = str(ln.get_label())
            if label.startswith('_'):
                continue
            group = _color_group_label(label)
            if group in group_to_color:
                ln.set_color(group_to_color[group])

        if axi.get_legend() is not None:
            # Rebuild legends after the color update so legend handles and
            # click-to-hide callbacks continue to match the data lines.
            finalize_axis_legend(axi, ctx)


def is_gamma_ratio_plot_mode(plot_mode):
    """True when plot mode is gamma-ratio mode (including legacy labels)."""
    mode_txt = str(plot_mode).strip()
    return mode_txt == 'Plot γ/γ_ref'


def _matching_value(mapping, wanted_key, default=None):
    """Get a mapping value by exact key first, then string-equivalent key."""
    if not hasattr(mapping, 'get'):
        return default
    try:
        if wanted_key in mapping:
            return mapping.get(wanted_key, default)
    except Exception:
        pass
    wanted_text = str(wanted_key)
    try:
        for key in mapping.keys():
            if str(key) == wanted_text:
                return mapping.get(key, default)
    except Exception:
        pass
    return default


def _filter_selected_map_by_key_flags(selected_map, flag_map):
    """Keep only selected parameters whose key-based checkbox is currently on."""
    if not hasattr(selected_map, 'items'):
        return {}
    if not hasattr(flag_map, 'keys') or len(flag_map) == 0:
        return selected_map

    filtered = {}
    for key, value in selected_map.items():
        if bool(_matching_value(flag_map, key, False)):
            filtered[key] = value
    return filtered


def _filter_selected_map_by_index_flags(selected_map, flag_map, ordered_names):
    """Keep only selected parameters whose index-based checkbox is currently on."""
    if not hasattr(selected_map, 'items'):
        return {}
    if not hasattr(flag_map, 'keys') or len(flag_map) == 0:
        return selected_map
    if len(ordered_names) == 0:
        return selected_map

    enabled = set()
    for idx, pname in enumerate(ordered_names):
        if bool(_matching_value(flag_map, idx, False)):
            enabled.add(str(pname))

    return {key: value for key, value in selected_map.items() if str(key) in enabled}


def _current_cgyro_parameter_names(root, runid, nr_list, force_read_all):
    """Rebuild the GUI parameter list so index flags map to current names."""
    try:
        run_db = root['CGYRO_scan']['RUN_DB']
        runid_key = _resolve_mapping_key(run_db, runid)
        if runid_key is None:
            return []
        run_node = run_db.get(runid_key, {})
    except Exception:
        return []

    keysets = []
    for nr in nr_list:
        try:
            nr_key = _resolve_mapping_key(run_node, nr)
            if nr_key is None:
                continue
            nr_node = run_node.get(nr_key, {})
            if hasattr(nr_node, 'keys'):
                keysets.append(set(nr_node.keys()))
        except Exception:
            continue

    if len(keysets) == 0:
        return []
    if force_read_all:
        names = set.union(*keysets)
    else:
        names = set.intersection(*keysets)
    names = list(names)
    try:
        names.sort()
    except Exception:
        pass
    return stable_keys(dict.fromkeys(names))


def _merge_selected_by_nr(selected_by_nr):
    """Build a global selected-parameter map from filtered per-nr selections."""
    merged = {}
    if not hasattr(selected_by_nr, 'items'):
        return merged
    for _nr, per_nr in selected_by_nr.items():
        if not hasattr(per_nr, 'items'):
            continue
        for para, values in per_nr.items():
            if para not in merged:
                merged[para] = values
    return merged


def _sanitize_selected_parameters(root, settings):
    """Return selections that agree with the current GUI checkbox flags."""
    force_read_all = bool(settings.get('force_read_all_nr_items', False))
    nr_list = settings.get('nr_CGYRO', [])

    if force_read_all:
        selected_by_nr = settings.get('selected_paras_by_nr', {})
        flags_by_nr = settings.get('para_list_flag_by_nr', {})
        filtered_by_nr = {}
        if hasattr(selected_by_nr, 'items'):
            for nr_key, per_nr in selected_by_nr.items():
                flags = _matching_value(flags_by_nr, nr_key, {})
                filtered_by_nr[str(nr_key)] = _filter_selected_map_by_key_flags(per_nr, flags)
        return _merge_selected_by_nr(filtered_by_nr), filtered_by_nr

    selected_map = settings.get('selected_paras', {})
    ordered_names = _current_cgyro_parameter_names(
        root,
        settings.get('runid', ''),
        nr_list,
        force_read_all=False,
    )
    selected_map = _filter_selected_map_by_index_flags(
        selected_map,
        settings.get('para_list_flag', {}),
        ordered_names,
    )
    return selected_map, {}


def build_context(root):
    """Collect all CGYRO-vs-CGYRO plotting settings into one runtime context."""
    settings = root['SETTINGS']['PHYSICS']['CGYRO_vs_CGYRO']
    legacy_physics = root['SETTINGS'].get('PHYSICS', {})
    ctx = {}
    ctx['plotcgyro'] = settings.get('plotcgyro', legacy_physics.get('plotcgyro', True))
    ctx['plot_mode'] = settings.get('plot_mode', 'Plot 2D')
    ctx['plot_3d'] = (ctx['plot_mode'] == 'Plot 3D')
    ctx['single_ky'] = (ctx['plot_mode'] == 'Plot single ky')
    ctx['plot_gamma_ratio'] = is_gamma_ratio_plot_mode(ctx['plot_mode'])
    ctx['plot_eigen_ball'] = (ctx['plot_mode'] == 'Plot eigen ball')
    ctx['abs_ky'] = bool(settings.get('abs_ky', legacy_physics.get('abs_ky', False)))
    ctx['selected_single_ky'] = parse_single_ky_values(root)
    ctx['gamma_ref_mode'] = settings.get('gamma_ref_mode', 'all ky')
    ctx['gamma_ref_value'] = settings.get('gamma_ref_value', '')
    ctx['gamma_ref_ky_values'] = settings.get('gamma_ref_ky_values', '')
    ctx['eigen_ky_mode'] = settings.get('eigen_ky_mode', 'max gamma')
    ctx['selected_eigen_ky'] = parse_eigen_ky_values(root)
    ctx['eigen_abs'] = settings.get('eigen_abs', False)
    ctx['eigen_error_filter'] = settings.get('eigen_error_filter', False)

    ctx['runid'] = settings.get('runid', '')
    ctx['nr_CGYRO'] = settings.get('nr_CGYRO', [])
    # Backward compatible: legacy `nr_plot_mode` still works.
    legacy_merge = (settings.get('nr_plot_mode', 'Split by nr') == 'All nr in one figure')
    ctx['merge_all_nr_plot'] = bool(settings.get('merge_all_nr_plot', legacy_merge))
    ctx['selected_paras'], ctx['selected_paras_by_nr'] = _sanitize_selected_parameters(root, settings)

    ctx['error_flag'] = settings.get('error_flag', 'CGYRO')
    ctx['effnum'] = settings.get('effnum', 5)
    ctx['style'] = dict(STYLE_DEFAULTS, **settings.get('style', {}))
    ctx['ave_window'] = settings.get('ave_window', 0.02)

    ctx['plot_log_x'] = settings.get('plot_log_x', False)
    ctx['plot_log_y'] = settings.get('plot_log_y', False)
    ctx['plot_log_z'] = settings.get('plot_log_z', False)
    ctx['normalize_main_ion'] = settings.get('normalize_main_ion', False)
    ctx['divide_by_ky'] = settings.get('divide_by_ky', True)
    ctx['divide_by_ky2'] = settings.get('divide_by_ky2', False)
    ctx['error_filter'] = settings.get('error_filter', True)
    ctx['highlight_max_gamma'] = settings.get('highlight_max_gamma', False)
    ctx['export_linear_now'] = settings.get('linear_export_now', False)
    ctx['export_linear_dir'] = settings.get('linear_export_dir', '')
    ctx['legend_order_mode'] = settings.get('legend_order_mode', 'Plot order')
    ctx['legend_order_text'] = settings.get('legend_order_text', '')
    try:
        ctx['error_tolerance'] = float(settings.get('error_tolerance', 0.01))
    except Exception:
        ctx['error_tolerance'] = 0.01
    if ctx['error_tolerance'] <= 0:
        ctx['error_tolerance'] = 0.01

    ctx['ms'] = 8
    ctx['lw'] = float(ctx['style']['line_width'])
    ctx['fs1'] = float(ctx['style']['font_size'])
    ctx['fs2'] = float(ctx['style']['legend_font_size'])
    ctx['fs3'] = float(ctx['style']['font_size'])
    ctx['bwith'] = 1.5

    ctx['selected_single_ky'] = maybe_abs_ky_list(ctx['selected_single_ky'], ctx)
    ctx['selected_eigen_ky'] = maybe_abs_ky_list(ctx['selected_eigen_ky'], ctx)
    return ctx


def _combine_nr_on_single_page(ctx):
    """
    True when user requests merged-nr plotting in one figure page.

    3D mode remains split by nr because each parameter builds a dedicated 3D surface page.
    """
    return (
        bool(ctx.get('merge_all_nr_plot', False))
        and len(ctx.get('nr_CGYRO', [])) > 1
        and (not ctx.get('plot_3d', False))
    )


def _legend_nr_prefix(ctx, nr):
    """Legend prefix used to distinguish curves when multiple nr share one page."""
    if _combine_nr_on_single_page(ctx):
        return f'[{nr}] '
    return ''


def _nr_title_text(ctx, nr):
    """Readable nr token for axis titles in split/combined modes."""
    if _combine_nr_on_single_page(ctx):
        return 'all selected nr'
    return str(nr)


def normalize_if_needed(datadir, ky_val, omega_val, gamma_val, normalize_main_ion):
    """
    Apply main-ion normalization to ky / omega / gamma when requested.

    omega/ky and gamma/ky are computed after this step using normalized ky.

    Rule follows CGYRO input: among ions, choose the species with largest density.
    """
    if not normalize_main_ion:
        return ky_val, omega_val, gamma_val
    if not hasattr(datadir, 'get') or 'input.cgyro.gen' not in datadir:
        return ky_val, omega_val, gamma_val

    try:
        inp = datadir['input.cgyro.gen']
        ns = int(inp.get('N_SPECIES', 1))
    except Exception:
        return ky_val, omega_val, gamma_val

    max_dens = -1
    main_ion_idx = -1
    for k in range(1, ns):
        try:
            dens = inp.get(f'DENS_{k}', 0)
        except Exception:
            dens = 0
        if dens > max_dens:
            max_dens = dens
            main_ion_idx = k

    if main_ion_idx == -1:
        return ky_val, omega_val, gamma_val

    try:
        z_main = inp.get(f'Z_{main_ion_idx}', 1.0)
        mass_main = inp.get(f'MASS_{main_ion_idx}', 1.0)
        ky_val = ky_val * sqrt(mass_main / 1.0) / z_main
        omega_val = omega_val * sqrt(mass_main / 1.0)
        gamma_val = gamma_val * sqrt(mass_main / 1.0)
    except Exception:
        return ky_val, omega_val, gamma_val

    return ky_val, omega_val, gamma_val


def _empty_series_arrays():
    """Return empty ky/omega/gamma/error arrays in the standard tuple shape."""
    return (
        array([]), array([]), array([]),
        array([]), array([]), array([]), array([])
    )


def _resolve_mapping_key(mapping, wanted_key):
    """
    Resolve one key against dict-like mappings with light type normalization.

    Preference order:
    1) exact key match
    2) string-equivalent key match
    3) float-equivalent key match
    """
    if not hasattr(mapping, 'keys'):
        return None

    try:
        if wanted_key in mapping:
            return wanted_key
    except Exception:
        pass

    wanted_text = str(wanted_key)
    for key in mapping.keys():
        if str(key) == wanted_text:
            return key

    try:
        wanted_float = float(wanted_key)
    except Exception:
        return None

    for key in mapping.keys():
        try:
            if float(key) == wanted_float:
                return key
        except Exception:
            continue
    return None


def _get_cgyro_lin_node(root, ctx, nr, para, value):
    """
    Safely access RUN_DB[runid][nr][para][value]['lin'].

    Returns the `lin` node or `None` when any level is missing.
    """
    try:
        run_db = root['CGYRO_scan']['RUN_DB']
    except Exception:
        return None

    runid_key = _resolve_mapping_key(run_db, ctx.get('runid', ''))
    if runid_key is None:
        return None

    run_node = run_db.get(runid_key, {})
    nr_key = _resolve_mapping_key(run_node, nr)
    if nr_key is None:
        return None

    nr_node = run_node.get(nr_key, {})
    para_key = _resolve_mapping_key(nr_node, para)
    if para_key is None:
        return None

    para_node = nr_node.get(para_key, {})
    value_key = _resolve_mapping_key(para_node, value)
    if value_key is None:
        return None

    value_node = para_node.get(value_key, {})
    if not hasattr(value_node, 'get'):
        return None

    lin_node = value_node.get('lin', None)
    if lin_node is None or not hasattr(lin_node, 'keys'):
        return None
    return lin_node


def _safe_text_token(value):
    """Convert arbitrary value into a filesystem-safe token."""
    s = str(value)
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', s)


def _export_linear_omega_gamma_vs_ky(ctx, nr, para, value, ky, omega, gamma,
                                     omega_error, gamma_error, omega_standard_err, gamma_standard_err,
                                     export_dir):
    """Export one (parameter,value) linear spectrum as a plain text table."""
    if len(ky) == 0:
        return

    ky = array(ky).ravel()
    omega = array(omega).ravel()
    gamma = array(gamma).ravel()
    omega_error = array(omega_error).ravel()
    gamma_error = array(gamma_error).ravel()
    omega_standard_err = array(omega_standard_err).ravel()
    gamma_standard_err = array(gamma_standard_err).ravel()

    n = min(
        len(ky),
        len(omega),
        len(gamma),
        len(omega_error),
        len(gamma_error),
        len(omega_standard_err),
        len(gamma_standard_err),
    )
    if n <= 0:
        return

    ky = ky[:n]
    omega = omega[:n]
    gamma = gamma[:n]
    omega_error = omega_error[:n]
    gamma_error = gamma_error[:n]
    omega_standard_err = omega_standard_err[:n]
    gamma_standard_err = gamma_standard_err[:n]

    sort_idx = argsort(ky)
    ky = ky[sort_idx]
    omega = omega[sort_idx]
    gamma = gamma[sort_idx]
    omega_error = omega_error[sort_idx]
    gamma_error = gamma_error[sort_idx]
    omega_standard_err = omega_standard_err[sort_idx]
    gamma_standard_err = gamma_standard_err[sort_idx]

    runid = _safe_text_token(ctx.get('runid', 'unknown'))
    nr_tok = _safe_text_token(nr)
    para_tok = _safe_text_token(para)
    val_tok = _safe_text_token(value) + '_' + hashlib.sha256(repr((nr, para, value)).encode('utf-8')).hexdigest()[:10]

    header = [
        "# CGYRO_vs_CGYRO linear spectrum export",
        f"# runid={runid}, nr={nr_tok}, para={para_tok}, value={val_tok}",
        f"# normalize_main_ion={ctx.get('normalize_main_ion', False)}; main ion=max-density ion before electron",
        "# native units: ky=k_y*rho_s, omega/gamma=c_s/a; main-ion option scales ky by sqrt(MASS)/Z and frequencies/std by sqrt(MASS)",
        f"# tail_fraction={ctx.get('ave_window', 0.5)}; minimum_tail_samples=2; error_filter={ctx.get('error_filter', False)}; relative_std_tolerance={ctx.get('error_tolerance', 0.01)}",
        "# gamma is the unclipped tail mean; std is population standard deviation, not standard error of the mean",
        "# columns: ky omega gamma omega_rel_err gamma_rel_err omega_std gamma_std",
    ]
    body = [
        f"{ky[i]:.12e} {omega[i]:.12e} {gamma[i]:.12e} "
        f"{omega_error[i]:.12e} {gamma_error[i]:.12e} "
        f"{omega_standard_err[i]:.12e} {gamma_standard_err[i]:.12e}"
        for i in range(n)
    ]
    text = "\n".join(header + body) + "\n"

    path = os.path.join(
        export_dir,
        f"omega_gamma_vs_ky__runid_{runid}__nr_{nr_tok}__{para_tok}_{val_tok}.txt"
    )
    abspath = os.path.abspath(path)
    try:
        os.makedirs(os.path.dirname(abspath), exist_ok=True)
        with open(abspath, 'x', encoding='utf-8') as f:
            f.write(text)
        return abspath
    except Exception as e:
        print(f"Warning: failed to export omega/gamma spectrum to {abspath}: {e}")
        return None


def collect_value_series(root, ctx, nr, para, value):
    """
    Read one full ky spectrum for a single `(nr, para, value)` point.

    Returns arrays:
    - ky, omega, gamma
    - omega_error, gamma_error (relative error over tail averaging window)
    - omega_standard_err, gamma_standard_err (absolute std over same window)
    """
    cgyrodir = _get_cgyro_lin_node(root, ctx, nr, para, value)
    if cgyrodir is None:
        return _empty_series_arrays()

    kyarr = cgyrodir.keys()
    k_num = len(kyarr)
    if k_num == 0:
        return _empty_series_arrays()

    omega = zeros(k_num)
    gamma = zeros(k_num)
    omega_error = zeros(k_num)
    gamma_error = zeros(k_num)
    omega_standard_err = zeros(k_num)
    gamma_standard_err = zeros(k_num)
    ky = zeros(k_num)
    j = 0

    for i in kyarr:
        datadir = cgyrodir[i]
        try:
            ntime = datadir['n_time']
            ind = int(ntime * ctx['ave_window'])
            if ind <= 1:
                ind = 2

            omega_arr = [float(item) for item in datadir['freq']['omega'][0][-1 * ind:]]
            gamma_arr = [float(item) for item in datadir['freq']['gamma'][0][-1 * ind:]]

            stats = _tail_frequency_stats(omega_arr, gamma_arr)
            if stats is None:
                continue
            omega_val, omega_standard_err_val, omega_err_val = stats[0]
            gamma_val, gamma_standard_err_val, gamma_err_val = stats[1]

            ky_val = datadir['kyrhos']
            ky_val, omega_val, gamma_val = normalize_if_needed(
                datadir, ky_val, omega_val, gamma_val, ctx['normalize_main_ion']
            )
            _, omega_standard_err_val, gamma_standard_err_val = normalize_if_needed(
                datadir, 0.0, omega_standard_err_val, gamma_standard_err_val, ctx['normalize_main_ion']
            )
            ky_val = maybe_abs_ky(ky_val, ctx)
            if not np.all(np.isfinite([ky_val, omega_val, gamma_val,
                                       omega_standard_err_val, gamma_standard_err_val])):
                continue
        except Exception:
            continue

        omega[j] = omega_val
        gamma[j] = gamma_val
        omega_error[j] = omega_err_val
        gamma_error[j] = gamma_err_val
        omega_standard_err[j] = omega_standard_err_val
        gamma_standard_err[j] = gamma_standard_err_val


        ky[j] = ky_val
        j += 1

        if ctx['error_filter']:
            tol = ctx.get('error_tolerance', 0.01)
            if omega_error[j-1] > tol or gamma_error[j-1] > tol:
                j -= 1

    valid = slice(0, j)
    ky_out = ky[valid]
    omega_out = omega[valid]
    gamma_out = gamma[valid]
    omega_error_out = omega_error[valid]
    gamma_error_out = gamma_error[valid]
    omega_standard_err_out = omega_standard_err[valid]
    gamma_standard_err_out = gamma_standard_err[valid]
    return ky_out, omega_out, gamma_out, omega_error_out, gamma_error_out, omega_standard_err_out, gamma_standard_err_out


def export_selected_linear_spectra(root, ctx):
    """Batch-export selected linear spectra when GUI export switch is enabled."""
    export_dir = str(ctx.get('export_linear_dir', '')).strip()
    if len(export_dir) == 0:
        print("Export canceled: no output directory selected.")
        return

    try:
        os.makedirs(export_dir, exist_ok=True)
    except Exception as e:
        print(f"Export failed: cannot create output directory {export_dir}: {e}")
        return

    if not hasattr(ctx.get('selected_paras', None), 'keys'):
        print("Export canceled: no selected parameters.")
        return

    export_dir = tempfile.mkdtemp(prefix='cgyro_spectra_', dir=export_dir)
    exported_files = []
    failed_items = []

    for nr in ctx.get('nr_CGYRO', []):
        for para, para_values in _iter_selected_parameter_items(ctx, nr):
            for value in para_values:
                try:
                    ky, omega, gamma, omega_error, gamma_error, omega_standard_err, gamma_standard_err = collect_value_series(
                        root, ctx, nr, para, value
                    )
                    if len(ky) == 0:
                        continue
                    out_path = _export_linear_omega_gamma_vs_ky(
                        ctx, nr, para, value,
                        ky, omega, gamma,
                        omega_error, gamma_error,
                        omega_standard_err, gamma_standard_err,
                        export_dir
                    )
                    if out_path is not None:
                        exported_files.append(out_path)
                except Exception as e:
                    failed_items.append((nr, para, value, str(e)))

    runid = _safe_text_token(ctx.get('runid', 'unknown'))
    manifest_path = os.path.join(
        os.path.abspath(export_dir),
        f"omega_gamma_vs_ky_manifest__runid_{runid}.txt"
    )
    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write("# Exported omega/gamma vs ky files\n")
            for p in exported_files:
                f.write(f"{p}\n")
    except Exception as e:
        print(f"Warning: failed to write export manifest {manifest_path}: {e}")

    print(f"Export finished: {len(exported_files)} files written to {os.path.abspath(export_dir)}")
    if len(failed_items) > 0:
        print(f"Export warnings: {len(failed_items)} entries failed.")
        for nr, para, value, msg in failed_items[:20]:
            print(f"  - nr={nr}, para={para}, value={value}: {msg}")


def flatten_balloon_field(field_obj):
    """Flatten OMFIT balloon field objects into 1D numpy arrays."""
    try:
        arr = array(field_obj)
        if arr.ndim == 0 and hasattr(field_obj, 'T'):
            arr = array(field_obj.T[-1])
        if arr.ndim >= 2:
            arr = arr.T[-1]
        arr = array(getattr(arr, 'data', arr)).ravel()
        return arr
    except Exception:
        pass

    try:
        arr = field_obj.T[-1]
        arr = array(getattr(arr, 'data', arr)).ravel()
        return arr
    except Exception:
        return None


def interpolate_field(theta_target, theta_src, field_src):
    """Interpolate a complex/real field from source theta grid to target grid."""
    theta_src = array(theta_src).ravel()
    field_src = array(field_src).ravel()

    n = min(len(theta_src), len(field_src))
    if n <= 0:
        return None

    theta_src = theta_src[:n]
    field_src = field_src[:n]

    sort_idx = argsort(theta_src)
    theta_sorted = theta_src[sort_idx]
    field_sorted = field_src[sort_idx]

    theta_unique, unique_idx = unique(theta_sorted, return_index=True)
    field_unique = field_sorted[unique_idx]

    if len(theta_unique) == 0:
        return None
    if len(theta_unique) == 1:
        return ones(len(theta_target), dtype=complex) * field_unique[0]

    if iscomplexobj(field_unique):
        real_part = interp(theta_target, theta_unique, real(field_unique))
        imag_part = interp(theta_target, theta_unique, imag(field_unique))
        return real_part + 1j * imag_part
    return interp(theta_target, theta_unique, field_unique)


def build_uniform_theta_and_phi(balloon):
    """Extract theta/phi from balloon data and resample to a uniform theta grid."""
    theta_key = None
    if 'theta_b_over_pi' in balloon:
        theta_key = 'theta_b_over_pi'
    elif 'theta_over_pi' in balloon:
        theta_key = 'theta_over_pi'
    if theta_key is None:
        return None, None, None

    theta_obj = balloon[theta_key]
    theta_arr = array(theta_obj)
    if theta_arr.ndim == 0 and hasattr(theta_obj, 'T'):
        theta_arr = array(theta_obj.T[-1])
    if theta_arr.ndim >= 2:
        theta_arr = theta_arr.T[-1]
    theta_over_pi = array(getattr(theta_arr, 'data', theta_arr)).ravel()
    phi_raw = flatten_balloon_field(balloon['balloon_phi']) if 'balloon_phi' in balloon else None
    if phi_raw is None:
        return None, None, None

    theta_src = theta_over_pi * pi
    n = min(len(theta_src), len(phi_raw))
    if n <= 1:
        return None, None, None
    theta_src = theta_src[:n]
    phi_raw = phi_raw[:n]

    sort_idx = argsort(theta_src)
    theta_sorted = theta_src[sort_idx]
    theta_unique = unique(theta_sorted)
    if len(theta_unique) <= 1:
        return None, None, None

    theta_uniform = linspace(theta_unique[0], theta_unique[-1], len(theta_unique))
    phi_uniform = interpolate_field(theta_uniform, theta_src, phi_raw)
    return theta_src, theta_uniform, phi_uniform


def compute_freq_stats(datadir, ave_window):
    """Use the same finite-sample and fluctuation policy as linear spectra."""
    try:
        ind = max(2, int(datadir['n_time'] * ave_window))
        stats = _tail_frequency_stats(datadir['freq']['omega'][0][-ind:],
                                      datadir['freq']['gamma'][0][-ind:])
        if stats is None:
            return None
        return {'omega_mean': stats[0][0], 'gamma_mean': stats[1][0],
                'omega_rel_err': stats[0][2], 'gamma_rel_err': stats[1][2]}
    except (KeyError, TypeError, ValueError):
        return None


def extract_eigen_curve(datadir):
    """Build a normalized eigenfunction bundle (phi/epar/apar/bpar) from one run."""
    if 'balloon' not in datadir:
        return None

    balloon = datadir['balloon']
    theta_src, theta_b, phi_b = build_uniform_theta_and_phi(balloon)
    if theta_src is None or theta_b is None or phi_b is None:
        return None

    apar_b = zeros(len(theta_b), dtype=complex)
    has_apar = False
    if 'balloon_apar' in balloon:
        apar_raw = flatten_balloon_field(balloon['balloon_apar'])
        apar_tmp = interpolate_field(theta_b, theta_src, apar_raw) if apar_raw is not None else None
        if apar_tmp is not None:
            apar_b = apar_tmp
            has_apar = True

    bpar_b = zeros(len(theta_b), dtype=complex)
    has_bpar = False
    if 'balloon_bpar' in balloon:
        bpar_raw = flatten_balloon_field(balloon['balloon_bpar'])
        bpar_tmp = interpolate_field(theta_b, theta_src, bpar_raw) if bpar_raw is not None else None
        if bpar_tmp is not None:
            bpar_b = bpar_tmp
            has_bpar = True

    epar_b = None
    if 'balloon_epar' in balloon:
        epar_raw = flatten_balloon_field(balloon['balloon_epar'])
        if epar_raw is not None:
            epar_b = interpolate_field(theta_b, theta_src, epar_raw)

    if epar_b is None:
        dtheta = gradient(theta_b)
        with errstate(divide='ignore', invalid='ignore'):
            grad_phi = gradient(phi_b) / dtheta
            grad2_phi = gradient(grad_phi) / dtheta
        q0 = 1.0
        rmaj0 = 1.0
        if 'input.cgyro.gen' in datadir:
            inp = datadir['input.cgyro.gen']
            try:
                q0 = float(inp.get('Q', 1.0))
            except Exception:
                q0 = 1.0
            try:
                rmaj0 = float(inp.get('RMAJ', 1.0))
            except Exception:
                rmaj0 = 1.0
        fac = -1.0
        if q0 != 0 and rmaj0 != 0:
            fac = -1.0 / (q0 * rmaj0)
        epar_b = fac * grad2_phi

    if has_apar:
        try:
            omega_last = float(datadir['freq']['omega'][0][-1])
            gamma_last = float(datadir['freq']['gamma'][0][-1])
            omega_complex = complex(omega_last, gamma_last)
            epar_b = epar_b + 1j * omega_complex * apar_b
        except Exception:
            pass

    return {
        'theta_over_pi': theta_b / pi,
        'phi_b': phi_b,
        'epar_b': epar_b,
        'apar_b': apar_b,
        'bpar_b': bpar_b,
        'has_apar': has_apar,
        'has_bpar': has_bpar,
    }


def select_eigen_entries(entries, ctx):
    """
    Choose which ky entries are plotted in eigen-ball mode.

    Policy:
    - `single ky`: map each requested ky to nearest available ky.
    - otherwise: optionally apply error filter, then keep max-gamma entry.
    """
    if len(entries) == 0:
        return []

    if ctx['eigen_ky_mode'] == 'single ky' and len(ctx['selected_eigen_ky']) > 0:
        ky_available = array([item['ky'] for item in entries])
        selected_idx = []
        for ky_req in ctx['selected_eigen_ky']:
            nearest_idx = int(argmin(abs(ky_available - ky_req)))
            if nearest_idx not in selected_idx:
                selected_idx.append(nearest_idx)
        return [entries[i] for i in selected_idx]

    candidates = list(entries)
    if ctx.get('eigen_error_filter', False):
        tol = ctx.get('error_tolerance', 0.01)
        candidates = [
            item for item in entries
            if item.get('omega_rel_err', 1.0e30) <= tol and item.get('gamma_rel_err', 1.0e30) <= tol
        ]
    if len(candidates) == 0:
        return []

    gamma_vals = array([item['gamma_mean'] for item in candidates])
    max_idx = int(argmax(gamma_vals))
    return [candidates[max_idx]]


def collect_eigen_entries_for_value(root, ctx, nr, para, value):
    """
    Collect candidate ky entries for one scan value and compute metadata.

    Metadata includes mean gamma and omega/gamma relative errors, used by
    `select_eigen_entries` for filtering and max-gamma selection.
    """
    cgyrodir = _get_cgyro_lin_node(root, ctx, nr, para, value)
    if cgyrodir is None:
        return []

    entries = []
    for key in cgyrodir.keys():
        datadir = cgyrodir[key]
        if 'kyrhos' not in datadir:
            continue
        try:
            ky_val = float(datadir['kyrhos'])
        except Exception:
            continue
        ky_val = maybe_abs_ky(ky_val, ctx)

        freq_stats = compute_freq_stats(datadir, ctx['ave_window'])
        gamma_mean = -1.0e30
        omega_rel_err = 1.0e30
        gamma_rel_err = 1.0e30
        if freq_stats is not None:
            gamma_mean = freq_stats['gamma_mean']
            omega_rel_err = freq_stats['omega_rel_err']
            gamma_rel_err = freq_stats['gamma_rel_err']

        entries.append({
            'ky': ky_val,
            'gamma_mean': gamma_mean,
            'omega_rel_err': omega_rel_err,
            'gamma_rel_err': gamma_rel_err,
            'datadir': datadir,
        })

    entries = sorted(entries, key=lambda item: item['ky'])
    return select_eigen_entries(entries, ctx)


def plot_complex_field(ax, x, y, label_base, ctx):
    """Plot complex field as |.| or Re/Im according to eigen plotting options."""
    if ctx['eigen_abs']:
        ax.plot(x, abs(y), linewidth=ctx['lw'], label=f'{label_base}, |.|')
        return

    line_re, = ax.plot(x, real(y), linewidth=ctx['lw'], label=f'{label_base}, Re')
    ax.plot(
        x, imag(y), '--',
        linewidth=ctx['lw'],
        color=line_re.get_color(),
        label=f'{label_base}, Im'
    )


def plot_mode_eigen_ball_for_entry(ax, ctx, nr, para, value, ky_used, eigen_curve):
    """Draw one eigen curve entry into the 2x2 eigen-ball page."""
    if eigen_curve is None:
        return False, False

    style_2d_axes(ax, ctx['bwith'])
    x = eigen_curve['theta_over_pi']
    label_str = f'{_legend_nr_prefix(ctx, nr)}CGYRO_{para}={value}, ky={ky_used:.4g}'

    plot_complex_field(ax[0, 0], x, eigen_curve['phi_b'], label_str, ctx)
    plot_complex_field(ax[0, 1], x, eigen_curve['epar_b'], label_str, ctx)

    has_apar = eigen_curve.get('has_apar', False)
    if has_apar:
        plot_complex_field(ax[1, 0], x, eigen_curve['apar_b'], label_str, ctx)

    has_bpar = eigen_curve.get('has_bpar', False)
    if has_bpar:
        plot_complex_field(ax[1, 1], x, eigen_curve['bpar_b'], label_str, ctx)

    return has_apar, has_bpar


def finalize_eigen_ball_axes(ax, ctx, has_any_apar, has_any_bpar):
    """Finalize titles/legends/labels for eigen-ball page after all curves are drawn."""
    if ctx['eigen_abs']:
        t_phi = '|$\\phi$|'
        t_epar = '|$E_{||}$|'
        t_apar = '|$A_{||}$|'
        t_bpar = '|$B_{||}$|'
    else:
        t_phi = 'Re/Im($\\phi$)'
        t_epar = 'Re/Im($E_{||}$)'
        t_apar = 'Re/Im($A_{||}$)'
        t_bpar = 'Re/Im($B_{||}$)'

    ax[0, 0].set_title(t_phi, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[0, 1].set_title(t_epar, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[1, 0].set_title(t_apar, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[1, 1].set_title(t_bpar, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})

    ax[1, 0].set_xlabel('$\\theta(\\pi)$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[1, 1].set_xlabel('$\\theta(\\pi)$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})

    if not has_any_apar:
        ax[1, 0].text(0.5, 0.5, 'No A|| data', ha='center', va='center', transform=ax[1, 0].transAxes)
    if not has_any_bpar:
        ax[1, 1].text(0.5, 0.5, 'No B|| data', ha='center', va='center', transform=ax[1, 1].transAxes)

    for r in range(2):
        for c in range(2):
            ax[r, c].tick_params(labelsize=ctx['fs2'])
            if len(ax[r, c].lines) > 0:
                finalize_axis_legend(ax[r, c], ctx)

    # Re-apply one case-color mapping across all eigen-ball panels.  This is
    # intentionally after legend creation so Re/Im entries are synchronized.
    apply_color_order_to_axes(ax, ctx)


def _finalize_2d_page_legends(ax, ctx):
    """Finalize/reorder legends for currently populated 2x2 axes."""
    finalize_axis_legend(ax[0, 0], ctx)
    finalize_axis_legend(ax[1, 0], ctx)
    if ctx['error_flag'] == 'CGYRO':
        finalize_axis_legend(ax[0, 1], ctx)
        finalize_axis_legend(ax[1, 1], ctx)
    apply_color_order_to_axes(ax, ctx)


def plot_mode_2d_for_value(ax, ctx, nr, para, value, ky, omega, gamma, omega_error, gamma_error, omega_standard_err, gamma_standard_err):
    """Plot one scan value onto the standard 2x2 omega/gamma(+error) page."""
    if len(ky) == 0:
        return

    sort_idx = argsort(ky)
    ky = ky[sort_idx]
    omega = omega[sort_idx]
    gamma = gamma[sort_idx]
    omega_error = omega_error[sort_idx]
    gamma_error = gamma_error[sort_idx]

    y_omega, y_gamma, title_omega, title_gamma = apply_divide_by_ky(
        ky, omega, gamma, ctx['divide_by_ky'], ctx.get('divide_by_ky2', False)
    )

    label_str = f'{_legend_nr_prefix(ctx, nr)}CGYRO_{para}={value}'
    style_2d_axes(ax, ctx['bwith'])

    ax[0, 0].set_title(title_omega, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[0, 0].plot(ky, y_omega, label=label_str, linewidth=ctx['lw'])

    if ctx['plot_log_x']:
        ax[0, 0].set_xscale('log')
    if ctx['plot_log_y']:
        ax[0, 0].set_yscale('log')
        ax[1, 0].set_yscale('log')


    if ctx['error_flag'] == 'CGYRO':
        ax[0, 1].set_title('Relative time fluctuation', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
        ax[0, 1].plot(ky, omega_error, linewidth=ctx['lw'], label=label_str)
        ax[1, 1].set_title('Relative time fluctuation', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
        ax[1, 1].plot(ky, gamma_error, linewidth=ctx['lw'], label=label_str)

    ax[1, 0].set_title(title_gamma, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax[1, 0].plot(ky, y_gamma, label=label_str, linewidth=ctx['lw'])
    ax[1, 0].set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)
    ax[1, 1].set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}, labelpad=5)

    if ctx['highlight_max_gamma']:
        max_gamma_idx = argmax(y_gamma)
        x_val = ky[max_gamma_idx]
        y_val = y_gamma[max_gamma_idx]
        ax[1, 0].plot(x_val, y_val, 'ro', markersize=ctx['ms']*1.5)
        txt = ax[1, 0].annotate(
            f'({x_val:.3f}, {y_val:.3f})',
            xy=(x_val, y_val)
        )
        _finalize_2d_page_legends(ax, ctx)
        return ax, txt
    else:
        _finalize_2d_page_legends(ax, ctx)
        return ax, None


def build_param_cloud(root, ctx, nr, para, para_values):
    """Convert one parameter scan into point cloud data for 3D/single-ky modes."""
    all_ky = []
    all_param_vals = []
    all_omega = []
    all_gamma = []

    for value in para_values:
        ky, omega, gamma, _, _, _, _ = collect_value_series(root, ctx, nr, para, value)
        if len(ky) == 0:
            continue

        y_omega, y_gamma, _, _ = apply_divide_by_ky(
            ky, omega, gamma, ctx['divide_by_ky'], ctx.get('divide_by_ky2', False)
        )

        for idx in range(len(ky)):
            all_ky.append(float(ky[idx]))
            all_param_vals.append(float(value))
            all_omega.append(float(y_omega[idx]))
            all_gamma.append(float(y_gamma[idx]))

    return (
        array(all_ky).ravel(),
        array(all_param_vals).ravel(),
        array(all_omega).ravel(),
        array(all_gamma).ravel()
    )


def filter_single_ky(unique_ky, selected_single_ky):
    """Map requested ky values to nearest available ky points in the scan."""
    if len(selected_single_ky) == 0:
        return unique_ky
    filtered = []
    for ky_req in selected_single_ky:
        if len(unique_ky) > 0:
            nearest_idx = argmin(abs(unique_ky - ky_req))
            filtered.append(float(unique_ky[nearest_idx]))
    return array(sorted(list(set(filtered))))


def plot_mode_single_ky(ax_omega, ax_gamma, ctx, nr, para, all_ky, all_param_vals, all_omega, all_gamma):
    """Plot parameter value vs omega/gamma for selected ky slices."""
    if len(all_ky) == 0:
        return

    unique_ky = unique(all_ky)
    unique_ky = filter_single_ky(unique_ky, ctx['selected_single_ky'])

    for ky_val in unique_ky:
        mask = (abs(all_ky - ky_val) < 1e-10).ravel()
        param_vals_for_ky = unique(all_param_vals[mask])
        sort_idx_param = argsort(param_vals_for_ky)
        param_vals_for_ky = param_vals_for_ky[sort_idx_param]

        omega_for_ky = []
        gamma_for_ky = []

        for p_val in param_vals_for_ky:
            p_mask = mask & (abs(all_param_vals - p_val) < 1e-10)
            if sum(p_mask) > 0:
                omega_for_ky.append(mean(all_omega[p_mask]))
                gamma_for_ky.append(mean(all_gamma[p_mask]))

        omega_for_ky = array(omega_for_ky)
        gamma_for_ky = array(gamma_for_ky)

        label_str = f'{_legend_nr_prefix(ctx, nr)}{para}, ky={ky_val:.3f}'
        ax_omega.plot(param_vals_for_ky, omega_for_ky, 'o-', label=label_str, linewidth=ctx['lw'], markersize=ctx['ms'])
        ax_gamma.plot(param_vals_for_ky, gamma_for_ky, 's-', label=label_str, linewidth=ctx['lw'], markersize=ctx['ms'])

    ax_omega.set_xlabel('parameter value', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    omega_title = divide_title(ctx, 'omega')
    gamma_title = divide_title(ctx, 'gamma')
    ax_omega.set_ylabel(omega_title, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax_omega.set_title(
        f'{omega_title} vs parameter ({_nr_title_text(ctx, nr)})',
        fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}
    )
    finalize_axis_legend(ax_omega, ctx)
    ax_omega.grid(True, alpha=0.3)

    ax_gamma.set_xlabel('parameter value', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax_gamma.set_ylabel(gamma_title, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax_gamma.set_title(
        f'{gamma_title} vs parameter ({_nr_title_text(ctx, nr)})',
        fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}
    )
    finalize_axis_legend(ax_gamma, ctx)
    apply_color_order_to_axes([ax_omega, ax_gamma], ctx)
    ax_gamma.grid(True, alpha=0.3)

    for ax_curr in [ax_omega, ax_gamma]:
        ax_curr.tick_params(labelsize=ctx['fs2'])
        for spine in ax_curr.spines.values():
            spine.set_linewidth(ctx['bwith'])


def plot_mode_3d(ax_omega, ax_gamma, fig, ctx, nr, para, all_ky, all_param_vals, all_omega, all_gamma):
    """Plot 3D surfaces: x=ky, y=parameter value, z=omega/gamma."""
    if len(all_ky) == 0:
        return

    unique_ky = unique(all_ky)
    unique_param = unique(all_param_vals)

    ky_grid = tile(unique_ky, (len(unique_param), 1))
    param_grid = tile(unique_param.reshape(-1, 1), (1, len(unique_ky)))

    omega_grid = full((len(unique_param), len(unique_ky)), nan)
    gamma_grid = full((len(unique_param), len(unique_ky)), nan)

    for p_idx, p_val in enumerate(unique_param):
        for k_idx, k_val in enumerate(unique_ky):
            mask = ((abs(all_param_vals - p_val) < 1e-10) & (abs(all_ky - k_val) < 1e-10)).ravel()
            if sum(mask) > 0:
                omega_grid[p_idx, k_idx] = mean(all_omega[mask])
                gamma_grid[p_idx, k_idx] = mean(all_gamma[mask])

    surf_omega = ax_omega.plot_surface(ky_grid, param_grid, omega_grid, cmap='viridis', alpha=0.8)
    surf_gamma = ax_gamma.plot_surface(ky_grid, param_grid, gamma_grid, cmap='plasma', alpha=0.8)

    ax_omega.set_xlabel('ky', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs2']})
    ax_omega.set_ylabel(para, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs2']})
    omega_title = divide_title(ctx, 'omega')
    gamma_title = divide_title(ctx, 'gamma')
    ax_omega.set_zlabel(omega_title, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs2']})
    ax_omega.set_title(f'{omega_title} vs {para} ({nr})', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})

    ax_gamma.set_xlabel('ky', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs2']})
    ax_gamma.set_ylabel(para, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs2']})
    ax_gamma.set_zlabel(gamma_title, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs2']})
    ax_gamma.set_title(f'{gamma_title} vs {para} ({nr})', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})

    if ctx.get('plot_log_x', False):
        if len(unique_ky) > 0 and all(unique_ky > 0):
            ax_omega.set_xscale('log')
            ax_gamma.set_xscale('log')

    if ctx.get('plot_log_y', False):
        if len(unique_param) > 0 and all(unique_param > 0):
            ax_omega.set_yscale('log')
            ax_gamma.set_yscale('log')

    if ctx.get('plot_log_z', False):
        omega_valid = omega_grid[isfinite(omega_grid)]
        gamma_valid = gamma_grid[isfinite(gamma_grid)]
        if len(omega_valid) > 0 and all(omega_valid > 0):
            ax_omega.set_zscale('log')
        if len(gamma_valid) > 0 and all(gamma_valid > 0):
            ax_gamma.set_zscale('log')

    fig.colorbar(surf_omega, ax=ax_omega, shrink=0.5, aspect=5)
    fig.colorbar(surf_gamma, ax=ax_gamma, shrink=0.5, aspect=5)


def parse_gamma_ref_ky_values(ctx):
    """Parse optional reference ky list used by gamma-ratio mode."""
    return maybe_abs_ky_list(parse_float_list_text(ctx.get('gamma_ref_ky_values', '')), ctx)


def get_gamma_ratio_curve(root, ctx, nr, para, para_values):
    """
    Build gamma/gamma_ref curve for one scanned parameter.

    - x-axis: parameter value
    - y-axis: representative gamma normalized by reference gamma
    - reference value is snapped to nearest available parameter value
    """
    try:
        ref_value = float(ctx['gamma_ref_value'])
    except Exception:
        return None

    gamma_map = {}
    ref_ky_targets = parse_gamma_ref_ky_values(ctx)

    for value in para_values:
        ky, omega, gamma, _, _, _, _ = collect_value_series(root, ctx, nr, para, value)
        if len(gamma) == 0:
            continue

        # Gamma ratios always use gamma, independently of spectrum display options.
        y_gamma = gamma

        if ctx['gamma_ref_mode'] == 'single ky':
            if len(ref_ky_targets) == 0:
                continue
            ky_used = []
            gamma_used = []
            for ky_req in ref_ky_targets:
                nearest_idx = argmin(abs(ky - ky_req))
                ky_used.append(float(ky[nearest_idx]))
                gamma_used.append(float(y_gamma[nearest_idx]))
            if len(gamma_used) > 0:
                gamma_map[float(value)] = mean(array(gamma_used))
        else:
            gamma_map[float(value)] = nanmax(y_gamma)

    if len(gamma_map) == 0:
        return None

    ref_candidates = array(list(gamma_map.keys()))
    ref_idx = argmin(abs(ref_candidates - ref_value))
    ref_value_used = float(ref_candidates[ref_idx])
    gamma_ref = gamma_map[ref_value_used]

    if gamma_ref == 0:
        return None

    x_vals = array(sorted(gamma_map.keys()))
    y_vals = array([gamma_map[x] / gamma_ref for x in x_vals])
    return x_vals, y_vals, ref_value_used


def plot_mode_gamma_ratio(ax0, ctx, nr, para, x_vals, y_vals, ref_value_used):
    """Render one gamma-ratio curve on the dedicated gamma-ratio page."""
    label_prefix = _legend_nr_prefix(ctx, nr)
    ax0.plot(x_vals, y_vals, 'o-', linewidth=ctx['lw'], markersize=ctx['ms'],
             label=f'{label_prefix}{para}, ref={ref_value_used}')
    ax0.set_xlabel(para, fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax0.set_ylabel('$gamma$/$gamma_ref$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
    ax0.set_title(
        f'Plot $gamma$/$gamma_ref$ ({_nr_title_text(ctx, nr)})',
        fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']}
    )
    ax0.grid(True, alpha=0.3)
    finalize_axis_legend(ax0, ctx)
    apply_color_order_to_axes(ax0, ctx)
    ax0.tick_params(labelsize=ctx['fs2'])
    for spine in ax0.spines.values():
        spine.set_linewidth(ctx['bwith'])


def _is_standard_2d_mode(ctx):
    """True for default 2x2 omega/gamma(+error) plotting mode."""
    return (
        (not ctx['plot_3d'])
        and (not ctx['single_ky'])
        and (not ctx['plot_gamma_ratio'])
        and (not ctx['plot_eigen_ball'])
    )


def _build_nr_pages(fn, ctx, nr):
    """
    Create all figure pages needed for one selected `nr`.

    Returns a dictionary holding page-local axes handles.
    Keys are created even when page is disabled; disabled pages keep `None`.
    """
    pages = {
        'ax_2d': None,
        'single_axes': None,
        'gamma_ratio_ax': None,
        'eigen_axes': None,
    }

    if _is_standard_2d_mode(ctx):
        fig2d, ax_2d = fn.subplots(
            nrows=2, ncols=2, figsize=DEFAULT_FIGSIZE_2X2,
            label=nr, sharex=True, sharey=False, squeeze=False
        )
        apply_figure_layout(fig2d, ctx)
        pages['ax_2d'] = ax_2d

    if ctx['single_ky']:
        fig_single, ax_tmp = fn.subplots(
            nrows=1, ncols=2, figsize=DEFAULT_FIGSIZE_1X2, label=f'{nr}_single_ky', squeeze=False
        )
        apply_figure_layout(fig_single, ctx)
        pages['single_axes'] = (ax_tmp[0, 0], ax_tmp[0, 1])

    if ctx['plot_gamma_ratio']:
        fig_gamma_ratio, ax_tmp = fn.subplots(
            nrows=1, ncols=1, figsize=DEFAULT_FIGSIZE_GAMMA_RATIO, label=f'{nr}_gamma_ratio', squeeze=False
        )
        apply_figure_layout(fig_gamma_ratio, ctx)
        pages['gamma_ratio_ax'] = ax_tmp[0, 0]

    if ctx['plot_eigen_ball']:
        fig_eigen, ax_tmp = fn.subplots(
            nrows=2, ncols=2, figsize=DEFAULT_FIGSIZE_EIGEN, label=f'{nr}_eigen_ball',
            sharex=True, sharey=False, squeeze=False
        )
        apply_figure_layout(fig_eigen, ctx)
        pages['eigen_axes'] = ax_tmp

    return pages


def _plot_parameter_in_2d_page(root, ctx, nr, para, para_values, ax_2d):
    """
    Render all selected values of one parameter onto one standard 2x2 page.

    Max-gamma labels are adjusted after all values of this parameter are drawn.
    """
    texts_to_adjust = []
    ax_last = ax_2d

    for value in para_values:
        ky, omega, gamma, omega_error, gamma_error, omega_standard_err, gamma_standard_err = collect_value_series(
            root, ctx, nr, para, value
        )
        if len(ky) == 0:
            continue
        ax_last, txt = plot_mode_2d_for_value(
            ax_2d, ctx, nr, para, value, ky, omega, gamma,
            omega_error, gamma_error, omega_standard_err, gamma_standard_err
        )
        if txt is not None:
            texts_to_adjust.append(txt)

    if len(texts_to_adjust) > 0 and ax_last is not None:
        _adjust_labels(
            texts_to_adjust,
            ax=ax_last[1, 0],
            only_move={'text': 'y'},
            arrowprops=dict(arrowstyle='->', color='red', lw=1.5),
        )


def _plot_parameter_in_eigen_page(root, ctx, nr, para, para_values, eigen_axes):
    """
    Plot eigen-ball curves for one parameter.

    Returns two booleans: (has_any_apar, has_any_bpar) within this parameter.
    """
    has_any_apar = False
    has_any_bpar = False

    for value in para_values:
        eigen_entries = collect_eigen_entries_for_value(root, ctx, nr, para, value)
        for entry in eigen_entries:
            eigen_curve = extract_eigen_curve(entry['datadir'])
            has_apar, has_bpar = plot_mode_eigen_ball_for_entry(
                eigen_axes, ctx, nr, para, value, entry['ky'], eigen_curve
            )
            has_any_apar = has_any_apar or has_apar
            has_any_bpar = has_any_bpar or has_bpar

    return has_any_apar, has_any_bpar


def _plot_parameter_in_cloud_modes(root, ctx, nr, para, para_values, single_axes):
    """Handle single-ky and 3D plotting modes for one parameter."""
    all_ky, all_param_vals, all_omega, all_gamma = build_param_cloud(root, ctx, nr, para, para_values)

    if ctx['single_ky']:
        ax_omega, ax_gamma = single_axes
        plot_mode_single_ky(ax_omega, ax_gamma, ctx, nr, para, all_ky, all_param_vals, all_omega, all_gamma)
        return

    if ctx['plot_3d']:
        fig = plt.figure(label=f'{nr}_{para}_3D', figsize=DEFAULT_FIGSIZE_3D)
        apply_figure_layout(fig, ctx)
        ax_omega = fig.add_subplot(1, 2, 1, projection='3d')
        ax_gamma = fig.add_subplot(1, 2, 2, projection='3d')
        plot_mode_3d(ax_omega, ax_gamma, fig, ctx, nr, para, all_ky, all_param_vals, all_omega, all_gamma)


def _iter_selected_parameter_items(ctx, nr=None):
    """
    Yield `(para, para_values)` pairs that have at least one selected value.

    When available, per-nr selections (`selected_paras_by_nr`) take precedence.
    """
    def _normalize_selected_values(values):
        """Normalize GUI-stored selected values into a flat non-empty list."""
        if values is None:
            return []

        if isinstance(values, str):
            values = _parse_gui_value_text(values)

        if hasattr(values, '__iter__'):
            raw = list(values)
        else:
            raw = [values]

        out = []
        for item in raw:
            if item is None:
                continue
            if isinstance(item, str):
                item_s = item.strip()
                if len(item_s) == 0:
                    continue
                parsed = _parse_gui_value_text(item_s)
                if len(parsed) > 0 and (
                    len(parsed) > 1 or item_s.startswith('[') or item_s.startswith('(')
                ):
                    for parsed_item in parsed:
                        try:
                            out.append(float(parsed_item))
                        except Exception:
                            out.append(parsed_item)
                    continue
                try:
                    out.append(float(item_s))
                except Exception:
                    out.append(item_s)
                continue
            try:
                out.append(float(item))
            except Exception:
                out.append(item)
        return out

    selected_map = ctx.get('selected_paras', {})
    if nr is not None:
        selected_by_nr = ctx.get('selected_paras_by_nr', {})
        if hasattr(selected_by_nr, 'get'):
            selected_per_nr = selected_by_nr.get(str(nr), None)
            if hasattr(selected_per_nr, 'keys'):
                selected_map = selected_per_nr

    if not hasattr(selected_map, 'keys'):
        return

    for para in selected_map:
        para_values = _normalize_selected_values(selected_map[para])
        if len(para_values) == 0:
            continue
        yield para, para_values


def _has_any_selected_parameters(ctx):
    """True when at least one `(nr, para, values)` selection is non-empty."""
    for nr in ctx.get('nr_CGYRO', []):
        for _para, _para_values in _iter_selected_parameter_items(ctx, nr):
            return True
    for _para, _para_values in _iter_selected_parameter_items(ctx):
        return True
    return False


def _plot_gamma_ratio_page_for_nr(root, ctx, nr, pages):
    """Render one gamma-ratio page for current `nr`."""
    ax0 = pages.get('gamma_ratio_ax', None)
    if ax0 is None:
        return

    for para, para_values in _iter_selected_parameter_items(ctx, nr):
        result = get_gamma_ratio_curve(root, ctx, nr, para, para_values)
        if result is None:
            continue
        x_vals, y_vals, ref_value_used = result
        plot_mode_gamma_ratio(ax0, ctx, nr, para, x_vals, y_vals, ref_value_used)


def _plot_eigen_ball_page_for_nr(root, ctx, nr, pages):
    """Render one eigen-ball page for current `nr` and finalize axes state."""
    eigen_axes = pages.get('eigen_axes', None)
    if eigen_axes is None:
        return

    has_any_apar = False
    has_any_bpar = False
    for para, para_values in _iter_selected_parameter_items(ctx, nr):
        has_apar, has_bpar = _plot_parameter_in_eigen_page(
            root, ctx, nr, para, para_values, eigen_axes
        )
        has_any_apar = has_any_apar or has_apar
        has_any_bpar = has_any_bpar or has_bpar

    finalize_eigen_ball_axes(eigen_axes, ctx, has_any_apar, has_any_bpar)


def _plot_eigen_ball_page_for_all_nr(root, ctx, nr_list, pages):
    """Render one shared eigen-ball page for all selected nr and finalize once."""
    eigen_axes = pages.get('eigen_axes', None)
    if eigen_axes is None:
        return

    has_any_apar = False
    has_any_bpar = False
    for nr in nr_list:
        for para, para_values in _iter_selected_parameter_items(ctx, nr):
            has_apar, has_bpar = _plot_parameter_in_eigen_page(
                root, ctx, nr, para, para_values, eigen_axes
            )
            has_any_apar = has_any_apar or has_apar
            has_any_bpar = has_any_bpar or has_bpar

    finalize_eigen_ball_axes(eigen_axes, ctx, has_any_apar, has_any_bpar)


def _plot_standard_2d_page_for_nr(root, ctx, nr, pages):
    """Render one standard 2x2 omega/gamma page for current `nr`."""
    ax_2d = pages.get('ax_2d', None)
    if ax_2d is None:
        return

    for para, para_values in _iter_selected_parameter_items(ctx, nr):
        _plot_parameter_in_2d_page(root, ctx, nr, para, para_values, ax_2d)


def _plot_cloud_pages_for_nr(root, ctx, nr, pages):
    """Render single-ky or 3D pages for current `nr` (one 3D figure per parameter)."""
    single_axes = pages.get('single_axes', None)
    for para, para_values in _iter_selected_parameter_items(ctx, nr):
        _plot_parameter_in_cloud_modes(root, ctx, nr, para, para_values, single_axes)


def _plot_nr_pages_by_mode(root, ctx, nr, pages):
    """Dispatch one `nr` to exactly one active page-rendering path."""
    if ctx['plot_gamma_ratio']:
        _plot_gamma_ratio_page_for_nr(root, ctx, nr, pages)
        return

    if ctx['plot_eigen_ball']:
        _plot_eigen_ball_page_for_nr(root, ctx, nr, pages)
        return

    if _is_standard_2d_mode(ctx):
        _plot_standard_2d_page_for_nr(root, ctx, nr, pages)
        return

    _plot_cloud_pages_for_nr(root, ctx, nr, pages)


def run_plot(root):
    """
    Main entry point called by OMFIT plot action.

    Flow:
    1) Build runtime context.
    2) Create per-`nr` pages.
    3) Dispatch each `nr` to one active plotting mode.
    """
    report = selection_check(root)
    if report['errors']:
        raise ValueError('\n'.join(report['errors']))
    ctx = build_context(root)
    if not ctx['plotcgyro']:
        return
    if ctx.get('export_linear_now', False):
        export_selected_linear_spectra(root, ctx)
        return

    fn = FigureNotebook(0, 'CGYRO_Spectra_Comparison')
    if not _has_any_selected_parameters(ctx):
        return

    if _combine_nr_on_single_page(ctx):
        pages = _build_nr_pages(fn, ctx, 'ALL_NR')
        if ctx['plot_eigen_ball']:
            _plot_eigen_ball_page_for_all_nr(root, ctx, ctx['nr_CGYRO'], pages)
        else:
            for nr in ctx['nr_CGYRO']:
                _plot_nr_pages_by_mode(root, ctx, nr, pages)
        return

    for nr in ctx['nr_CGYRO']:
        pages = _build_nr_pages(fn, ctx, nr)
        _plot_nr_pages_by_mode(root, ctx, nr, pages)


def _adjust_labels(*args, **kwargs):
    """Optional annotation adjustment must not prevent ordinary spectra from plotting."""
    try:
        from adjustText import adjust_text
    except ImportError:
        warnings.warn('adjustText is unavailable; peak labels keep their default positions.', RuntimeWarning)
        return
    return adjust_text(*args, **kwargs)
