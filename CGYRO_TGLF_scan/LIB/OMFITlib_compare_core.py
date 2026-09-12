"""CGYRO/TGLF comparison: core.

Extracted from the reviewed project; data is read from the supplied OMFIT tree.
"""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    TypeError,
    ValueError,
    abs,
    all,
    bool,
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
    range,
    set,
    sorted,
    str,
    tuple,
)

import numpy as np
import re
from OMFITlib_compare_state import (
    STYLE_DEFAULTS,
)
from numpy import (
    allclose,
    array,
    interp,
    linspace,
    log10,
    sqrt,
    unique,
    zeros,
)


def resolve_key(mapping, key):
    """Exact, textual, then unambiguous numeric key lookup (no nearest match)."""
    try:
        if key in mapping:
            return key
    except TypeError:
        return None
    matches = [k for k in mapping.keys() if str(k) == str(key)]
    if len(matches) == 1:
        return matches[0]
    try:
        target = float(key)
    except (TypeError, ValueError):
        return None
    numeric = []
    for candidate in mapping.keys():
        try:
            if np.isfinite(target) and float(candidate) == target:
                numeric.append(candidate)
        except (TypeError, ValueError):
            continue
    if len(numeric) > 1:
        raise ValueError('Ambiguous numeric scan key: {!r}'.format(key))
    return numeric[0] if numeric else None


def normalize_flux_species_option(value):
    """Normalize GUI flux-species option into canonical labels."""
    sval = str(value).strip().lower()
    if sval in ['electron only', 'electron', 'e', 'elec']:
        return 'Electron only'
    if sval in ['ion only', 'ions only', 'ion', 'ions']:
        return 'Ion only'
    return 'Both'


def is_gamma_ratio_plot_mode(plot_mode):
    """True when selected plot mode is gamma-ratio mode (with legacy label support)."""
    mode_txt = str(plot_mode).strip()
    return mode_txt in ('Plot γ/γ_ref', 'Plot 纬/纬_ref')


