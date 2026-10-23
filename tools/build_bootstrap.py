"""Bind the Command box bootstrap to a statically reviewed manager archive."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
from release_policy import MAX_MANAGER_BOOTSTRAP_BYTES

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'OMFITtemplates/LIB'))
from OMFITlib_template_service import new_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manager', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = args.manager.read_bytes()
    if not 0 < len(data) < MAX_MANAGER_BOOTSTRAP_BYTES:
        raise ValueError('Use a manager package below 1 MB')
    # Identity and validation must describe the same captured bytes even when
    # another build replaces the input path while this generator is running.
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.testzip() is not None:
            raise ValueError('Manager ZIP CRC mismatch')
        tree = ast.parse(archive.read('OMFITtemplates/LIB/OMFITlib_template_versions.py'), feature_version=(3, 9))
    versions = [ast.literal_eval(item.value) for item in tree.body if isinstance(item, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'MANAGER_VERSION' for target in item.targets)]
    if len(versions) != 1 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', versions[0]):
        raise ValueError('Invalid manager version')
    version = versions[0]
    if args.manager.name != 'OMFIT_template_manager_' + version + '.omfit.zip':
        raise ValueError('Unexpected manager archive name')
    manager = dict(repository='Liu-s-CGYRO-project/CGYRO_TGLF_scan', version=version,
                   name=args.manager.name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    source = Path(__file__).with_name('bootstrap_manager.py').read_text(encoding='utf-8')
    marker = 'MANAGER = None  # Filled by build_bootstrap.py in the published asset.'
    if source.count(marker) != 1:
        raise ValueError('Unexpected bootstrap metadata marker')
    source = source.replace(marker, 'MANAGER = ' + repr(manager))
    ast.parse(source, feature_version=(3, 9))
    with new_file(args.output) as temporary:
        temporary.write_bytes(source.encode('utf-8'))
    payload = args.output.read_bytes()
    print(json.dumps(dict(path=str(args.output), bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                         manager=manager)), flush=True)


if __name__ == '__main__':
    main()
