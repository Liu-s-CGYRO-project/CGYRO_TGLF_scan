"""Register the unchanged plotting fonts from the independent shared cache."""
from builtins import all, id, set, str
import threading
from matplotlib import font_manager
from OMFITlib_plot_font_data import FONT_ASSETS
from OMFITlib_font_ui import ensure_fonts


_lock = threading.RLock()
_registered = set()


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
            font_manager.fontManager.addfont(path)
            _registered.add(key)
