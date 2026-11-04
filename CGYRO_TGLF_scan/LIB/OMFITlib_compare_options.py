"""Shared plot-option validation with no dependency on GUI or result readers.

Import these functions while OMFIT loads the page. Saved GUI callbacks retain
them after execGlobLoc removes the OMFIT library importer and module cache.
"""
from builtins import SyntaxError, TypeError, ValueError, all, dict, float, hasattr, isinstance, list, str
import ast
import math
import re

# These are scientific/statistical defaults, shared by initialization, reset
# widgets and legacy missing-key reads. Changing one must not change only a UI.
STAT_DEFAULTS = {'ave_window': 0.02, 'effnum': 5, 'error_tolerance': 0.01}

__all__ = ['STAT_DEFAULTS', 'is_gamma_ratio_plot_mode', 'parse_float_list_text', 'validate_options']


def is_gamma_ratio_plot_mode(plot_mode):
    """True when selected plot mode is gamma-ratio mode (with legacy label support)."""
    mode_txt = str(plot_mode).strip()
    return mode_txt in ('Plot γ/γ_ref', 'Plot 纬/纬_ref')


def parse_float_list_text(text, unique=True):
    """Accept numeric GUI text/list/scalars; never ignore malformed selections."""
    if text is None or isinstance(text, str) and not text.strip():
        return []
    if isinstance(text, str):
        try:
            text = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            text = text.strip()
            # OMFIT can persist NumPy's whitespace-separated array display.
            if text.startswith('[') and text.endswith(']'):
                text = text[1:-1]
            text = [item for item in re.split(r'[\s,]+', text) if item]
    if hasattr(text, 'keys'):
        raise ValueError('Values must be a numeric list, not a mapping')
    if not hasattr(text, '__iter__') or isinstance(text, str):
        text = [text]
    try:
        values = [float(item) for item in text
                  if item is not None and not (isinstance(item, str) and not item.strip())]
    except (TypeError, ValueError):
        raise ValueError('Values must be finite numbers, separated by commas or spaces') from None
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Values must be finite numbers')
    return list(dict.fromkeys(values)) if unique else values


def validate_options(settings):
    """Check active plot controls without loading any calculation data."""
    if settings.get('linear_export_now', None):
        return []
    mode = settings.get('plot_mode', 'Plot 2D')
    errors = []
    try:
        if mode == 'Plot single ky':
            parse_float_list_text(settings.get('single_ky_values', ''))
        elif mode == 'Plot time traces':
            parse_float_list_text(settings.get('time_ky_values', ''))
        elif mode == 'Plot eigen ball' and settings.get('eigen_ky_mode', None) == 'single ky':
            if not parse_float_list_text(settings.get('eigen_ky_values', '')):
                raise ValueError('Enter at least one ky value for the eigenfunction')
        elif is_gamma_ratio_plot_mode(mode):
            reference = '' if settings.get('cgyro_view', '') == '收敛测试' else settings.get('gamma_ref_value', '')
            if reference is not None and str(reference).strip() and not math.isfinite(float(reference)):
                raise ValueError('Reference scan value must be finite')
            if settings.get('gamma_ref_mode', None) == 'single ky' and not parse_float_list_text(settings.get('gamma_ref_ky_values', '')):
                raise ValueError('Enter at least one ky value for the growth-rate ratio')
        elif mode not in ('Plot 2D', 'Plot 3D', 'Plot eigen ball'):
            raise ValueError('Choose a supported CGYRO plot mode')
    except (TypeError, ValueError) as exc:
        prefix = 'Invalid ky values: ' if mode in ('Plot single ky', 'Plot time traces', 'Plot eigen ball') else ''
        errors.append(prefix + str(exc))
    return errors
