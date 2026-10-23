"""Build a standalone first-deploy script bound to reviewed release packages."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile
from release_policy import MAX_PROJECT_PACKAGE_BYTES

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'OMFITtemplates/LIB'))
from OMFITlib_template_service import new_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    template_data = args.template.read_bytes()
    with zipfile.ZipFile(io.BytesIO(template_data)) as archive:
        template = json.loads(archive.read('manifest.json'))
        if archive.testzip() is not None:
            raise ValueError('Template CRC mismatch')
    version = template['version']
    if (template.get('author'), template.get('id'), template.get('examples')) != ('tdxy-liu', 'cgyro-tglf', False):
        raise ValueError('Use the reviewed code-only cgyro-tglf template')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('Expected a stable project release version')
    project_data = args.project.read_bytes()
    with zipfile.ZipFile(io.BytesIO(project_data)) as archive:
        metadata = json.loads(archive.read('PROJECT_CONTENTS.json'))
        if archive.testzip() is not None:
            raise ValueError('Project CRC mismatch')
    if metadata['version'] != version:
        raise ValueError('Project and template versions differ')
    release = dict(repository='Liu-s-CGYRO-project/CGYRO_TGLF_scan', version=version)
    # Reuse the verified snapshots, not paths a parallel build could replace.
    for kind, path, expected, data in (
        ('project', args.project, 'CGYRO_TGLF_scan_code_only_' + version + '.zip', project_data),
        ('template', args.template, 'tdxy-liu__cgyro-tglf__' + version + '.omfittpl.zip', template_data),
    ):
        if path.name != expected or not 0 < len(data) < MAX_PROJECT_PACKAGE_BYTES:
            raise ValueError('Unexpected release package: ' + str(path))
        release[kind] = dict(name=expected, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    source = Path(__file__).with_name('deploy_project.py').read_text(encoding='utf-8')
    marker = 'RELEASE = None  # Filled by build_deployer.py in the published standalone asset.'
    if source.count(marker) != 1:
        raise ValueError('Unexpected deployment source marker')
    source = source.replace(marker, 'RELEASE = ' + repr(release))
    limit_marker = 'LIMIT = None  # Filled from release_policy.py by build_deployer.py.'
    if source.count(limit_marker) != 1:
        raise ValueError('Unexpected deployment size-policy marker')
    source = source.replace(limit_marker, 'LIMIT = ' + repr(MAX_PROJECT_PACKAGE_BYTES))
    ast.parse(source, feature_version=(3, 9))
    with new_file(args.output) as temporary:
        # Bytes preserve LF on Windows too, including the Linux shebang.
        temporary.write_bytes(source.encode('utf-8'))
    data = args.output.read_bytes()
    print(json.dumps(dict(path=str(args.output), name=args.output.name, bytes=len(data),
                         sha256=hashlib.sha256(data).hexdigest(), release=release)), flush=True)


if __name__ == '__main__':
    main()
