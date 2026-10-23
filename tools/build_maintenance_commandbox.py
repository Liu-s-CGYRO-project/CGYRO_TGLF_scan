"""Embed a verified code-only build in a single offline Command Box updater."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import textwrap
from release_policy import MAX_PROJECT_PACKAGE_BYTES

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'OMFITtemplates/LIB'))
from OMFITlib_template_archive import Project
from OMFITlib_template_service import new_file


def build(project, output):
    data = Path(project).read_bytes()
    if not 0 < len(data) < MAX_PROJECT_PACKAGE_BYTES:
        raise ValueError('Expected a code-only project smaller than 2 MiB')
    # Project intentionally accepts native paths. Validate a private copy of
    # the captured payload so replacing the input cannot substitute unverified
    # bytes (or calculation data) for the archive that passed these checks.
    with tempfile.TemporaryDirectory(prefix='omfit-build-maintenance-') as directory:
        snapshot = Path(directory) / 'code.zip'
        snapshot.write_bytes(data)
        with Project(snapshot) as archive:
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
    package_marker = 'PACKAGE = None  # Filled by build_maintenance_commandbox.py.'
    payload_marker = 'PAYLOAD = None  # Filled by build_maintenance_commandbox.py.'
    if source.count(package_marker) != 1 or source.count(payload_marker) != 1:
        raise ValueError('Unexpected maintenance source markers')
    source = source.replace(package_marker, 'PACKAGE = ' + repr(package))
    encoded = base64.b85encode(data).decode('ascii')
    payload = 'PAYLOAD = (\n' + ''.join('    b' + repr(line) + '\n' for line in textwrap.wrap(
        encoded, 100, break_on_hyphens=False, drop_whitespace=False)) + ')'
    source = source.replace(payload_marker, payload)
    ast.parse(source, feature_version=(3, 9))
    output = Path(output)
    # An Abort or disk error must not leave a truncated script looking usable.
    with new_file(output) as temporary:
        temporary.write_bytes(source.encode('utf-8'))
    return dict(output=str(output), bytes=output.stat().st_size,
                sha256=hashlib.sha256(output.read_bytes()).hexdigest(), package=package)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.project, args.output), indent=2))
