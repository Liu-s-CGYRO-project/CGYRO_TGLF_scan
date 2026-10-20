"""Build a standalone first-deploy script bound to reviewed release packages."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.template) as archive:
        template = json.loads(archive.read('manifest.json'))
    version = template['version']
    if (template.get('author'), template.get('id'), template.get('examples')) != ('tdxy-liu', 'cgyro-tglf', False):
        raise ValueError('Use the reviewed code-only cgyro-tglf template')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('Expected a stable project release version')
    with zipfile.ZipFile(args.project) as archive:
        metadata = json.loads(archive.read('PROJECT_CONTENTS.json'))
    if metadata['version'] != version:
        raise ValueError('Project and template versions differ')
    release = dict(repository='Liu-s-CGYRO-project/CGYRO_TGLF_scan', version=version)
    for kind, path, expected in (
        ('project', args.project, 'CGYRO_TGLF_scan_code_only_' + version + '.zip'),
        ('template', args.template, 'tdxy-liu__cgyro-tglf__' + version + '.omfittpl.zip'),
    ):
        data = path.read_bytes()
        if path.name != expected or not 0 < len(data) < 1000000:
            raise ValueError('Unexpected release package: ' + str(path))
        release[kind] = dict(name=expected, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    source = Path(__file__).with_name('deploy_project.py').read_text(encoding='utf-8')
    marker = 'RELEASE = None  # Filled by build_deployer.py in the published standalone asset.'
    if source.count(marker) != 1:
        raise ValueError('Unexpected deployment source marker')
    source = source.replace(marker, 'RELEASE = ' + repr(release))
    ast.parse(source, feature_version=(3, 9))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(source)
    data = args.output.read_bytes()
    print(json.dumps(dict(path=str(args.output), name=args.output.name, bytes=len(data),
                         sha256=hashlib.sha256(data).hexdigest(), release=release)), flush=True)


if __name__ == '__main__':
    main()
