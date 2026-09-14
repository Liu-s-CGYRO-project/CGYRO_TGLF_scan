"""Shared plot-option validation with no dependency on GUI or result readers.

Import these functions while OMFIT loads the page. Saved GUI callbacks retain
them after execGlobLoc removes the OMFIT library importer and module cache.
"""
from builtins import SyntaxError, TypeError, ValueError, all, dict, float, hasattr, isinstance, list, str
import ast
import math
import re

__all__ = ['is_gamma_ratio_plot_mode', 'parse_float_list_text', 'validate_options']


def is_gamma_ratio_plot_mode(plot_mode):
    """True when selected plot mode is gamma-ratio mode (with legacy label support)."""
    mode_txt = str(plot_mode).strip()
    return mode_txt in ('Plot γ/γ_ref', 'Plot 纬/纬_ref')


def parse_float_list_text(text):
    """Accept GUI text/list/scalar values; never turn invalid input into 'all ky'."""
    if text is None or isinstance(text, str) and not text.strip():
        return []
    if isinstance(text, str):
        try:
            text = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            text = [item for item in re.split(r'[\s,]+', text.strip()) if item]
    if not hasattr(text, '__iter__') or isinstance(text, str):
        text = [text]
    try:
        values = [float(item) for item in text]
    except (TypeError, ValueError):
        raise ValueError('ky values must be finite numbers, separated by commas') from None
    if not all(math.isfinite(value) for value in values):
        raise ValueError('ky values must be finite numbers')
    return list(dict.fromkeys(values))


def validate_options(settings):
    """Check active plot controls without loading any calculation data."""
    if settings.get('linear_export_now', None):
        return []
    mode = settings.get('plot_mode', 'Plot 2D')
    errors = []
    try:
        if mode == 'Plot single ky':
            parse_float_list_text(settings.get('single_ky_values', ''))
        elif mode == 'Plot eigen ball' and settings.get('eigen_ky_mode', None) == 'single ky':
            if not parse_float_list_text(settings.get('eigen_ky_values', '')):
                raise ValueError('Enter at least one ky value for the eigenfunction')
        elif is_gamma_ratio_plot_mode(mode):
            reference = settings.get('gamma_ref_value', '')
            if reference is not None and str(reference).strip() and not math.isfinite(float(reference)):
                raise ValueError('Reference scan value must be finite')
            if settings.get('gamma_ref_mode', None) == 'single ky' and not parse_float_list_text(settings.get('gamma_ref_ky_values', '')):
                raise ValueError('Enter at least one ky value for the growth-rate ratio')
        elif mode not in ('Plot 2D', 'Plot 3D', 'Plot eigen ball'):
            raise ValueError('Choose a supported CGYRO plot mode')
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    return errors