def build_context(root):
    """Collect all plotting settings into a compact runtime context dict."""
    settings = root['SETTINGS']['PHYSICS']
    compare_mode = settings.get('compare_mode', 'CGYRO_vs_TGLF')
    mode_state = settings.get(compare_mode, {})

    ctx = {}
    ctx['compare_mode'] = compare_mode
    ctx['mode_state'] = mode_state

    ctx['cgyro_state'] = mode_state.get('CGYRO', {})
    ctx['tglf_state'] = mode_state.get('TGLF', {})
    ctx['plot_state'] = mode_state.get('plot', {})
    ctx['check_cgyro_output_now'] = bool(mode_state.get('check_cgyro_output_now', False))

    plot_state = mode_state if compare_mode == 'CGYRO_vs_CGYRO' else ctx['plot_state']
    ctx['ave_window'] = float(plot_state.get('ave_window', 0.02))
    ctx['effnum'] = plot_state.get('effnum', 5)
    ctx['plot_mode'] = plot_state.get('plot_mode', 'Plot 2D')
    ctx['plot_gamma_ratio'] = is_gamma_ratio_plot_mode(ctx['plot_mode'])
    ctx['error_flag'] = plot_state.get('error_flag', 'CGYRO')
    ctx['plot_log_x'] = plot_state.get('plot_log_x', False)
    ctx['plot_log_y'] = plot_state.get('plot_log_y', False)
    ctx['abs_ky'] = bool(plot_state.get('abs_ky', settings.get('abs_ky', False)))
    ctx['normalize_main_ion'] = plot_state.get(
        'normalize_main_ion', settings.get('normalize_main_ion', False)
    )
    ctx['divide_by_ky'] = plot_state.get('divide_by_ky', settings.get('divide_by_ky', True))
    ctx['divide_by_ky2'] = plot_state.get('divide_by_ky2', settings.get('divide_by_ky2', False))
    ctx['gamma_ref_mode'] = plot_state.get('gamma_ref_mode', 'all ky')
    ctx['gamma_ref_value'] = plot_state.get('gamma_ref_value', '')
    ctx['gamma_ref_ky_values'] = plot_state.get('gamma_ref_ky_values', '')
    ctx['gamma_ref_split_panels'] = bool(plot_state.get('gamma_ref_split_panels', False))
    ctx['gamma_ref_tglf2d_x_axis'] = plot_state.get('gamma_ref_tglf2d_x_axis', 'para1')
    ctx['gamma_ref_ky_min'] = plot_state.get('gamma_ref_ky_min', '')
    ctx['gamma_ref_ky_max'] = plot_state.get('gamma_ref_ky_max', '')
    ctx['gamma_ref_error_filter'] = bool(plot_state.get('gamma_ref_error_filter', False))
    ctx['tglf_vs_tglf_mode'] = plot_state.get('tglf_vs_tglf_mode', 'Spectra')
    old_ion_mode = plot_state.get('tglf_flux_ion_mode', None)
    flux_species = normalize_flux_species_option(plot_state.get('tglf_flux_species', 'Both'))
    if 'tglf_flux_merge_ions' in plot_state:
        flux_merge_ions = bool(plot_state.get('tglf_flux_merge_ions', True))
    elif old_ion_mode is not None:
        flux_merge_ions = (old_ion_mode != 'Split ions')
    else:
        flux_merge_ions = True
    ctx['tglf_flux_species'] = flux_species
    ctx['tglf_flux_merge_ions'] = flux_merge_ions
    # Legacy compatibility for code paths still using the old string mode.
    ctx['tglf_flux_ion_mode'] = 'Merge ions' if flux_merge_ions else 'Split ions'
    ctx['tglf2d_plot_mode'] = plot_state.get('tglf2d_plot_mode', '2D')
    ctx['tglf2d_x_axis'] = plot_state.get('tglf2d_x_axis', 'para1')
    ctx['highlight_max_gamma'] = settings.get('highlight_max_gamma', False)
    ctx['legend_order_mode'] = mode_state.get(
        'legend_order_mode',
        plot_state.get('legend_order_mode', 'Plot order')
    )
    ctx['legend_order_text'] = mode_state.get(
        'legend_order_text',
        plot_state.get('legend_order_text', '')
    )
    try:
        ctx['error_tolerance'] = float(plot_state.get('error_tolerance', 0.01))
    except Exception:
        ctx['error_tolerance'] = 0.01
    if ctx['error_tolerance'] <= 0:
        ctx['error_tolerance'] = 0.01

    ctx['comparison_layout'] = plot_state.get('comparison_layout', 'Overlay')
    ctx['show_flux_spectra'] = plot_state.get('show_flux_spectra', True)
    ctx['style'] = dict(STYLE_DEFAULTS, **mode_state.get('style', {}))
    ctx['_diagnostics'] = []

    # Plot style defaults
    ctx['ms'] = 8
    ctx['lw'] = float(ctx['style']['line_width'])
    ctx['fs1'] = float(ctx['style']['font_size'])
    ctx['fs2'] = float(ctx['style']['legend_font_size'])
    ctx['fs3'] = float(ctx['style']['font_size'])
    ctx['bwith'] = 1.5

    return ctx


def _tail_frequency_stats(omega_samples, gamma_samples):
    """Population std and relative fluctuation; invalid samples reject this run.

    A nonzero fluctuation about a numerically zero mean has infinite relative
    error. Exactly constant zero samples have zero fluctuation. No display floor
    or clipping is applied to values exported or used in comparisons.
    """
    omega = np.asarray(omega_samples, dtype=float).ravel()
    gamma = np.asarray(gamma_samples, dtype=float).ravel()
    if (omega.size == 0 or gamma.size == 0 or omega.size != gamma.size
            or not np.all(np.isfinite(omega)) or not np.all(np.isfinite(gamma))):
        return None
    result = []
    for values in (omega, gamma):
        avg = float(np.mean(values))
        spread = float(np.std(values))
        near_zero = abs(avg) <= np.finfo(float).eps * max(1.0, float(np.max(np.abs(values))))
        relative = (0.0 if spread == 0 else float('inf')) if near_zero else spread / abs(avg)
        result.append((avg, spread, relative))
    return result


