#!/usr/bin/env python3
"""Deploy a current OMFIT project from a saved ZIP using Python 3.9+ only.

The release asset embeds matching package sizes/digests. It uses no GitHub API,
does not import OMFIT or run expressions, and always writes a new project ZIP.
"""
import argparse
import ast
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib
from http.client import IncompleteRead, RemoteDisconnected
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from urllib import error, parse, request
import uuid
import zipfile

RELEASE = None  # Filled by build_deployer.py in the published standalone asset.
REPOSITORY = 'Liu-s-CGYRO-project/CGYRO_TGLF_scan'
GROUP = 'CGYRO_TGLF_scan'
LEGACY = ('CGYRO_scan', 'TGLF_scan', 'Transfer_tool')
RUNTIME = ('OMFITlib_template_archive', 'OMFITlib_template_versions', 'OMFITlib_template_service')
DEFAULT_PROXY = 'http://47.102.120.146:18889'
LIMIT = None  # Filled from release_policy.py by build_deployer.py.


class DeploymentError(ValueError):
    pass


class HTTPSRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if parse.urlsplit(newurl).scheme != 'https':
            raise DeploymentError('Download redirect is not HTTPS')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def download(kind, folder, args):
    if not isinstance(RELEASE, dict) or RELEASE.get('repository') != REPOSITORY:
        raise DeploymentError('Download omfit-deploy.py from a Release; source checkout use requires --template FILE')
    version = RELEASE.get('version', '')
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise DeploymentError('Invalid deployment release version')
    package = RELEASE[kind]
    expected = ('CGYRO_TGLF_scan_code_only_' + version + '.zip' if kind == 'project'
                else 'tdxy-liu__cgyro-tglf__' + version + '.omfittpl.zip')
    if (package.get('name') != expected or not 0 < package.get('bytes', 0) < LIMIT
            or not re.fullmatch(r'[a-f0-9]{64}', package.get('sha256', ''))):
        raise DeploymentError('Invalid embedded package identity or checksum')
    proxy = (request.ProxyHandler() if args.network == 'system' else
             request.ProxyHandler({}) if args.network == 'direct' else
             request.ProxyHandler({'http': args.proxy, 'https': args.proxy}))
    opener = request.build_opener(proxy, HTTPSRedirect())
    tag = 'omfit/tdxy-liu/cgyro-tglf/' + version
    url = 'https://github.com/' + REPOSITORY + '/releases/download/' + parse.quote(tag, safe='/') + '/' + expected
    target = folder / expected
    print('Downloading', expected, flush=True)
    for attempt in range(3):
        try:
            with opener.open(request.Request(url, headers={'User-Agent': 'OMFIT-project-deployer/1'}), timeout=30) as response:
                with target.open('wb') as output:
                    count = 0
                    while True:
                        block = response.read(64 * 1024)
                        if not block:
                            break
                        count += len(block)
                        if count > package['bytes']:
                            raise DeploymentError('Download exceeds the declared package size')
                        output.write(block)
            if target.stat().st_size != package['bytes'] or digest(target) != package['sha256']:
                raise DeploymentError('Incomplete download or SHA-256 mismatch')
            return target
        except (error.URLError, OSError, TimeoutError, IncompleteRead, RemoteDisconnected, DeploymentError) as exc:
            if attempt == 2:
                raise DeploymentError('Package download failed after 3 attempts: ' + str(exc)) from None
            time.sleep(attempt + 1)


@contextmanager
def runtime(template, folder):
    """Load only the three verified, standard-library-only archive engine files."""
    with zipfile.ZipFile(template) as archive:
        infos = archive.infolist()
        if len({info.filename for info in infos}) != len(infos):
            raise DeploymentError('Template contains duplicate ZIP members')
        info = archive.getinfo('manifest.json')
        if info.file_size > 1024 * 1024:
            raise DeploymentError('Template manifest is too large')
        manifest = json.loads(archive.read(info))
        if (manifest.get('format') != 'omfit-template-v1'
                or (manifest.get('author'), manifest.get('id')) != ('tdxy-liu', 'cgyro-tglf')
                or manifest.get('examples') is not False
                or set(manifest.get('roots', [])) != {GROUP, 'OMFITtemplates'}):
            raise DeploymentError('Select the official code-only cgyro-tglf template')
        for module in RUNTIME:
            name = 'OMFITtemplates/LIB/' + module + '.py'
            member = archive.getinfo('payload/' + name)
            entry = manifest.get('files', {}).get(name, {})
            if not 0 < member.file_size < 2 * 1024 * 1024:
                raise DeploymentError('Invalid archive engine file: ' + module)
            content = archive.read(member)
            if (len(content) != entry.get('bytes')
                    or hashlib.sha256(content).hexdigest() != entry.get('sha256')):
                raise DeploymentError('Archive engine checksum mismatch: ' + module)
            ast.parse(content, filename=module + '.py', feature_version=(3, 9))
            (folder / (module + '.py')).write_bytes(content)
    sys.path.insert(0, str(folder))
    try:
        engine = importlib.import_module('OMFITlib_template_service')
        structures = importlib.import_module('OMFITlib_template_archive')
        with engine.Template(template) as checked:
            checked.verify()
        yield engine, structures, manifest
    finally:
        sys.path.remove(str(folder))


