"""Encode the pinned, unmodified open plotting fonts for OMFIT portability.

Download the files and licenses listed in plot_fonts_sources.json to --source.
The build is offline and refuses font or license bytes with different hashes.
No font modification, subsetting, OS installation or application run is used.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]
SOURCES = Path(__file__).with_name('plot_fonts_sources.json')


def build(source):
    manifest = json.loads(SOURCES.read_text(encoding='utf-8'))
    resources = {}
    for filename, specification in manifest['files'].items():
        data = (source / filename).read_bytes()
        if hashlib.sha256(data).hexdigest() != specification['sha256']:
            raise ValueError('Unexpected upstream font or license: ' + filename)
        resources[filename] = data
    lines = ['"""Original open fonts, compressed for OMFIT project transport.',
             '', 'Source Han Serif: Adobe, SIL OFL 1.1.',
             'Liberation Sans: Google / Red Hat, SIL OFL 1.1.',
             'See DOCS/PLOT_FONTS_LICENSE.txt for full notices and source URLs.',
             'Rebuild with tools/build_plot_fonts.py; no font bytes are modified.',
             '"""']
    bundle_id = hashlib.sha256(''.join(manifest['files'][face['filename']]['sha256']
                                      for face in manifest['faces']).encode('ascii')).hexdigest()
    lines.extend(['BUNDLE_ID = ' + repr(bundle_id),
                  'DEFAULT_FONTS = ' + repr(manifest['defaults']), 'FONT_ASSETS = ('])
    total = 0
    for face in manifest['faces']:
        filename = face['filename']
        data = resources[filename]
        if not data.startswith((b'OTTO', b'\x00\x01\x00\x00')):
            raise ValueError('Unsupported upstream font format: ' + filename)
        encoded = base64.b85encode(zlib.compress(data, 9)).decode('ascii')
        total += len(data)
        lines.append('    {')
        for key in ('filename', 'family', 'style', 'weight'):
            lines.append('        ' + repr(key) + ': ' + repr(face[key]) + ',')
        lines.append("        'sha256': " + repr(manifest['files'][filename]['sha256']) + ',')
        lines.append("        'payload': (")
        lines.extend("            b'" + encoded[start:start + 8192] + "'" for start in range(0, len(encoded), 8192))
        lines.extend(['        ),', '    },'])
    lines.append(')')
    (ROOT / 'CGYRO_TGLF_scan/LIB/OMFITlib_plot_font_data.py').write_text(
        '\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    notice = ['Bundled plotting fonts: original, unmodified upstream files.',
              'No Microsoft SimSun or Arial font files are included.',
              'The following SIL OFL 1.1 licenses apply to these font resources.', '']
    for name, specification in manifest['files'].items():
        notice.extend([name, 'Source: ' + specification['url'], 'SHA-256: ' + specification['sha256'], ''])
    for face in manifest['faces']:
        notice.extend([face['filename']] + face['copyright'] + [''])
    for name in manifest['licenses']:
        notice.extend(['=' * 72, name, '=' * 72, resources[name].decode('utf-8'), ''])
    (ROOT / 'CGYRO_TGLF_scan/DOCS/PLOT_FONTS_LICENSE.txt').write_text(
        '\n'.join(notice), encoding='utf-8', newline='\n')
    return dict(bundle_id=bundle_id, fonts=len(manifest['faces']), font_bytes=total, defaults=manifest['defaults'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source), indent=2))
