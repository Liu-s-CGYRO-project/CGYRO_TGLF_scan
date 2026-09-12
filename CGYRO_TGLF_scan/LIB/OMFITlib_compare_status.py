"""CGYRO/TGLF comparison: status.

Extracted from the reviewed project; data is read from the supplied OMFIT tree.
"""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    Exception,
    any,
    float,
    getattr,
    hasattr,
    isinstance,
    len,
    list,
    max,
    open,
    reversed,
    str,
)

import os
import re
from numpy import (
    argsort,
    array,
)
from OMFITlib_compare_core import (
    _get_mapping_item,
    _maybe_abs_ky,
    _to_float_scalar,
    resolve_key,
    to_float_list,
)
from OMFITlib_compare_style import (
    DEFAULT_FIGSIZE_GAMMA_RATIO,
    apply_figure_layout,
    finalize_axis_legend,
)


def _parse_cgyro_outmsg_code(last_line):
    """Map out.cgyro.info last-line text to status code."""
    text = str(last_line).strip().lower()
    if len(text) == 0:
        return 3
    if 'linear converged' in text:
        return 0
    if 'linear terminated at max time' in text:
        return 1
    if 'integration error exceeded limit' in text:
        return 2
    return 3


def _read_cgyro_status_code(datadir):
    """
    Read one CGYRO run status from out.cgyro.info.

    Code meaning:
      0 converged
      1 terminated at max time
      2 integration error
      3 unfinished/unknown
      4 no out.cgyro.info
    """
    if not hasattr(datadir, 'get'):
        return 4

    info_node = datadir.get('out.cgyro.info', None)
    if info_node is None:
        return 4

    filename = getattr(info_node, 'filename', '')
    if not isinstance(filename, str) or len(filename.strip()) == 0 or (not os.path.isfile(filename)):
        return 4

    try:
        with open(filename, 'r', errors='ignore') as fobj:
            lines = fobj.readlines()
    except Exception:
        return 4

    if len(lines) == 0:
        return 3
    last_nonempty = ''
    for line in reversed(lines):
        if len(str(line).strip()) > 0:
            last_nonempty = str(line).strip()
            break
    return _parse_cgyro_outmsg_code(last_nonempty)


def _iter_selected_parameter_items_for_nr(mode_state, nr):
    """
    Yield (para, values) selected in CGYRO_vs_CGYRO mode.

    Per-nr selections take precedence over merged global selection.
    """
    def _normalize_selected_values(values):
        if values is None:
            return []
        if isinstance(values, str):
            vals = to_float_list(values)
            if len(vals) > 0:
                return vals
            tokens = [t.strip() for t in re.split(r'[\s,]+', values) if len(t.strip()) > 0]
            return tokens
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
                parsed = to_float_list(item_s)
                if len(parsed) > 0 and len(item_s) > 1:
                    out.extend(parsed)
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

    selected_map = mode_state.get('selected_paras', {})
    selected_by_nr = mode_state.get('selected_paras_by_nr', {})
    if hasattr(selected_by_nr, 'get'):
        per_nr = selected_by_nr.get(str(nr), None)
        if hasattr(per_nr, 'keys'):
            selected_map = per_nr

    if not hasattr(selected_map, 'keys'):
        return

    for para in selected_map:
        vals = _normalize_selected_values(selected_map[para])
        if len(vals) == 0:
            continue
        yield para, vals


def _collect_cgyro_output_status_curves(root, mode_state, runid, nr, para, values, allow_all_values_fallback=False):
    """Collect status-code curves (y=status) vs ky for one (nr, para)."""
    out_curves = []
    try:
        run_db = root['CGYRO_scan']['RUN_DB']
        runid_key = resolve_key(run_db, runid)
        if runid_key is None:
            return out_curves
        nr_map = run_db[runid_key]
        nr_key = resolve_key(nr_map, nr)
        if nr_key is None:
            return out_curves
        para_map = nr_map[nr_key]
        para_key = resolve_key(para_map, para)
        if para_key is None:
            return out_curves
        value_map = para_map[para_key]
    except Exception:
        return out_curves

    values_iter = list(values)
    if len(values_iter) == 0 and allow_all_values_fallback and hasattr(value_map, 'keys'):
        values_iter = list(value_map.keys())

    for value in values_iter:
        value_key = resolve_key(value_map, value)
        if value_key is None:
            continue
        try:
            cgyrodir = value_map[value_key]['lin']
        except Exception:
            continue
        if not hasattr(cgyrodir, 'keys'):
            continue

        ky_vals = []
        status_vals = []
        for ky_key in cgyrodir.keys():
            datadir = cgyrodir[ky_key]
            ky_val = _to_float_scalar(_get_mapping_item(datadir, 'kyrhos'))
            if ky_val is None:
                ky_val = _to_float_scalar(ky_key)
            if ky_val is None:
                continue
            ky_val = _maybe_abs_ky(ky_val, mode_state.get('plot', {}))
            status_code = _read_cgyro_status_code(datadir)
            ky_vals.append(float(ky_val))
            status_vals.append(float(status_code))

        if len(ky_vals) == 0:
            continue
        ky_arr = array(ky_vals, dtype=float)
        st_arr = array(status_vals, dtype=float)
        sort_idx = argsort(ky_arr)
        ky_arr = ky_arr[sort_idx]
        st_arr = st_arr[sort_idx]

        out_curves.append({
            'label': f'{para}={value}',
            'ky': ky_arr,
            'status': st_arr,
        })
    return out_curves


