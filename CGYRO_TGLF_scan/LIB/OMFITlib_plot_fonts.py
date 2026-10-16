"""English plot fonts, including legacy Matplotlib, delayed draw and export."""
from builtins import callable, dict, getattr, id, isinstance, next, str
from pathlib import Path
import matplotlib as mpl
from matplotlib import font_manager
from OMFITlib_plot_font_assets import register_bundled_fonts, register_font_file
from OMFITlib_plot_font_data import BUNDLE_ID, DEFAULT_FONTS
from OMFITlib_plot_labels import apply_english_labels


FONT_DEFAULTS = dict(font_family=DEFAULT_FONTS['font_family'], font_file='')
FONT_PROFILE = 'plot-fonts-v3-english:' + BUNDLE_ID
_file_names = {}


def initialize_fonts(style):
    """Migrate former defaults once, preserving deliberate custom choices."""
    if style.get('plot_font_profile', '') != FONT_PROFILE:
        if style.get('font_family', '') in ('', 'DejaVu Sans', 'Noto Sans CJK SC', 'Arial', 'Source Han Serif CN', 'SimSun', '宋体'):
            style['font_family'] = FONT_DEFAULTS['font_family']
        for key, value in FONT_DEFAULTS.items():
            style.setdefault(key, value)
        style['plot_font_profile'] = FONT_PROFILE


def _file_family(value, label):
    if value is None or not str(value).strip():
        return None
    path = Path(str(value).strip()).expanduser()
    try:
        path = path.resolve(strict=True)
        stat = path.stat()
        key = (id(font_manager.fontManager), str(path), stat.st_mtime_ns, stat.st_size)
        if key not in _file_names:
            register_font_file(path)
            _file_names[key] = font_manager.FontProperties(fname=str(path)).get_name()
        return _file_names[key]
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError('Cannot load ' + label + ' font file: ' + str(path)) from exc


def font_families(style):
    """English figures need one Latin family, with no CJK/version prerequisite."""
    english_file = _file_family(style.get('font_file', ''), 'Latin')
    english = english_file or str(style['font_family']).strip()
    if not english_file:
        register_bundled_fonts((english,))
    available = {font.name.casefold(): font.name for font in font_manager.fontManager.ttflist}
    candidates = ('Arial', 'ArialMT') if english.casefold() == 'arial' else (english,)
    actual = next((available[name.casefold()] for name in candidates if name.casefold() in available), None)
    if actual is None and english in ('sans-serif', 'serif', 'monospace', 'cursive', 'fantasy'):
        filename = font_manager.findfont(font_manager.FontProperties(family=[english]), fallback_to_default=False)
        actual = font_manager.FontProperties(fname=filename).get_name()
    if actual is None:
        raise ValueError('Plot font not found: ' + english + '. Select its font file in Global style.')
    return [actual]


def font_rc(style):
    """Snapshot fonts for text, math, and vector exports of this figure."""
    family = font_families(style)
    english = family[0]
    rc = {'font.family': family, 'font.serif': family, 'font.sans-serif': family,
          'mathtext.fontset': 'custom', 'mathtext.rm': english,
          'mathtext.it': english + ':italic', 'mathtext.bf': english + ':bold',
          'mathtext.sf': english, 'mathtext.tt': mpl.rcParams['mathtext.tt'],
          'mathtext.cal': mpl.rcParams['mathtext.cal'],
          'pdf.fonttype': 42, 'ps.fonttype': 42,
          'svg.fonttype': 'path'}
    if 'mathtext.fallback' in mpl.rcParams:
        rc['mathtext.fallback'] = 'stix'
    elif 'mathtext.fallback_to_cm' in mpl.rcParams:
        rc['mathtext.fallback_to_cm'] = True
    if 'mathtext.bfit' in mpl.rcParams:
        rc['mathtext.bfit'] = english + ':bold:italic'
    return rc


def apply_text_fonts(figure, config):
    """One Latin face for English labels on both old and current renderers."""
    from matplotlib.text import Text
    apply_english_labels(figure)
    family = config['font.family']
    for text in figure.findobj(match=Text):
        text.set_fontfamily(family)
        set_math = getattr(text, 'set_math_fontfamily', None)
        if callable(set_math):
            set_math('custom')


def with_font_rc(function, config, *args, **kwargs):
    """Keep font settings active when Tk draws later or a save dialog exports."""
    with mpl.rc_context(config):
        from matplotlib.figure import Figure
        figure = getattr(function, '__self__', None)
        if isinstance(figure, Figure):
            apply_text_fonts(figure, config)
        return function(*args, **kwargs)
