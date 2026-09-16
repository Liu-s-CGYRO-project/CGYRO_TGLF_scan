"""Selection identity, legacy setting migration and checks without plotting or I/O."""

# OMFIT libraries inherit a pylab namespace; keep Python scalar/iterator semantics.
from builtins import (
    TypeError,
    ValueError,
    all,
    any,
    bool,
    enumerate,
    float,
    hasattr,
    isinstance,
    len,
    list,
    repr,
    sorted,
    str,
    tuple,
)
from copy import (
    deepcopy,
)
import math
import re
from OMFITlib_compare_options import validate_options

MODES = ['CGYRO_vs_TGLF', 'CGYRO_vs_CGYRO', 'TGLF_vs_TGLF', 'TGLF_vs_CGYRO']
MODE_LABELS = {
    'CGYRO_vs_TGLF': 'CGYRO / TGLF · 按 CGYRO 半径分组',
    'CGYRO_vs_CGYRO': 'CGYRO / CGYRO · 扫描对比',
    'TGLF_vs_TGLF': 'TGLF / TGLF · 扫描对比',
    'TGLF_vs_CGYRO': 'TGLF / CGYRO · 按 TGLF 半径分组',
}
STYLE_DEFAULTS = {
    'font_size': 12, 'legend_font_size': 9, 'line_width': 1.8,
    'show_grid': True, 'legend_location': 'best',
    'figure_width': 0.0, 'figure_height': 0.0,
}
SELECTION_KEYS = (
    'nr_flag', 'nr_selected', 'nr_CGYRO', 'rho_flag', 'rho_selected',
    'para_flag', 'para_list_flag', 'selected_paras', 'selected_paras_2d',
    'rho_pair_flags', 'rho_pair_cfg', 'para_list_flag_by_nr',
    'selected_paras_by_nr', '_selector_keys',
)


def natural_key(value):
    return tuple((0, float(p)) if re.fullmatch(r'\d+(?:\.\d+)?', p)
                 else (1, p.casefold()) for p in re.split(r'(\d+(?:\.\d+)?)', str(value)))


def stable_keys(mapping):
    """Stable numeric/natural ordering; never sorts a saved OMFIT tree in-place."""
    # CGYRO RUN_DB stores inspectable metadata beside physical result branches.
    # Reserved keys must never appear as selectable cases or scan parameters.
    keys = [key for key in mapping.keys() if not str(key).startswith('__')]
    try:
        if all(math.isfinite(float(k)) for k in keys):
            return sorted(keys, key=lambda k: (float(k), str(k)))
    except (ValueError, TypeError):
        pass
    return sorted(keys, key=natural_key)


def has_values(value):
    if value is None:
        return False
    if hasattr(value, 'items'):
        return bool(value) and all(has_values(v) for v in value.values())
    if isinstance(value, str):
        return bool(value.strip())
    try:
        return len(value) > 0
    except TypeError:
        return True  # Numeric zero is a valid scan value.


def dict_path(prefix, *keys):
    """Quote arbitrary run/parameter names as literals, including quotes and slashes."""
    for key in keys:
        if hasattr(key, 'item'):
            key = key.item()
        prefix += '[' + repr(key) + ']'
    return prefix


def sync_flags(state, key, items, selected_key=None):
    """Keep legacy index-based widget paths while binding flags to item identity."""
    tokens = [str(item) for item in items]
    history = state.setdefault('_selector_keys', {})
    old = state.get(key, {})
    previous = history.get(key, None)
    if previous is not None:
        enabled = {token for i, token in enumerate(previous) if old.get(i, old.get(str(i), False))}
    elif selected_key and selected_key in state:
        selected = state[selected_key]
        if hasattr(selected, 'items'):
            enabled = {str(k) for k, v in selected.items() if has_values(v)}
        else:
            enabled = {str(item) for item in selected}
    else:
        enabled = {token for i, token in enumerate(tokens) if old.get(i, old.get(str(i), False))}
    state[key] = {i: token in enabled for i, token in enumerate(tokens)}
    history[key] = tokens
    return state[key]


def selected_items(flags, items):
    return [item for i, item in enumerate(items) if flags.get(i, flags.get(str(i), False))]


def activate_source(state, source):
    """Switch only selection state, retaining a small snapshot per run/source.

    Plot styling and user-edited scientific settings remain outside these snapshots.
    The first visit adopts legacy saved selections instead of erasing them.
    """
    previous = state.get('_selection_source', None)
    if previous is None:
        state['_selection_source'] = source
        return
    if previous == source:
        return
    saved = state.setdefault('_selection_sources', {})
    saved[previous] = {k: deepcopy(state[k]) for k in SELECTION_KEYS if k in state}
    restored = deepcopy(saved.get(source, {}))
    for key in SELECTION_KEYS:
        state.pop(key, None)
    state.update(restored)
    state['_selection_source'] = source


def plot_state(mode, state):
    return state if mode == 'CGYRO_vs_CGYRO' else state.setdefault('plot', {})