def plot_cgyro_output_status(root, ctx):
    """Plot status code curves for selected CGYRO scans (CGYRO_vs_CGYRO mode)."""
    if str(ctx.get('compare_mode', '')) != 'CGYRO_vs_CGYRO':
        return

    mode_state = ctx.get('mode_state', {})
    runid = mode_state.get('runid', '')
    nr_list = mode_state.get('nr_CGYRO', [])
    if (not hasattr(nr_list, '__iter__')) or len(nr_list) == 0:
        nr_list = mode_state.get('nr_selected', [])
    if (not runid) or (not hasattr(nr_list, '__iter__')) or len(nr_list) == 0:
        return

    fn = FigureNotebook(0, 'CGYRO_Output_Status')
    has_any_page = False
    has_any_para_selection = False
    diagnostics = []

    if not runid:
        diagnostics.append('missing runid')
    if (not hasattr(nr_list, '__iter__')) or len(nr_list) == 0:
        diagnostics.append('no nr selected (nr_CGYRO/nr_selected empty)')

    for nr in nr_list:
        per_nr_has_para = False
        for para, values in _iter_selected_parameter_items_for_nr(mode_state, nr):
            has_any_para_selection = True
            per_nr_has_para = True
            curves = _collect_cgyro_output_status_curves(
                root, mode_state, runid, nr, para, values, allow_all_values_fallback=True
            )
            if len(curves) == 0:
                continue

            fig, ax_grid = fn.subplots(
                nrows=1,
                ncols=1,
                figsize=DEFAULT_FIGSIZE_GAMMA_RATIO,
                label=f'nr={nr},{para}',
                squeeze=False,
            )
            apply_figure_layout(fig, ctx)
            ax = ax_grid[0, 0]

            for spine in ax.spines.values():
                spine.set_linewidth(ctx['bwith'])
            ax.grid(True, alpha=0.3)

            for item in curves:
                ky = item.get('ky', array([]))
                st = item.get('status', array([]))
                if len(ky) == 0 or len(st) == 0:
                    continue
                ax.plot(
                    ky, st, 'o-',
                    linewidth=ctx['lw'],
                    markersize=max(4, ctx['ms'] * 0.7),
                    label=item.get('label', ''),
                )

            if ctx.get('plot_log_x', False):
                positive = True
                for item in curves:
                    ky = item.get('ky', array([]))
                    if len(ky) == 0:
                        continue
                    if any(array(ky) <= 0):
                        positive = False
                        break
                if positive:
                    ax.set_xscale('log')

            ax.set_ylim(-0.1, 4.1)
            ax.set_yticks([0, 1, 2, 3, 4])
            ax.set_xlabel('$k_y$*$\\rho_s$', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
            ax.set_ylabel('output status code', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
            ax.set_title(f'check cgyro output (nr={nr}, {para})', fontdict={'family': 'DejaVu Sans', 'size': ctx['fs1']})
            ax.tick_params(labelsize=ctx['fs2'])

            ax.text(
                0.01, 0.98,
                '0: converged | 1: t_max | 2: integration error | 3: unfinished | 4: missing out.cgyro.info',
                transform=ax.transAxes,
                ha='left',
                va='top',
                fontsize=max(8, ctx['fs2'] - 1),
            )

            finalize_axis_legend(ax, ctx)
            has_any_page = True
        if not per_nr_has_para:
            diagnostics.append(f'nr={nr}: no selected parameters')

    if not has_any_page:
        fig, ax_grid = fn.subplots(
            nrows=1, ncols=1, figsize=DEFAULT_FIGSIZE_GAMMA_RATIO,
            label='no_data', squeeze=False
        )
        apply_figure_layout(fig, ctx)
        ax = ax_grid[0, 0]
        ax.set_axis_off()
        ax.text(
            0.5, 0.5,
            'No selected CGYRO scan data found for output check.',
            ha='center', va='center', transform=ax.transAxes
        )
        if not has_any_para_selection:
            diagnostics.append('selected_paras/selected_paras_by_nr is empty')
        if len(diagnostics) > 0:
            try:
                ax.text(
                    0.5, 0.38,
                    'Reasons: ' + '; '.join(diagnostics),
                    ha='center', va='center', transform=ax.transAxes,
                    fontsize=max(8, ctx['fs2'] - 1)
                )
            except Exception:
                pass
