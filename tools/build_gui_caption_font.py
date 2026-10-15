"""Build the tiny licensed font subset for the two GUI sort captions.

This is a resource build, not an application or regression-test entry point.
The original Noto font is an external build input; only nine characters are
embedded in the OMFIT project, with the original OFL license included.
"""
import argparse
import base64
import hashlib
from io import BytesIO
from pathlib import Path
import textwrap
from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'f8d157532fbfaeda587e826d4cd5b21a49186f7c'
SOURCE_SHA256 = '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b'
LICENSE_SHA256 = '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2'
TEXT = '图例排序关键词 = '


def build(source, license_path):
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unexpected upstream font bytes')
    license_data = license_path.read_bytes()
    if hashlib.sha256(license_data).hexdigest() != LICENSE_SHA256:
        raise ValueError('Unexpected upstream license bytes')
    font = TTFont(source, recalcTimestamp=False)
    options = subset.Options()
    options.layout_features = []
    options.desubroutinize = True
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17]
    options.name_languages = [0x409]
    options.drop_tables += ['BASE', 'vhea', 'vmtx', 'DSIG']
    operation = subset.Subsetter(options=options)
    operation.populate(text=TEXT)
    operation.subset(font)
    # Identify this as a modified subset, preserving original copyright/license.
    names = {1: 'CGYRO Sort Caption SC', 2: 'Regular', 3: 'CGYRO Sort Caption SC 1.0',
             4: 'CGYRO Sort Caption SC Regular', 6: 'CGYROSortCaptionSC-Regular',
             16: 'CGYRO Sort Caption SC', 17: 'Regular'}
    for entry in font['name'].names:
        if entry.nameID in names:
            entry.string = names[entry.nameID].encode(entry.getEncoding())
    if 'CFF ' in font:
        cff = font['CFF '].cff
        cff.fontNames = [names[6]]
        cff.topDictIndex[0].FamilyName = names[1]
        cff.topDictIndex[0].FullName = names[4]
    buffer = BytesIO()
    font.save(buffer)
    data = buffer.getvalue()
    cmap = TTFont(BytesIO(data)).getBestCmap()
    if set(map(ord, TEXT)) != set(cmap):
        raise ValueError('Font subset character coverage mismatch')
    encoded = base64.b85encode(data).decode('ascii')
    payload = '\n'.join("    b'" + part + "'" for part in textwrap.wrap(encoded, width=96, break_on_hyphens=False))
    module = '''"""Modified Noto Sans CJK SC subset for the project's two sort captions.

Original font: https://github.com/notofonts/noto-cjk
Copyright 2014-2021 Adobe (http://www.adobe.com/), with Reserved Font Name
Source. Licensed under SIL Open Font License 1.1; see DOCS/FONT_LICENSE.txt.
Rebuild with tools/build_gui_caption_font.py and the pinned upstream inputs.
"""
UPSTREAM_REVISION = {!r}
UPSTREAM_SHA256 = {!r}
FONT_SHA256 = {!r}
FONT_B85 = (
{}
)
'''.format(REVISION, SOURCE_SHA256, hashlib.sha256(data).hexdigest(), payload)
    target = ROOT / 'CGYRO_TGLF_scan/LIB/OMFITlib_gui_caption_font.py'
    target.write_text(module, encoding='utf-8', newline='\n')
    (ROOT / 'CGYRO_TGLF_scan/DOCS/FONT_LICENSE.txt').write_bytes(license_data)
    return dict(bytes=len(data), characters=sorted(cmap), sha256=hashlib.sha256(data).hexdigest(),
                module=str(target), upstream_revision=REVISION)


if __name__ == '__main__':
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--license', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.license), ensure_ascii=False, indent=2))
