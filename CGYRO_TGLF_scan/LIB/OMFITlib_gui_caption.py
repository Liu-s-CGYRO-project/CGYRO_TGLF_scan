"""Draw the two sort captions with bundled glyphs on font-poor servers.

The native label text, field bindings and defaults stay intact. Only the
caption's pixels come from the small OFL font subset carried by this project.
"""
from builtins import int, max, round, str, tuple
import base64
from functools import lru_cache
from io import BytesIO
from OMFITlib_gui_caption_font import FONT_B85


CAPTIONS = ('图例排序', '排序关键词', '图例排序 = ', '排序关键词 = ')


@lru_cache(maxsize=8)
def _font(pixels):
    from PIL import ImageFont
    return ImageFont.truetype(BytesIO(base64.b85decode(FONT_B85)), pixels)


def caption_bitmap(text, pixels, foreground, background):
    """Create pixels independently of Tk/X11 font substitution."""
    from PIL import Image, ImageDraw
    scale = 3
    font = _font(max(1, int(pixels)) * scale)
    # Pillow 8+ provides getbbox; older OMFIT environments provide getsize.
    if hasattr(font, 'getbbox'):
        left, top, right, bottom = font.getbbox(text)
    else:
        right, bottom = font.getsize(text)
        left, top = 0, 0
    width = max(1, (right - left + 2 * scale + scale - 1) // scale)
    height = max(1, (bottom - top + 2 * scale + scale - 1) // scale)
    canvas = Image.new('RGB', (width * scale, height * scale), background)
    ImageDraw.Draw(canvas).text((scale - left, scale - top), text, font=font, fill=foreground)
    resampling = getattr(Image, 'Resampling', Image)
    return canvas.resize((width, height), resampling.LANCZOS)


def apply_sort_caption(widget, font, style, background):
    """Keep the original caption as text; pin its image to this widget's life."""
    text = str(widget.cget('text'))
    if text not in CAPTIONS:
        return
    from PIL import ImageTk
    size = font.actual('size')
    pixels = max(1, int(round(size * widget.winfo_fpixels('1p')))) if size > 0 else max(1, -size)
    foreground = style.lookup(widget.cget('style') or 'TLabel', 'foreground') or '#000000'
    foreground = tuple(value // 257 for value in widget.winfo_rgb(foreground))
    background = tuple(value // 257 for value in widget.winfo_rgb(background))
    bitmap = caption_bitmap(text, pixels, foreground, background)
    photo = ImageTk.PhotoImage(bitmap, master=widget)
    widget.configure(image=photo, compound='none')
    widget._cgyro_caption_image = photo