def relocate_expression(row, mapping, structures):
    """Rewrite only explicit OMFIT['old_module'] atoms, preserving other text.

    AST positions are UTF-8 byte offsets, so edits also work after Chinese
    comments. Relative root[...] expressions automatically follow their module.
    No expression is evaluated, and literals containing code are not guessed.
    """
    if row.kind != 'OMFITexpression' or not row.fields[2].startswith('_'):
        return row, False
    code = ast.literal_eval(row.fields[2][1:])
    if not isinstance(code, str):
        raise DeploymentError('Invalid serialized OMFIT expression at ' + row.fields[0])
    lines = code.encode('utf-8').splitlines(keepends=True)
    offsets, current = [], 0
    for line in lines:
        offsets.append(current)
        current += len(line)
    changes = []
    for node in ast.walk(ast.parse(code)):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == 'OMFIT' and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str) and node.slice.value in mapping):
            text = 'OMFIT' + ''.join('[' + repr(key) + ']' for key in mapping[node.slice.value])
            changes.append((offsets[node.lineno - 1] + node.col_offset,
                            offsets[node.end_lineno - 1] + node.end_col_offset, text.encode()))
    if not changes:
        return row, False
    content = code.encode('utf-8')
    for start, end, text in sorted(changes, reverse=True):
        content = content[:start] + text + content[end:]
    code = content.decode('utf-8')
    ast.parse(code)
    fields = list(row.fields)
    fields[2] = '_' + repr(code)
    return structures.Row(structures.SEPARATOR.join(fields)), True


def project_adapter(engine, structures, source, template, report):
    """Relocate standard modules in memory; stream original backing files once.

    Reusing the existing merge engine preserves its ownership, collision and
    post-write checks without building a second intermediate copy of the data.
    """
    with structures.Project(source) as current, engine.Template(template) as incoming:
        roots = current.roots
        if GROUP in roots:
            mapping = {}
            report['layout'] = 'grouped'
        else:
            mapping = {name: (GROUP, name) for name in LEGACY if name in roots}
            if not mapping:
                raise DeploymentError('No recognized CGYRO/TGLF modules. Found: ' + ', '.join(roots))
            if any(row.keys == (GROUP,) for row in current.rows):
                raise DeploymentError('CGYRO_TGLF_scan already exists as a non-module node')
            report['layout'] = 'independent'
        report['old_roots'] = roots
        report['module_mapping'] = {name: list(path) for name, path in mapping.items()}
        scaffold = [row.text() for row in incoming.rows if row.keys == (GROUP,)]
    base = structures.Project

    class RelocatedProject(base):
        def __init__(self, filename, payload=False):
            super().__init__(filename, payload)
            if payload or self.path != source or not mapping:
                return
            try:
                rows, rewritten = [], []
                for original in self.rows:
                    fields = list(original.fields)
                    if original.keys[0] in mapping:
                        keys = mapping[original.keys[0]] + original.keys[1:]
                        fields[0] = ''.join('[' + repr(key) + ']' for key in keys)
                    row = structures.Row(structures.SEPARATOR.join(fields))
                    row, changed = relocate_expression(row, mapping, structures)
                    rows.append(row)
                    if changed:
                        rewritten.append(row.fields[0])
                rows += [structures.Row(text) for text in scaffold]
                if len({row.keys for row in rows}) != len(rows):
                    raise DeploymentError('Module relocation produces duplicate tree paths')
                self.rows = rows
                self.modules = {row.keys for row in rows if row.kind == 'OMFITmodule'}
                self.roots = sorted({row.keys[0] for row in rows if len(row.keys) == 1 and row.kind == 'OMFITmodule'})
                report['rewritten_expression_nodes'] = rewritten
            except BaseException:
                self.close()
                raise
    return RelocatedProject


def default_output(source, version):
    stem = source.stem if source is not None else 'CGYRO_TGLF_scan'
    parent = source.parent if source is not None else Path.cwd()
    result = parent / (stem + '-deployed-' + version + '.zip')
    if result.exists() or result.is_symlink() or result.with_suffix('.deploy.json').exists():
        result = parent / (stem + '-deployed-' + version + '-' + uuid.uuid4().hex[:8] + '.zip')
    return result


