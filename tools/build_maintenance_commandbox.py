"""Embed a verified code-only build in a single offline Command Box updater."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'OMFITtemplates/LIB'))
from OMFITlib_template_archive import Project


def build(project, output):
    data = Path(project).read_bytes()
    if not 0 < len(data) < 2 * 1024 * 1024:
        raise ValueError('Expected a code-only project smaller than 2 MiB')
    with Project(project) as archive:
        archive.require_entry_first()
        if set(archive.roots) != {'CGYRO_TGLF_scan', 'OMFITtemplates'}:
            raise ValueError('Both project and matching manager must be included')
        if any(kind == 'data' for kind in archive.ownership(archive.roots).values()):
            raise ValueError('Refusing to embed calculation data')
        metadata = json.loads(archive.read('PROJECT_CONTENTS.json'))
        if archive.z.testzip() is not None:
            raise ValueError('CRC failure')
    package = dict(version=metadata['version'], bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    source = Path(__file__).with_name('maintenance_commandbox.py').read_text(encoding='utf-8')
    source = source.replace('PACKAGE = None  # Filled by build_maintenance_commandbox.py.',
                            'PACKAGE = ' + repr(package))
    encoded = base64.b85encode(data).decode('ascii')
    payload = 'PAYLOAD = (\n' + ''.join('    b' + repr(line) + '\n' for line in textwrap.wrap(
        encoded, 100, break_on_hyphens=False, drop_whitespace=False)) + ')'
    source = source.replace('PAYLOAD = None  # Filled by build_maintenance_commandbox.py.', payload)
    ast.parse(source, feature_version=(3, 9))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(source)
    return dict(output=str(output), bytes=output.stat().st_size,
                sha256=hashlib.sha256(output.read_bytes()).hexdigest(), package=package)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.project, args.output), indent=2))
