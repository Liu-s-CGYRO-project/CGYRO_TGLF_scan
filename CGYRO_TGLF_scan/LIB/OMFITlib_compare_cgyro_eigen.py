"""CGYRO self-comparison: eigen helpers, independent of GUI globals."""

# Explicit builtins protect against the OMFIT pylab execution namespace.
from builtins import Exception, abs, complex, float, getattr, hasattr, int, len, sorted
import numpy as np
from numpy import argmax, argmin, argsort, array, imag, interp, iscomplexobj, linspace, ones, pi, real, unique, zeros
from OMFITlib_compare_cgyro_data import _get_cgyro_lin_node, compute_freq_stats, diagnostic
from OMFITlib_compare_cgyro_selection import maybe_abs_ky


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

    n = len(theta_src)
    if n == 0 or n != len(field_src) or not np.all(np.isfinite(theta_src)) or not np.all(np.isfinite(field_src)):
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
    n = len(theta_src)
    if n <= 1 or n != len(phi_raw) or not np.all(np.isfinite(theta_src)):
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


def extract_eigen_curve(datadir):
    """Read saved fields on a common grid; do not invent missing E-parallel data."""
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

    return {
        'theta_over_pi': theta_b / pi,
        'phi_b': phi_b,
        'epar_b': epar_b,
        'has_epar': epar_b is not None,
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

    candidates = [item for item in entries if np.isfinite(item['gamma_mean'])]
    if ctx.get('eigen_error_filter', False):
        tol = ctx.get('error_tolerance', 0.01)
        candidates = [
            item for item in candidates
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
        diagnostic(ctx, nr, para, value, 'No saved linear spectrum for eigenfunction selection')
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
        if not np.isfinite(ky_val):
            diagnostic(ctx, nr, para, value, 'Non-finite eigenfunction ky', ky=key)
            continue

        freq_stats = compute_freq_stats(datadir, ctx['ave_window'])
        gamma_mean = np.nan
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
    selected = select_eigen_entries(entries, ctx)
    if not selected:
        diagnostic(ctx, nr, para, value, 'No valid eigenfunction candidate passes the selected frequency/filter policy')
    return selected
