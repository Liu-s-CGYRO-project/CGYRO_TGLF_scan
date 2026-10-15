"""Validate, cache and register the plotting fonts carried by an install pack."""
from builtins import id, set, str
import base64
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import zlib
from matplotlib import font_manager
from OMFITlib_plot_font_data import FONT_ASSETS


_lock = threading.RLock()
_registered = set()
_paths = {}


def _write_font(directory, asset, data):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    suffix = Path(asset['filename']).suffix.lower()
    if suffix not in ('.ttf', '.otf', '.ttc'):
        raise ValueError('随包字体格式不受支持：' + asset['filename'])
    path = directory / (asset['sha256'] + suffix)
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == asset['sha256']:
        return str(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix=suffix, delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
        os.replace(temporary, path)
        return str(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def register_bundled_fonts():
    """Load all supplied faces once; explicit file settings may override them."""
    with _lock:
        for asset in FONT_ASSETS:
            key = (id(font_manager.fontManager), asset['sha256'])
            if key in _registered:
                continue
            path = _paths.get(asset['sha256'], '')
            if not path or not Path(path).is_file():
                data = zlib.decompress(base64.b85decode(asset['payload']))
                if hashlib.sha256(data).hexdigest() != asset['sha256']:
                    raise ValueError('随包字体校验失败：' + asset['filename'])
                cache = Path(os.environ.get('XDG_CACHE_HOME') or os.environ.get('LOCALAPPDATA') or
                             (Path.home() / '.cache')) / 'omfit-cgyro' / 'fonts'
                try:
                    path = _write_font(cache, asset, data)
                except OSError:
                    path = _write_font(Path(tempfile.mkdtemp(prefix='omfit-plot-fonts-')), asset, data)
                _paths[asset['sha256']] = path
            font_manager.fontManager.addfont(path)
            _registered.add(key)
