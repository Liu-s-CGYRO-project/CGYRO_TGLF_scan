"""CGYRO/TGLF comparison: series.

Extracted from the reviewed project; data is read from the supplied OMFIT tree.
"""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    IndexError,
    KeyError,
    TypeError,
    ValueError,
    dict,
    float,
    hasattr,
    int,
    isinstance,
    len,
    list,
    max,
    range,
    str,
    tuple,
    zip,
)

import numpy as np
from numpy import (
    array,
    ndarray,
)
from OMFITlib_compare_state import (
    stable_keys,
)
from OMFITlib_compare_core import (
    checked_spectrum,
)
from OMFITlib_compare_core import (
    _maybe_abs_ky,
    _tail_frequency_stats,
    _to_float_scalar,
    cgyro_tglf_error,
    normalize_if_needed,
    normalize_tglf_if_needed,
    resolve_2d_param_node,
    resolve_key,
    split_2d_param_name,
    to_float_list,
)


def collect_cgyro_series(root, ctx, runid, nr, para, value):
    """Read one CGYRO spectrum and report malformed/missing samples explicitly."""
    node = root.get('CGYRO_scan', {}).get('RUN_DB', {})
    for token in (runid, nr, para, value):
        key = resolve_key(node, token)
        if key is None:
            ctx.setdefault('_diagnostics', []).append('Missing CGYRO selection: {}'.format((runid, nr, para, value)))
            return tuple(array([]) for _ in range(5))
        node = node[key]
    linear = node.get('lin', {})
    values = []
    for key in stable_keys(linear):
        try:
            data = linear[key]
            ntime = int(data['n_time'])
            window = float(ctx.get('ave_window', .02))
            if not 0 < window <= 1 or ntime <= 0:
                raise ValueError('Invalid averaging window or sample count')
            count = max(2, int(ntime * window))
            omega = np.asarray(data['freq']['omega'][0], dtype=float)
            gamma = np.asarray(data['freq']['gamma'][0], dtype=float)
            if len(omega) != len(gamma) or len(omega) != ntime:
                raise ValueError('Frequency samples disagree with n_time')
            stats = _tail_frequency_stats(omega[-count:], gamma[-count:])
            if stats is None:
                raise ValueError('Empty or non-finite frequency samples')
            ky, om, ga = normalize_if_needed(data, float(data['kyrhos']), stats[0][0], stats[1][0], ctx.get('normalize_main_ion', False))
            ky = float(_maybe_abs_ky(ky, ctx))
            if not np.all(np.isfinite([ky, om, ga])):
                raise ValueError('Non-finite normalized spectrum')
            values.append((ky, om, ga, stats[0][2], stats[1][2]))
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            ctx.setdefault('_diagnostics', []).append('CGYRO {} / {} / {} / {} / ky={}: {}'.format(runid, nr, para, value, key, exc))
    if not values:
        return tuple(array([]) for _ in range(5))
    return tuple(np.asarray(v) for v in zip(*values))


def _parse_tglf_2d_value_pair(value):
    """Parse one 2D TGLF value token into (para1_value, para2_value)."""
    if isinstance(value, (list, tuple, ndarray)) and len(value) >= 2:
        v1 = _to_float_scalar(value[0])
        v2 = _to_float_scalar(value[1])
        return v1, v2

    if isinstance(value, dict):
        v1 = _to_float_scalar(value.get('para1', value.get('p1', None)))
        v2 = _to_float_scalar(value.get('para2', value.get('p2', None)))
        return v1, v2

    vals = to_float_list(value)
    if len(vals) >= 2:
        return float(vals[0]), float(vals[1])
    return None, None


def collect_tglf_series(root, ctx, rho, para, value, mode_idx=1):
    """Read only the selected 1D/2D source; preserve optional missing second modes."""
    dimension = ctx.get('tglf_state', {}).get('spectra_mode')
    if dimension is None:
        dimension = '2D' if isinstance(value, (list, tuple, ndarray)) else '1D'
    key = 'scanResults2D_spectra' if dimension == '2D' else 'scanResults_spectra'
    node = root.get('TGLF_scan', {}).get(key, {})
    try:
        for token in (rho, para):
            found = resolve_key(node, token)
            if found is None:
                raise KeyError(token)
            node = node[found]
        if dimension == '2D':
            p1, p2 = _parse_tglf_2d_value_pair(value)
            node = resolve_2d_param_node(node, p1, p2)
        else:
            found = resolve_key(node, value)
            node = node[found] if found is not None else None
        if node is None:
            raise KeyError(value)
        spec = node.get('eigenvalue_spectrum', node)
        if int(mode_idx) == 2 and ('freq(2)' not in spec or 'gamma(2)' not in spec):
            return array([]), array([]), array([])
        ky, omega, gamma = checked_spectrum(spec['ky'], spec['freq({})'.format(int(mode_idx))], spec['gamma({})'.format(int(mode_idx))])
        ky, omega, gamma = normalize_tglf_if_needed(node, ky, omega, gamma, ctx.get('normalize_main_ion', False), root=root, rho=rho)
        return _maybe_abs_ky(ky, ctx), omega, gamma
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        ctx.setdefault('_diagnostics', []).append('TGLF {} / {} / {} / {}: {}'.format(key, rho, para, value, exc))
        return array([]), array([]), array([])


