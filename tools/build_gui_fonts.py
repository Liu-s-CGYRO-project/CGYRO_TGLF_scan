"""Embed the full licensed CJK font for both self-contained OMFIT modules.

Input: the pinned, unmodified official Noto Sans CJK SC Regular font and OFL
license. Runtime uses only Python's standard library and the native renderer.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import textwrap
import zlib

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'f8d157532fbfaeda587e826d4cd5b21a49186f7c'
SOURCE_SHA256 = '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b'
LICENSE_SHA256 = '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2'


def build(source, license_path):
    data = source.read_bytes()
    license_data = license_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unexpected upstream font bytes')
    if hashlib.sha256(license_data).hexdigest() != LICENSE_SHA256:
        raise ValueError('Unexpected upstream license bytes')
    encoded = base64.b85encode(zlib.compress(data, 9)).decode('ascii')
    # Older manager installers accept at most 8 MiB per incremental file.
    # Keep complete, original font bytes while transporting three small parts.
    parts = [encoded[start:start + 6 * 1024 ** 2] for start in range(0, len(encoded), 6 * 1024 ** 2)]
    if len(parts) != 3:
        raise ValueError('Unexpected pinned font part count')
    module = '''"""Full unmodified Noto Sans CJK SC Regular, encoded for OMFIT portability.

Source: https://github.com/notofonts/noto-cjk
Copyright 2014-2021 Adobe (http://www.adobe.com/), Reserved Font Name Source.
Licensed under SIL OFL 1.1; see DOCS/FONT_LICENSE.txt.
Rebuild with tools/build_gui_fonts.py and the pinned upstream inputs.
"""
from OMFITlib_gui_font_part1 import FONT_PART1
from OMFITlib_gui_font_part2 import FONT_PART2
from OMFITlib_gui_font_part3 import FONT_PART3
FONT_FAMILY = 'Noto Sans CJK SC'
UPSTREAM_REVISION = {!r}
FONT_SHA256 = {!r}
FONT_B85 = FONT_PART1 + FONT_PART2 + FONT_PART3
'''.format(REVISION, SOURCE_SHA256)
    gui_source = (ROOT / 'CGYRO_TGLF_scan/LIB/OMFITlib_gui_fonts.py').read_bytes()
    for name in ('CGYRO_TGLF_scan', 'OMFITtemplates'):
        module_root = ROOT / name
        (module_root / 'LIB/OMFITlib_gui_font_data.py').write_text(module, encoding='utf-8', newline='\n')
        for index, part in enumerate(parts, 1):
            chunks = '\n'.join("    b'" + part[start:start + 8192] + "'" for start in range(0, len(part), 8192))
            content = ('"""Unmodified Noto font transport part; see DOCS/FONT_LICENSE.txt."""\n'
                       'FONT_PART' + str(index) + ' = (\n' + chunks + '\n)\n')
            (module_root / ('LIB/OMFITlib_gui_font_part' + str(index) + '.py')).write_text(
                content, encoding='utf-8', newline='\n')
        (module_root / 'DOCS').mkdir(exist_ok=True)
        (module_root / 'DOCS/FONT_LICENSE.txt').write_bytes(license_data)
        (module_root / 'LIB/OMFITlib_gui_fonts.py').write_bytes(gui_source)
    return dict(font_bytes=len(data), compressed_bytes=len(zlib.compress(data, 9)), sha256=SOURCE_SHA256,
                modules=['CGYRO_TGLF_scan', 'OMFITtemplates'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--license', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.license), indent=2))
