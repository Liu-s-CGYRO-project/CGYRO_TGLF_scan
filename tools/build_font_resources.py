"""Build independent, reproducible original-font packs and small manifests.

No GUI, rendering, application activation or regression test is run. Font
bytes and complete upstream licenses are preserved and checked before packing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'Liu-s-CGYRO-project/CGYRO_TGLF_scan'
TAG = 'omfit-fonts/v1'
GUI_SHA256 = '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b'
GUI_LICENSE = '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2'


def checked(path, digest):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Unexpected upstream bytes: ' + str(path))
    return data


def specification(data):
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def bundle(kind, resources, fonts, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    members = {name: specification(data) for name, data in resources.items()}
    identity = dict(format='omfit-font-bundle-v1', kind=kind, files=members)
    identity_bytes = (json.dumps(identity, sort_keys=True, indent=2) + '\n').encode('utf-8')
    resources = dict(resources, **{'font_bundle.json': identity_bytes})
    members['font_bundle.json'] = specification(identity_bytes)
    name = 'OMFIT_fonts_' + kind + '_v1.zip'
    path = output / name
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for member, data in sorted(resources.items()):
            info = zipfile.ZipInfo(member)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Font archive CRC mismatch')
    record = dict(specification(path.read_bytes()), filename=name,
                  url='https://github.com/' + REPOSITORY + '/releases/download/' + TAG + '/' + name,
                  members=members, fonts=fonts)
    return record, path


def build(gui_source, gui_license, plot_source, output):
    gui_data = checked(gui_source, GUI_SHA256)
    gui_notice = checked(gui_license, GUI_LICENSE)
    sources = json.loads((ROOT / 'tools/plot_fonts_sources.json').read_bytes())
    plot_resources = {name: checked(Path(plot_source) / name, spec['sha256'])
                      for name, spec in sources['files'].items()}
    gui_name = 'NotoSansCJKsc-Regular.otf'
    gui_font = dict(specification(gui_data), filename=gui_name, family='Noto Sans CJK SC',
                    style='normal', weight=400, bundle='gui')
    fonts = {gui_name: gui_font}
    for face in sources['faces']:
        name = face['filename']
        fonts[name] = dict(face, **specification(plot_resources[name]), bundle='plot')
    gui_pack, gui_path = bundle('gui', {gui_name: gui_data, 'Noto-OFL.txt': gui_notice}, [gui_name], output)
    plot_pack, plot_path = bundle('plot', plot_resources, [face['filename'] for face in sources['faces']], output)
    packs = dict(gui=gui_pack, plot=plot_pack)
    module = ('"""Pinned original fonts downloaded once into the shared user cache.\n\n'
              'Licenses: DOCS/FONT_LICENSE.txt and DOCS/PLOT_FONTS_LICENSE.txt.\n'
              'Rebuild offline with tools/build_font_resources.py.\n"""\n'
              'FONT_BUNDLES = ' + repr(packs) + '\nFONT_FILES = ' + repr(fonts) + '\n')
    gui_module = ('"""GUI font identity; font bytes live in the independent font pack."""\n'
                  'FONT_FAMILY = \'Noto Sans CJK SC\'\nFONT_FILENAME = ' + repr(gui_name) +
                  '\nFONT_SHA256 = ' + repr(GUI_SHA256) + '\n')
    for module_name in ('CGYRO_TGLF_scan', 'OMFITtemplates'):
        lib = ROOT / module_name / 'LIB'
        (lib / 'OMFITlib_font_manifest.py').write_text(module, encoding='utf-8', newline='\n')
        (lib / 'OMFITlib_gui_font_data.py').write_text(gui_module, encoding='utf-8', newline='\n')
    bundle_id = hashlib.sha256(''.join(fonts[face['filename']]['sha256'] for face in sources['faces']).encode('ascii')).hexdigest()
    plot_module = ('"""Plot font identities; unchanged fonts are cached outside the project."""\n'
                   'BUNDLE_ID = ' + repr(bundle_id) + '\nDEFAULT_FONTS = ' + repr(sources['defaults']) +
                   '\nFONT_ASSETS = ' + repr(tuple(fonts[face['filename']] for face in sources['faces'])) + '\n')
    (ROOT / 'CGYRO_TGLF_scan/LIB/OMFITlib_plot_font_data.py').write_text(plot_module, encoding='utf-8', newline='\n')
    report = dict(fonts=fonts, bundles=packs, paths=[str(gui_path), str(plot_path)], font_bytes_embedded=0)
    (Path(output) / 'font_resources.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui-source', required=True, type=Path)
    parser.add_argument('--gui-license', required=True, type=Path)
    parser.add_argument('--plot-source', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    result = build(args.gui_source, args.gui_license, args.plot_source, args.output_dir)
    print(json.dumps(dict(paths=result['paths'], packs={key: value['bytes'] for key, value in result['bundles'].items()},
                          fonts=len(result['fonts']), font_bytes_embedded=0), indent=2))
