"""Independent Chinese/Latin plot fonts, including delayed draw and export."""
from builtins import dict, id, int, next, str, tuple
from pathlib import Path
import re
import matplotlib as mpl
from matplotlib import font_manager
from OMFITlib_plot_font_assets import register_bundled_fonts
from OMFITlib_plot_font_data import BUNDLE_ID, DEFAULT_FONTS


FONT_DEFAULTS = dict(DEFAULT_FONTS, font_file='', chinese_font_file='')
FONT_PROFILE = 'plot-fonts-v2:' + BUNDLE_ID
_file_names = {}


def initialize_fonts(style):
    """Migrate former defaults once, preserving deliberate custom choices."""
    if style.get('plot_font_profile', '') != FONT_PROFILE:
        if style.get('font_family', '') in ('', 'DejaVu Sans', 'Noto Sans CJK SC', 'Arial'):
            style['font_family'] = FONT_DEFAULTS['font_family']
        if style.get('chinese_font_family', '') in ('', 'SimSun', '宋体', 'Noto Sans CJK SC'):
            style['chinese_font_family'] = FONT_DEFAULTS['chinese_font_family']
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
            font_manager.fontManager.addfont(str(path))
            _file_names[key] = font_manager.FontProperties(fname=str(path)).get_name()
        return _file_names[key]
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(label + '文件无法加载：' + str(path)) from exc


def font_families(style):
    """Use Latin first, then the configured Chinese font for missing glyphs."""
    version = re.match(r'^(\d+)\.(\d+)', mpl.__version__)
    if version and tuple(int(part) for part in version.groups()) < (3, 6):
        raise ValueError('中英文混排需要 Matplotlib 3.6 或以上版本。')
    english_file = _file_family(style.get('font_file', ''), '英文字体')
    chinese_file = _file_family(style.get('chinese_font_file', ''), '中文字体')
    english = english_file or str(style['font_family']).strip()
    chinese = chinese_file or str(style['chinese_font_family']).strip()
    register_bundled_fonts(tuple(family for family, custom in ((english, english_file), (chinese, chinese_file)) if not custom))
    available = {font.name.casefold(): font.name for font in font_manager.fontManager.ttflist}
    aliases = {'simsun': ('SimSun', '宋体'), '宋体': ('SimSun', '宋体'), 'arial': ('Arial', 'ArialMT')}
    selected = []
    for label, requested in (('英文', english), ('中文', chinese)):
        candidates = aliases.get(requested.casefold(), (requested,))
        actual = next((available[name.casefold()] for name in candidates if name.casefold() in available), None)
        if actual is None and requested in ('sans-serif', 'serif', 'monospace', 'cursive', 'fantasy'):
            filename = font_manager.findfont(font_manager.FontProperties(family=[requested]), fallback_to_default=False)
            actual = font_manager.FontProperties(fname=filename).get_name()
        if actual is None:
            raise ValueError('未找到绘图' + label + '字体 ' + requested + '；请在“全局样式”指定对应的字体文件。')
        if actual not in selected:
            selected.append(actual)
    return selected


def font_rc(style):
    """Snapshot fonts for text, math, and vector exports of this figure."""
    family = font_families(style)
    english = family[0]
    rc = {'font.family': family, 'font.serif': family, 'font.sans-serif': family,
          'mathtext.fontset': 'custom', 'mathtext.rm': english,
          'mathtext.it': english + ':italic', 'mathtext.bf': english + ':bold',
          'mathtext.sf': english, 'mathtext.tt': mpl.rcParams['mathtext.tt'],
          'mathtext.cal': mpl.rcParams['mathtext.cal'],
          'mathtext.fallback': 'stix', 'pdf.fonttype': 42, 'ps.fonttype': 42,
          'svg.fonttype': 'path'}
    if 'mathtext.bfit' in mpl.rcParams:
        rc['mathtext.bfit'] = english + ':bold:italic'
    return rc


def with_font_rc(function, config, *args, **kwargs):
    """Keep font settings active when Tk draws later or a save dialog exports."""
    with mpl.rc_context(config):
        return function(*args, **kwargs)