def apply_cross_model_error_if_applicable(ctx, cgyro_curves, tglf_curves):
    """
    Apply CGYRO-TGLF cross-model error only in two valid cases:
    1) exactly one TGLF curve (reference), compare all CGYRO curves to it;
    2) exactly one CGYRO curve (reference), compare all TGLF curves to it.
    """
    if ctx.get('error_flag') != 'CGYRO-TGLF':
        return

    if len(tglf_curves) == 1 and len(cgyro_curves) >= 1:
        ref = tglf_curves[0]
        ref['show_error'] = False
        for curve in cgyro_curves:
            omega_err, gamma_err = cgyro_tglf_error(
                curve['ky'], curve['omega'], curve['gamma'],
                ref['ky'], ref['omega'], ref['gamma'],
                output_grid='cgyro',
            )
            curve['show_error'] = True
            curve['omega_error'] = omega_err
            curve['gamma_error'] = gamma_err
            curve['error_label'] = f"{curve['label']} vs {ref['label']}"
        return

    if len(cgyro_curves) == 1 and len(tglf_curves) >= 1:
        ref = cgyro_curves[0]
        ref['show_error'] = False
        for curve in tglf_curves:
            omega_err, gamma_err = cgyro_tglf_error(
                ref['ky'], ref['omega'], ref['gamma'],
                curve['ky'], curve['omega'], curve['gamma'],
                output_grid='tglf',
            )
            curve['show_error'] = True
            curve['omega_error'] = omega_err
            curve['gamma_error'] = gamma_err
            curve['error_label'] = f"{curve['label']} vs {ref['label']}"
        return

    raise ValueError('Model-difference panels require exactly one reference curve in at least one model per page.')


def read_settings(root, ctx, compare_mode):
    """
    Decode UI state for both compare modes.

    Returns:
    - rho_dict:
      * CGYRO_vs_TGLF: {nr: [rho, ...]}
      * TGLF_vs_CGYRO: {rho: [nr, ...]}
    - tglf_selected_paras
    - cgyro_selected_paras
    - runid: single runid (used by both compare modes)
    """
    tglf_state = ctx['tglf_state']
    cgyro_state = ctx['cgyro_state']
    selected_key = 'selected_paras_2d' if tglf_state.get('spectra_mode') == '2D' else 'selected_paras'
    tglf_selected_paras = dict(tglf_state.get(selected_key, {}))
    cgyro_selected_paras = cgyro_state.get('selected_paras', {})
    runid = cgyro_state.get('runid', '')
    rho_dict = {}

    if compare_mode == 'CGYRO_vs_TGLF':
        rho_pair_cfg = tglf_state.get('rho_pair_flags', {})
        nr_selected = cgyro_state.get('nr_selected', [])
        for nr in nr_selected:
            nr_key = str(nr)
            flags = rho_pair_cfg.get(nr_key, {})
            rho_vals = []
            for rho_key, is_on in flags.items():
                if not is_on:
                    continue
                try:
                    rho_vals.append(float(rho_key))
                except Exception:
                    continue
            rho_dict[nr] = rho_vals

    elif compare_mode == 'TGLF_vs_CGYRO':
        rho_selected = tglf_state.get('rho_selected', [])
        nr_pair_cfg = cgyro_state.get('rho_pair_cfg', {})
        run_db = root['CGYRO_scan']['RUN_DB']
        runid_key = resolve_key(run_db, runid)
        for rho in rho_selected:
            rho_key = str(rho)
            cfg = nr_pair_cfg.get(rho_key, {})

            nr_flags = cfg.get('nr_flag', {})
            if runid_key is None:
                rho_dict[rho] = []
                continue

            nr_list = stable_keys(run_db[runid_key])
            if 'nr_selected' in cfg:
                rho_dict[rho] = [nr for nr in cfg['nr_selected'] if nr in nr_list]
                continue
            selected_nr = []
            for idx, flag in nr_flags.items():
                if not flag:
                    continue
                try:
                    i = int(idx)
                except Exception:
                    continue
                if 0 <= i < len(nr_list):
                    selected_nr.append(nr_list[i])
            rho_dict[rho] = selected_nr

    return rho_dict, tglf_selected_paras, cgyro_selected_paras, runid