def normalize_if_needed(datadir, ky_val, omega_val, gamma_val, normalize_main_ion):
    """
    Apply main-ion normalization to ky / omega / gamma when requested.

    omega/ky and gamma/ky are computed after this step using normalized ky.

    Formula follows CGYRO_vs_CGYRO implementation for consistency.
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


def _get_mapping_item(mapping, key):
    """Robust key lookup for OMFIT-like mapping objects."""
    if not hasattr(mapping, 'keys'):
        return None
    try:
        k_resolved = resolve_key(mapping, key)
        if k_resolved is not None:
            return mapping[k_resolved]
    except Exception:
        pass
    try:
        return mapping[key]
    except Exception:
        return None


def _to_float_scalar(value):
    """Convert scalar-like object to float when possible."""
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        pass
    try:
        arr = array(getattr(value, 'values', value)).ravel()
        if len(arr) == 0:
            return None
        return float(arr[0])
    except Exception:
        return None


def _maybe_abs_ky(ky, ctx=None):
    """Return ky or |ky| according to the shared plot option."""
    if ctx is None or not ctx.get('abs_ky', False):
        return ky
    try:
        return abs(array(ky, dtype=float))
    except Exception:
        try:
            return abs(float(ky))
        except Exception:
            return ky


def _read_tglf_main_ion(inp):
    """
    Determine TGLF main ion from input.tglf-like mapping.

    Rule: among ions (ZS_i > 0), pick the species with largest AS_i.
    """
    if inp is None or not hasattr(inp, 'keys'):
        return None, None

    ns = _to_float_scalar(_get_mapping_item(inp, 'NS'))
    if ns is None:
        ns = _to_float_scalar(_get_mapping_item(inp, 'N_SPECIES'))

    if ns is None:
        ns_guess = 0
        for k in list(inp.keys()):
            mk = re.match(r'^(?:AS|ZS|MASS)_(\d+)$', str(k))
            if mk is None:
                continue
            try:
                ns_guess = max(ns_guess, int(mk.group(1)))
            except Exception:
                continue
        ns = ns_guess

    try:
        ns = int(ns)
    except Exception:
        ns = 0
    if ns <= 0:
        return None, None

    best_idx = None
    best_as = -1.0
    fallback_idx = None
    for i in range(1, ns + 1):
        z_i = _to_float_scalar(_get_mapping_item(inp, f'ZS_{i}'))
        m_i = _to_float_scalar(_get_mapping_item(inp, f'MASS_{i}'))
        a_i = _to_float_scalar(_get_mapping_item(inp, f'AS_{i}'))

        if z_i is None or m_i is None:
            continue
        if z_i <= 0 or m_i <= 0:
            continue

        if fallback_idx is None:
            fallback_idx = i

        a_eff = a_i if a_i is not None else -1.0
        if a_eff > best_as:
            best_as = a_eff
            best_idx = i

    if best_idx is None:
        best_idx = fallback_idx
    if best_idx is None:
        return None, None

    z_main = _to_float_scalar(_get_mapping_item(inp, f'ZS_{best_idx}'))
    mass_main = _to_float_scalar(_get_mapping_item(inp, f'MASS_{best_idx}'))
    if z_main is None or mass_main is None or mass_main <= 0:
        return None, None
    return z_main, mass_main


def _get_tglf_input_for_node(tglf_node, root=None, rho=None):
    """
    Get input.tglf-like mapping from one TGLF result node.
    Priority: node-local input files, then root['input.tglf'][rho].
    """
    candidate_keys = ['input.tglf.gen', 'input.tglf', 'out.tglf.localdump', 'out.tglf.globaldump']
    if hasattr(tglf_node, 'keys'):
        for k in candidate_keys:
            inp = _get_mapping_item(tglf_node, k)
            if inp is not None and hasattr(inp, 'keys'):
                return inp

    if root is not None and rho is not None:
        try:
            inp_all = root.get('input.tglf', None)
        except Exception:
            inp_all = None
        if inp_all is not None and hasattr(inp_all, 'keys'):
            rho_key = resolve_key(inp_all, rho)
            if rho_key is not None:
                inp = inp_all[rho_key]
                if hasattr(inp, 'keys'):
                    return inp
    return None


def normalize_tglf_if_needed(tglf_node, ky, omega, gamma, normalize_main_ion, root=None, rho=None):
    """
    Apply main-ion normalization to TGLF ky / omega / gamma when requested.
    """
    if not normalize_main_ion:
        return ky, omega, gamma

    inp = _get_tglf_input_for_node(tglf_node, root=root, rho=rho)
    z_main, mass_main = _read_tglf_main_ion(inp)
    if z_main is None or mass_main is None:
        return ky, omega, gamma

    try:
        sf = sqrt(mass_main / 1.0)
        ky_out = ky * sf / z_main if z_main != 0 else ky
        omega_out = omega * sf
        gamma_out = gamma * sf
    except Exception:
        return ky, omega, gamma

    return ky_out, omega_out, gamma_out


def cgyro_tglf_error(
    ky_cgyro, omega_cgyro, gamma_cgyro,
    ky_tglf, omega_tglf, gamma_tglf, output_grid='tglf',
):
    """Relative difference / abs(CGYRO) on the requested grid.

    Only interpolate the other spectrum inside its measured range. Missing or
    non-overlapping data return NaN; a shared single ky is compared directly.
    """
    if output_grid not in ('tglf', 'cgyro'):
        raise ValueError("output_grid must be 'tglf' or 'cgyro'")
    kc, kt = np.asarray(ky_cgyro, dtype=float), np.asarray(ky_tglf, dtype=float)
    target = kt if output_grid == 'tglf' else kc
    result = []
    for cg_values, tg_values in ((omega_cgyro, omega_tglf), (gamma_cgyro, gamma_tglf)):
        vc, vt = np.asarray(cg_values, dtype=float), np.asarray(tg_values, dtype=float)
        if len(vc) != len(kc) or len(vt) != len(kt):
            raise ValueError('ky and spectrum lengths must match')
        out = np.full(target.shape, np.nan, dtype=float)
        source_x, source_y = (kc, vc) if output_grid == 'tglf' else (kt, vt)
        target_y = vt if output_grid == 'tglf' else vc
        valid = np.isfinite(source_x) & np.isfinite(source_y)
        sx, sy = source_x[valid], source_y[valid]
        order = np.argsort(sx)
        sx, sy = sx[order], sy[order]
        if len(sx) == 0:
            result.append(out)
            continue
        if len(np.unique(sx)) != len(sx):
            raise ValueError('duplicate ky values are ambiguous for interpolation')
        overlap = np.isfinite(target) & np.isfinite(target_y) & (target >= sx[0]) & (target <= sx[-1])
        if np.any(overlap):
            interpolated = np.interp(target[overlap], sx, sy)
            cg = interpolated if output_grid == 'tglf' else target_y[overlap]
            tg = target_y[overlap] if output_grid == 'tglf' else interpolated
            out[overlap] = np.abs(cg - tg) / np.maximum(np.abs(cg), 1e-6)
        result.append(out)
    return tuple(result)


def apply_divide_by_ky(ky, omega, gamma, divide_by_ky, divide_by_ky2=False):
    """Apply the selected omega/gamma ky normalization."""
    if len(ky) == 0:
        return omega, gamma, None, None

    ky, omega, gamma = (np.asarray(v, dtype=float) for v in (ky, omega, gamma))
    if divide_by_ky2:
        y_omega = np.divide(omega, ky ** 2, out=np.full_like(omega, np.nan), where=ky != 0)
        y_gamma = np.divide(gamma, ky ** 2, out=np.full_like(gamma, np.nan), where=ky != 0)
        title_omega = 'omega/ky^2'
        title_gamma = 'gamma/ky^2'
    elif divide_by_ky:
        y_omega = np.divide(omega, ky, out=np.full_like(omega, np.nan), where=ky != 0)
        y_gamma = np.divide(gamma, ky, out=np.full_like(gamma, np.nan), where=ky != 0)
        title_omega = 'omega/ky'
        title_gamma = 'gamma/ky'
    else:
        y_omega = omega
        y_gamma = gamma
        title_omega = 'omega'
        title_gamma = 'gamma'

    return y_omega, y_gamma, title_omega, title_gamma


def divide_title(ctx, field):
    """Return the displayed omega/gamma label for the selected ky power."""
    if ctx.get('divide_by_ky2', False):
        return f'{field}/ky^2'
    if ctx.get('divide_by_ky', True):
        return f'{field}/ky'
    return field


def parse_float_list_text(text):
    """Parse comma/space mixed float list text."""
    if not isinstance(text, str) or len(text.strip()) == 0:
        return []
    raw = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", text)
    out = []
    for item in raw:
        try:
            out.append(float(item))
        except Exception:
            continue
    return out


def _gamma_ratio_ky_bounds(ctx):
    """Decode optional ky lower/upper bounds for all-ky gamma_ref mode."""
    ky_min = _to_float_scalar(ctx.get('gamma_ref_ky_min', None))
    ky_max = _to_float_scalar(ctx.get('gamma_ref_ky_max', None))
    if ky_min is not None and ky_max is not None and ky_min > ky_max:
        ky_min, ky_max = ky_max, ky_min
    return ky_min, ky_max


def split_2d_param_name(pname):
    """
    Split a combined 2D parameter name like `para1+para2`.

    Returns `(para1_name, para2_name)`, with a safe fallback when delimiter
    is absent.
    """
    if not isinstance(pname, str) or '+' not in pname:
        return str(pname), 'para2'
    p1, p2 = pname.split('+', 1)
    return p1.strip(), p2.strip()


def to_float_list(values):
    """
    Convert scalar/list/string inputs into a float list.

    String inputs are parsed with regex, so formats like `'[0.1, 0.2]'`
    and `'0.1 0.2'` are both supported.
    """
    if values is None:
        return []
    if isinstance(values, str):
        # OMFIT Entry may store arrays as strings like "[0.1 0.2]" or "0.1,0.2".
        raw = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", values)
    elif hasattr(values, '__iter__'):
        raw = list(values)
    else:
        raw = [values]

    out = []
    for item in raw:
        try:
            out.append(float(item))
        except Exception:
            pass
    return out


def available_numeric_keys(mapping):
    """Return sorted numeric keys parsed from a mapping-like object."""
    vals = []
    if not hasattr(mapping, 'keys'):
        return vals
    for k in mapping.keys():
        try:
            vals.append(float(k))
        except Exception:
            continue
    vals.sort()
    return vals


def extract_tglf2d_series(
    node, mode_idx=1, normalize_main_ion=False, root=None, rho=None, ctx=None
):
    """Extract ky, omega, gamma spectrum arrays from a 2D TGLF node for one eigen mode."""
    try:
        spec = node.get('eigenvalue_spectrum', node)
    except Exception:
        spec = node

    try:
        ky = array(spec.get('ky', []), dtype=float).ravel()
        omega = array(spec[f'freq({int(mode_idx)})']).ravel()
        gamma = array(spec[f'gamma({int(mode_idx)})']).ravel()
    except Exception:
        return array([]), array([]), array([])

    if not len(ky):
        return array([]), array([]), array([])
    ky, omega, gamma = checked_spectrum(ky, omega, gamma)
    ky, omega, gamma = normalize_tglf_if_needed(
        node, ky, omega, gamma, normalize_main_ion, root=root, rho=rho
    )
    ky = _maybe_abs_ky(ky, ctx)
    return ky, omega, gamma


def get_2d_scan_values(param_node, cfg):
    """Missing keys use available values; explicitly empty selections stay empty."""
    p1 = to_float_list(cfg['para1_values']) if 'para1_values' in cfg else available_numeric_keys(param_node)
    if 'para2_values' in cfg:
        p2 = to_float_list(cfg['para2_values'])
    else:
        p2 = sorted(set(value for first in p1
                        for value in available_numeric_keys(param_node.get(resolve_key(param_node, first), {}))))
    return p1, p2


def resolve_2d_param_node(param_node, p1_val, p2_val):
    """
    Resolve nested 2D scan node:
    param_node[p1_val][p2_val]
    """
    p1_key = resolve_key(param_node, p1_val)
    if p1_key is None:
        return None
    p2_map = param_node[p1_key]
    if not hasattr(p2_map, 'keys'):
        return None
    p2_key = resolve_key(p2_map, p2_val)
    if p2_key is None:
        return None
    return p2_map[p2_key]


def mode_titles(ctx, mode_idx):
    """Return omega/gamma title pair for one eigen mode."""
    if ctx.get('divide_by_ky2', False):
        return f'omega({mode_idx})/ky^2', f'gamma({mode_idx})/ky^2'
    if ctx.get('divide_by_ky', True):
        return f'omega({mode_idx})/ky', f'gamma({mode_idx})/ky'
    return f'omega({mode_idx})', f'gamma({mode_idx})'


def prepare_spectrum_for_plot(ky, omega_arr, gamma_arr, divide_by_ky=True, divide_by_ky2=False):
    """Sort and scale without dividing by zero or modifying saved values."""
    ky, omega_arr, gamma_arr = checked_spectrum(ky, omega_arr, gamma_arr)
    order = np.argsort(ky)
    ky = ky[order]
    omega, gamma, _, _ = apply_divide_by_ky(ky, omega_arr[order], gamma_arr[order], divide_by_ky, divide_by_ky2)
    return ky, omega, gamma


def collect_tglf2d_mode_curves(
    param_node, fixed_values, varying_values, fixed_is_para2, divide_by_ky=True,
    normalize_main_ion=False, ctx=None, divide_by_ky2=False
):
    """
    Collect mode-indexed spectra curves for a parameter grid.

    Returns:
      {
        1: [{'ky','omega','gamma','fixed_val','varying_val'}, ...],
        2: [...]
      }
    """
    curves_by_mode = {1: [], 2: []}

    for fixed_val in fixed_values:
        for varying_val in varying_values:
            if fixed_is_para2:
                p1_val, p2_val = varying_val, fixed_val
            else:
                p1_val, p2_val = fixed_val, varying_val

            node = resolve_2d_param_node(param_node, p1_val, p2_val)
            if node is None:
                continue

            for mode_idx in [1, 2]:
                ky, omega_arr, gamma_arr = extract_tglf2d_series(
                    node, mode_idx=mode_idx, normalize_main_ion=normalize_main_ion,
                    ctx=ctx
                )
                if len(ky) == 0:
                    continue

                ky_plot, omega_plot, gamma_plot = prepare_spectrum_for_plot(
                    ky, omega_arr, gamma_arr,
                    divide_by_ky=divide_by_ky, divide_by_ky2=divide_by_ky2
                )
                try:
                    fixed_num = float(fixed_val)
                    varying_num = float(varying_val)
                except Exception:
                    continue

                curves_by_mode[mode_idx].append({
                    'ky': ky_plot,
                    'omega': omega_plot,
                    'gamma': gamma_plot,
                    'fixed_val': fixed_num,
                    'varying_val': varying_num,
                })

    return curves_by_mode


def _fmt_curve_value(value):
    """Format numeric-like values for curve labels."""
    try:
        return f'{float(value):g}'
    except Exception:
        return str(value)


def build_labeled_mode_curves(mode_curves, varying_name, fixed_name):
    """
    Convert raw mode curves into generic curve dicts with display labels.
    """
    curves = []
    for item in mode_curves:
        label = f"{varying_name}={item['varying_val']:g}, {fixed_name}={item['fixed_val']:g}"
        curves.append({
            'ky': item['ky'],
            'omega': item['omega'],
            'gamma': item['gamma'],
            'label': label,
        })
    return curves


def build_surface_from_curves(spectra_curves):
    """
    Build gridded surface arrays from mode curves.
    Returns ky_base, var_axis, z_omega, z_gamma.
    """
    if len(spectra_curves) == 0:
        return None, None, None, None

    spectra_curves = sorted(spectra_curves, key=lambda x: x['varying_val'])
    ky_base = spectra_curves[0]['ky']
    var_axis = array([sc['varying_val'] for sc in spectra_curves], dtype=float)
    z_omega = zeros((len(spectra_curves), len(ky_base)))
    z_gamma = zeros((len(spectra_curves), len(ky_base)))

    for i, sc in enumerate(spectra_curves):
        if len(sc['ky']) == len(ky_base) and allclose(sc['ky'], ky_base):
            z_omega[i, :] = sc['omega']
            z_gamma[i, :] = sc['gamma']
        else:
            z_omega[i, :] = interp(ky_base, sc['ky'], sc['omega'])
            z_gamma[i, :] = interp(ky_base, sc['ky'], sc['gamma'])

    return ky_base, var_axis, z_omega, z_gamma


def build_3d_x_axis(ky_base, use_log_x):
    """
    Build x-axis values/label for 3D surfaces with optional explicit log10 transform.
    Returns x_vals_plot, x_label_3d, use_log_x_3d.
    """
    use_log_x_3d = False
    x_label_3d = '$k_y$*$\\rho_s$'
    x_vals_plot = ky_base

    if use_log_x and all(ky_base > 0):
        use_log_x_3d = True
        x_vals_plot = log10(ky_base)
        x_label_3d = 'log10($k_y$*$\\rho_s$)'
    return x_vals_plot, x_label_3d, use_log_x_3d


def apply_3d_log_ticks(ax_omega, ax_gamma, x_vals_plot, ky_base):
    """Set readable ky tick labels after explicit log10 transform."""
    n_ticks = min(6, len(ky_base))
    tick_idx = unique(linspace(0, len(ky_base) - 1, n_ticks, dtype=int))
    tick_pos = x_vals_plot[tick_idx]
    tick_lab = [f'{ky_base[i]:.3g}' for i in tick_idx]
    ax_omega.set_xticks(tick_pos)
    ax_gamma.set_xticks(tick_pos)
    ax_omega.set_xticklabels(tick_lab)
    ax_gamma.set_xticklabels(tick_lab)


def _flux_species_rank(species_label):
    """
    Stable species order for flux legends:
    electron first, then ion sum, then ion1/ion2..., then others.
    """
    s = str(species_label).strip().lower()
    if s in ['e', 'elec', 'electron', 'electrons']:
        return (0, 0, s)
    if s in ['ion_sum', 'ionsum', 'ion', 'ions']:
        return (1, 0, s)
    m = re.match(r'^(?:ion|i)\s*_?(\d+)$', s)
    if m is not None:
        try:
            return (2, int(m.group(1)), s)
        except Exception:
            return (2, 9999, s)
    return (3, 0, s)


def _filter_curves_by_kind(curves, kind_name):
    """Return curves matching given model kind name."""
    kind_up = str(kind_name).upper()
    out = []
    for curve in curves:
        if str(curve.get('kind', '')).upper() == kind_up:
            out.append(curve)
    return out


def checked_spectrum(ky, omega, gamma):
    """Enforce aligned finite data; mismatch is an error, never silent truncation."""
    values = tuple(np.asarray(v, dtype=float).ravel() for v in (ky, omega, gamma))
    if len({len(v) for v in values}) != 1:
        raise ValueError('ky, omega and gamma have different lengths')
    if not all(np.all(np.isfinite(v)) for v in values):
        raise ValueError('Spectrum contains non-finite values')
    return values
