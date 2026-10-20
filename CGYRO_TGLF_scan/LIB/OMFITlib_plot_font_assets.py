"""Register the unchanged plotting fonts from the independent shared cache."""
from builtins import RuntimeError, all, callable, getattr, id, set, str
import threading
from matplotlib import font_manager
from OMFITlib_plot_font_data import FONT_ASSETS
from OMFITlib_font_download_ui import ensure_fonts


_lock = threading.RLock()
_registered = set()


def register_font_file(path):
    """Register a face on both current and pre-addfont Matplotlib releases."""
    manager = font_manager.fontManager
    addfont = getattr(manager, 'addfont', None)
    if callable(addfont):
        addfont(str(path))
        return
    create = getattr(font_manager, 'createFontList', None)
    if not callable(create):
        raise RuntimeError('This Matplotlib font manager cannot register a font file: ' + str(path))
    entries = create([str(path)])
    if not entries:
        raise RuntimeError('Matplotlib could not read the font file: ' + str(path))
    manager.ttflist.extend(entries)
    clear = getattr(getattr(manager, '_findfont_cached', None), 'cache_clear', None)
    if callable(clear):
        clear()


def register_bundled_fonts(families=None):
    """Acquire default faces once; custom families or files need no font pack."""
    selected = [asset for asset in FONT_ASSETS if families is None or asset['family'] in families]
    if not selected:
        return
    if all((id(font_manager.fontManager), asset['sha256']) in _registered for asset in selected):
        return
    paths = ensure_fonts('plot')
    with _lock:
        for asset in selected:
            key = (id(font_manager.fontManager), asset['sha256'])
            if key in _registered:
                continue
            path = paths[asset['filename']]
            register_font_file(path)
            _registered.add(key)