def collect_cgyro_curves(k, v, runid, run_db, cgyro_selected_paras, root, ctx):
    """
    Collect CGYRO curves for one primary key:
    - In CGYRO_vs_TGLF mode: k is nr, v is [rho...]
    - In TGLF_vs_CGYRO mode: k is nr, v is rho
    """
    curves = []
    nr_key = k

    if not runid:
        return curves

    runid_key = resolve_key(run_db, runid)
    if runid_key is None:
        return curves

    run_db_runid = run_db[runid_key]
    nr_resolved = resolve_key(run_db_runid, nr_key)
    if nr_resolved is None:
        return curves

    run_db_nr = run_db_runid[nr_resolved]

    for para, values in cgyro_selected_paras.items():
        para_key = resolve_key(run_db_nr, para)
        if para_key is None:
            continue

        if hasattr(values, '__iter__') and not isinstance(values, str):
            vals = list(values)
        else:
            vals = [values]

        if not vals:
            continue

        run_db_nr_para = run_db_nr[para_key]

        for value in vals:
            value_key = resolve_key(run_db_nr_para, value)
            if value_key is None:
                continue

            ky, omega, gamma, omega_error, gamma_error = collect_cgyro_series(
                root, ctx, runid_key, nr_resolved, para_key, value_key
            )
            if not len(ky):
                continue
            label_cg = f'CGYRO({nr_resolved}, {para}={value})'
            curves.append({
                'kind': 'CGYRO',
                'label': label_cg,
                'error_label': label_cg,
                'show_error': True,
                'nr': nr_resolved,
                'rho': None,
                'para': para,
                'value': value,
                'ky': ky,
                'omega': omega,
                'gamma': gamma,
                'omega_error': omega_error,
                'gamma_error': gamma_error,
            })

    return curves


def collect_tglf_curves(k, tglf_selected_paras, root, ctx, mode_idx=1, include_rho_in_label=True):
    """
    Collect TGLF curves:
    - k may be a single rho or a rho list.
    """
    curves = []
    if isinstance(k, (list, tuple, ndarray)):
        rho_list = list(k)
    else:
        rho_list = [k]

    for rho_tglf in rho_list:
        # Let collect_tglf_series resolve the radius in the relevant 1D/2D tree.
        for para, values in tglf_selected_paras.items():
            vals_to_use = []
            is_2d_cfg = isinstance(values, dict) and (
                ('para1_values' in values) or ('para2_values' in values)
            )

            if is_2d_cfg:
                p1_vals = to_float_list(values.get('para1_values', []))
                p2_vals = to_float_list(values.get('para2_values', []))

                for p1 in p1_vals:
                    for p2 in p2_vals:
                        vals_to_use.append((float(p1), float(p2)))
            else:
                if hasattr(values, '__iter__') and not isinstance(values, str):
                    vals_to_use = list(values)
                else:
                    vals_to_use = [values]

            if len(vals_to_use) == 0:
                continue

            for value in vals_to_use:
                value_display = value
                ky, omega, gamma = collect_tglf_series(
                    root, ctx, rho_tglf, para, value, mode_idx=mode_idx
                )
                if len(ky) == 0:
                    continue

                if isinstance(value, (list, tuple, ndarray)) and len(value) >= 2:
                    p1_name, p2_name = split_2d_param_name(str(para))
                    try:
                        p1_txt = f'{float(value[0]):g}'
                    except Exception:
                        p1_txt = str(value[0])
                    try:
                        p2_txt = f'{float(value[1]):g}'
                    except Exception:
                        p2_txt = str(value[1])
                    value_display = f'{p1_name}={p1_txt},{p2_name}={p2_txt}'

                if include_rho_in_label:
                    label_tg = f'TGLF(rho={rho_tglf}, {para}={value_display}, mode={mode_idx})'
                else:
                    label_tg = f'{para}={value_display}, mode={mode_idx}'
                curves.append({
                    'kind': 'TGLF',
                    'label': label_tg,
                    'error_label': label_tg,
                    'show_error': False,
                    'nr': None,
                    'rho': rho_tglf,
                    'para': para,
                    'value': value,
                    'ky': ky,
                    'omega': omega,
                    'gamma': gamma,
                    'omega_error': np.full(len(ky), np.nan),
                    'gamma_error': np.full(len(ky), np.nan),
                })

    return curves