def initialize_settings(root):
    physics = root.setdefault('SETTINGS', {}).setdefault('PHYSICS', {})
    if physics.get('compare_mode', None) not in MODES:
        physics['compare_mode'] = 'CGYRO_vs_TGLF'
    for mode in MODES:
        state = physics.setdefault(mode, {})
        settings = plot_state(mode, state)
        settings.setdefault('plot_mode', 'Plot 2D')
        if settings['plot_mode'] == 'Plot 纬/纬_ref':
            settings['plot_mode'] = 'Plot γ/γ_ref'
        settings.setdefault('ave_window', 0.02)
        settings.setdefault('effnum', 5)
        settings.setdefault('divide_by_ky', physics.get('divide_by_ky', True))
        settings.setdefault('divide_by_ky2', physics.get('divide_by_ky2', False))
        settings.setdefault('error_tolerance', 0.01)
        settings.setdefault('plot_log_x', False)
        settings.setdefault('plot_log_y', False)
        state.setdefault('legend_order_mode', settings.get('legend_order_mode', 'Plot order'))
        state.setdefault('legend_order_text', settings.get('legend_order_text', ''))
        style = state.setdefault('style', {})
        for key, default in STYLE_DEFAULTS.items():
            style.setdefault(key, default)
        if mode == 'TGLF_vs_TGLF':
            settings.setdefault('tglf_vs_tglf_mode', 'Spectra')
            settings.setdefault('tglf_flux_merge_ions', settings.get('tglf_flux_ion_mode', None) != 'Split ions')
    return physics


def selection_check(root, mode=None):
    """Cheap selection/setting validation; never forces loading saved result objects."""
    physics = root.get('SETTINGS', {}).get('PHYSICS', {})
    mode = mode or physics.get('compare_mode', 'CGYRO_vs_TGLF')
    state = physics.get(mode, {})
    settings = state if mode == 'CGYRO_vs_CGYRO' else state.get('plot', {})
    errors, warnings = [], []
    cg = state if mode == 'CGYRO_vs_CGYRO' else state.get('CGYRO', {})
    tg = state.get('TGLF', {})
    if mode not in MODES:
        errors.append('Choose a supported comparison mode.')
    if mode != 'TGLF_vs_TGLF':
        if cg.get('runid', None) not in root.get('CGYRO_scan', {}).get('RUN_DB', {}):
            errors.append('Choose an available CGYRO run.')
        selections = [cg.get('selected_paras', {})]
        if mode == 'CGYRO_vs_CGYRO' and cg.get('force_read_all_nr_items', None):
            selections = [cg.get('selected_paras_by_nr', {}).get(str(nr), {}) for nr in cg.get('nr_CGYRO', [])]
        if not any(has_values(v) for selected in selections for v in selected.values()):
            errors.append('Select at least one CGYRO parameter and value.')
        if mode == 'CGYRO_vs_CGYRO' and not cg.get('nr_CGYRO', None):
            errors.append('Select at least one CGYRO radius.')
        try:
            window = float(settings.get('ave_window', 0.02))
            if not math.isfinite(window) or not 0 < window <= 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append('Averaging fraction must be > 0 and <= 1 (0.02 means the final 2%).')
    if mode != 'CGYRO_vs_CGYRO':
        key = 'selected_paras_2d' if tg.get('spectra_mode', '1D') == '2D' else 'selected_paras'
        if not any(has_values(v) for v in tg.get(key, {}).values()):
            errors.append('Select at least one TGLF parameter and value (both axes for 2D).')
        if mode in ('TGLF_vs_TGLF', 'TGLF_vs_CGYRO') and not tg.get('rho_selected', None):
            errors.append('Select at least one TGLF radius.')
        if mode == 'CGYRO_vs_TGLF':
            if not cg.get('nr_selected', None):
                errors.append('Select at least one CGYRO radius.')
            for nr in cg.get('nr_selected', []):
                if not any(tg.get('rho_pair_flags', {}).get(str(nr), {}).values()):
                    errors.append('Pair CGYRO {} with a TGLF radius.'.format(nr))
        if mode == 'TGLF_vs_CGYRO':
            for rho in tg.get('rho_selected', []):
                cfg = cg.get('rho_pair_cfg', {}).get(str(rho), {})
                if not cfg.get('nr_selected', None) and not any(cfg.get('nr_flag', {}).values()):
                    errors.append('Pair TGLF {} with a CGYRO radius.'.format(rho))
    if settings.get('divide_by_ky', None) and settings.get('divide_by_ky2', None):
        errors.append('Choose one spectrum scaling: raw, /ky, or /ky².')
    if mode == 'CGYRO_vs_CGYRO':
        errors.extend(validate_options(settings))
    try:
        tol = float(settings.get('error_tolerance', 0.01))
        if not math.isfinite(tol) or tol <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors.append('Relative fluctuation tolerance must be finite and > 0.')
    style = state.get('style', {})
    for key, low, high in [('font_size', 6, 30), ('legend_font_size', 5, 24),
                           ('line_width', .2, 8), ('figure_width', 0, 40), ('figure_height', 0, 30)]:
        try:
            value = float(style.get(key, STYLE_DEFAULTS[key]))
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError
            if key.startswith('figure_') and value != 0 and value < 3:
                raise ValueError
        except (TypeError, ValueError):
            errors.append('{} is outside the supported range.'.format(key))
    if settings.get('plot_log_y', None):
        warnings.append('Log Y hides zero/negative values, including stable gamma and signed omega.')
    return {'mode': mode, 'errors': errors, 'warnings': warnings,
            'summary': 'Ready to load selected curves.' if not errors else 'Selection needs attention.'}
