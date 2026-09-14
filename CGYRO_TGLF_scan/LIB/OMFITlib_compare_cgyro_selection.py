"""CGYRO self-comparison: selection helpers, independent of GUI globals."""

# Explicit builtins protect against the OMFIT pylab execution namespace.
from builtins import Exception, TypeError, ValueError, abs, all, bool, dict, enumerate, float, hasattr, isinstance, len, list, repr, set, str, tuple
import ast
import math
import re
from numpy import array
from OMFITlib_compare_state import STYLE_DEFAULTS, stable_keys
from OMFITlib_compare_core import resolve_key as _resolve_mapping_key
from OMFITlib_compare_options import is_gamma_ratio_plot_mode, parse_float_list_text, validate_options


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

    try:
        return parse_float_list_text(text)
    except ValueError:
        pass

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
    errors = validate_options(settings)
    if errors:
        raise ValueError('\n'.join(errors))
    legacy_physics = root['SETTINGS'].get('PHYSICS', {})
    ctx = {}
    ctx['plotcgyro'] = settings.get('plotcgyro', legacy_physics.get('plotcgyro', True))
    ctx['plot_mode'] = settings.get('plot_mode', 'Plot 2D')
    ctx['plot_3d'] = (ctx['plot_mode'] == 'Plot 3D')
    ctx['single_ky'] = (ctx['plot_mode'] == 'Plot single ky')
    ctx['plot_gamma_ratio'] = is_gamma_ratio_plot_mode(ctx['plot_mode'])
    ctx['plot_eigen_ball'] = (ctx['plot_mode'] == 'Plot eigen ball')
    ctx['abs_ky'] = bool(settings.get('abs_ky', legacy_physics.get('abs_ky', False)))
    exporting = settings.get('linear_export_now', False)
    ctx['selected_single_ky'] = parse_single_ky_values(root) if ctx['single_ky'] and not exporting else []
    ctx['gamma_ref_mode'] = settings.get('gamma_ref_mode', 'all ky')
    ctx['gamma_ref_value'] = settings.get('gamma_ref_value', '')
    ctx['gamma_ref_ky_values'] = settings.get('gamma_ref_ky_values', '')
    ctx['eigen_ky_mode'] = settings.get('eigen_ky_mode', 'max gamma')
    ctx['selected_eigen_ky'] = parse_eigen_ky_values(root) if ctx['plot_eigen_ball'] and ctx['eigen_ky_mode'] == 'single ky' and not exporting else []
    ctx['eigen_abs'] = settings.get('eigen_abs', False)
    ctx['eigen_error_filter'] = settings.get('eigen_error_filter', False)

    ctx['runid'] = settings.get('runid', '')
    ctx['nr_CGYRO'] = list(dict.fromkeys(settings.get('nr_CGYRO', [])))
    ctx['force_read_all_nr_items'] = bool(settings.get('force_read_all_nr_items', False))
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
    ctx['error_filter'] = settings.get('error_filter', False)
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
    ctx['_diagnostics'] = []
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
        return list({repr(item): item for item in out}.values())

    selected_map = ctx.get('selected_paras', {})
    if nr is not None:
        selected_by_nr = ctx.get('selected_paras_by_nr', {})
        if ctx.get('force_read_all_nr_items', None):
            selected_map = {}
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
    return False