def check_output(output, source=None):
    if output.suffix.lower() != '.zip' or output == source:
        raise DeploymentError('Output must be a new .zip path')
    report = output.with_suffix('.deploy.json')
    if output.exists() or output.is_symlink() or report.exists() or report.is_symlink():
        raise DeploymentError('Output project or deployment report already exists: ' + str(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', nargs='?', help='Saved old OMFIT project ZIP')
    parser.add_argument('--new', action='store_true', help='Create a fresh code-only project')
    parser.add_argument('--output', type=Path, help='New output ZIP; an existing file is never replaced')
    parser.add_argument('--template', type=Path, help='Local .omfittpl.zip for offline migration')
    parser.add_argument('--dry-run', action='store_true', help='Write a report without creating a project')
    parser.add_argument('--network', choices=('manual', 'system', 'direct'), default='manual')
    parser.add_argument('--proxy', default=DEFAULT_PROXY, help='HTTP(S) proxy used with --network manual')
    args = parser.parse_args()
    if sys.version_info < (3, 9):
        parser.error('Python 3.9 or newer is required; use the Python from your OMFIT environment')
    if bool(args.project) == args.new or (args.new and args.template):
        parser.error('Supply an old project ZIP, or use --new; --template is for migration only')
    source = Path(args.project).expanduser().resolve() if args.project else None
    report = dict(format='omfit-first-deploy-v1', source=str(source) if source else None,
                  created_at=datetime.now(timezone.utc).isoformat(),
                  data_policy='keep', settings_policy='keep', dry_run=args.dry_run)
    try:
        if args.network == 'manual' and parse.urlsplit(args.proxy).scheme not in ('http', 'https'):
            raise DeploymentError('The manual proxy must be an HTTP or HTTPS URL')
        if source is not None and not source.is_file():
            raise DeploymentError('Old project ZIP not found: ' + str(source))
        with tempfile.TemporaryDirectory(prefix='omfit-deploy-') as temporary:
            work = Path(temporary)
            package = args.template.expanduser().resolve() if args.template else download('project' if args.new else 'template', work, args)
            if args.new:
                version = RELEASE['version']
                with zipfile.ZipFile(package) as archive:
                    if archive.namelist()[0] != 'OMFITsave.txt' or archive.testzip() is not None:
                        raise DeploymentError('Invalid code-only project ZIP')
                output = (args.output.expanduser().absolute() if args.output else default_output(None, version))
                check_output(output)
                report.update(dict(layout='new', version=version, output=str(output)))
                if not args.dry_run:
                    output.parent.mkdir(parents=True, exist_ok=True)
                    sibling = output.with_name('.' + output.name + '.' + uuid.uuid4().hex + '.partial')
                    try:
                        with package.open('rb') as src, sibling.open('xb') as dst:
                            shutil.copyfileobj(src, dst)
                        if digest(sibling) != RELEASE['project']['sha256']:
                            raise DeploymentError('Written project checksum mismatch')
                        os.link(sibling, output)
                    finally:
                        if sibling.exists():
                            sibling.unlink()
            else:
                with runtime(package, work) as (engine, structures, metadata):
                    version = metadata['version']
                    output = (args.output.expanduser().absolute() if args.output else default_output(source, version))
                    check_output(output, source)
                    adapted = project_adapter(engine, structures, source, package, report)
                    original = engine.Project
                    try:
                        engine.Project = adapted
                        plan = engine.plan_update(source, package, data_policy='keep', settings_policy='keep')
                        report.update(dict(version=version, output=str(output),
                                           updated_modules=plan['updated_modules'], added_modules=plan['added_modules'],
                                           preserved_files=plan['preserved_files'],
                                           output_bytes_estimate=plan['output_bytes_estimate'],
                                           changes=plan['changes'], tree_changes=plan['tree_changes']))
                        print('Detected layout:', report['layout'], flush=True)
                        for old, new in report['module_mapping'].items():
                            print('  ' + old + ' -> ' + '/'.join(new), flush=True)
                        if not args.dry_run:
                            print('Writing new project; input/results/settings are kept...', flush=True)
                            engine.apply_update(plan, output)
                    finally:
                        engine.Project = original
            report_path = output.with_suffix('.deploy.json')
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open('x', encoding='utf-8') as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
            print('Report:', report_path, flush=True)
            print('PREVIEW_ONLY' if args.dry_run else 'DEPLOYED:', output, flush=True)
            if not args.dry_run:
                print('Open this new ZIP in OMFIT, then CGYRO_TGLF_scan -> GUIS -> main.')
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(1, 'Deployment stopped: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
