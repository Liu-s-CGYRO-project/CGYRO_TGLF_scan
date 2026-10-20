"""Create a self-contained CGYRO project copy with one physical result owner.

Only ZIP bytes and literal OMFITsave rows are read. Project code, expressions
and pickle are never executed. Supply the matching code-only release ZIP so
the resulting copy includes readers for the new ordinary-tree references.
"""
import argparse
import ast
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import sys
import zipfile

# This is the installed tool's reviewed, standard-library byte parser. Never
# import helper code, expressions or pickle supplied by the source project.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'))
from OMFITlib_cgyro_checkpoint import select_checkpoint

SEP = ' <-:-:-> '
CHUNK = 4 * 1024 * 1024
REF = '__RESULT_REF__'
STORE = 'RESULT_STORE'


def location(text):
    node, keys = ast.parse('tree' + text, mode='eval').body, []
    while isinstance(node, ast.Subscript):
        keys.insert(0, ast.literal_eval(node.slice))
        node = node.value
    if not isinstance(node, ast.Name) or node.id != 'tree':
        raise ValueError('Invalid saved tree location')
    return tuple(keys)


def entry(keys, kind='OMFITtree', value='', properties='{}'):
    return [''.join('[' + repr(key) + ']' for key in keys), kind, value, properties]


def rows(raw):
    result = OrderedDict()
    for text in raw.decode('utf-8-sig').splitlines():
        if not text.strip():
            continue
        fields = text.split(SEP)
        if len(fields) != 4:
            raise ValueError('Unsupported saved tree row')
        key = location(fields[0])
        if key in result:
            raise ValueError('Duplicate saved tree location')
        result[key] = fields
    return result


def name(path):
    path = path[2:] if path.startswith('./') else path
    parts = path.rstrip('/').split('/')
    if not path or path.startswith('/') or any(part in ('', '.', '..') or '\\' in part for part in parts):
        raise ValueError('Unsafe ZIP member: ' + path)
    return '/'.join(parts)


def content_key(files):
    raw = json.dumps(sorted(files), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def metadata_bytes(mapping):
    children = {}
    for key in mapping:
        # Settings/Namelist files materialize intermediate dictionaries. Native
        # saves list overrides below them without separate parent rows. Walk
        # those virtual parents, but never emit trees that replace the files.
        for length in range(1, len(key) + 1):
            prefix = key[:length]
            siblings = children.setdefault(prefix[:-1], OrderedDict())
            siblings.setdefault(prefix, None)
    output = []

    def visit(parent):
        for key in children.get(parent, []):
            if key in mapping:
                output.append(SEP.join(mapping[key]))
            visit(key)

    visit(())
    if len(output) != len(mapping):
        raise ValueError('Saved tree has missing parents')
    return ('\n'.join(output) + '\n').encode('utf-8')


def compact(source, output, code_project, report_path):
    source, output, code_project = (Path(path).resolve() for path in (source, output, code_project))
    if output == source or output.exists():
        raise ValueError('Choose a new output filename; the original is never overwritten')
    partial = output.with_name(output.name + '.partial')
    if partial.exists():
        raise ValueError('An unfinished output already exists: ' + str(partial))
    original_stat = source.stat()
    module = ('CGYRO_TGLF_scan', 'CGYRO_scan')
    module_path = '/'.join(module)
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(code_project) as code:
        released = rows(code.read('OMFITsave.txt'))
        for library in ('OMFITlib_cgyro_checkpoint', 'OMFITlib_cgyro_storage'):
            path = 'CGYRO_TGLF_scan/LIB/' + library + '.py'
            if (('CGYRO_TGLF_scan', 'LIB', library) not in released
                    or code.read(path) != (Path(__file__).resolve().parents[1] / path).read_bytes()):
                raise ValueError('Supply the matching reviewed code release: ' + library)
        if code.testzip() is not None:
            raise ValueError('Code release CRC mismatch')
        infos = {name(info.filename): info for info in archive.infolist() if not info.is_dir()}
        if len(infos) != len([info for info in archive.infolist() if not info.is_dir()]):
            raise ValueError('Duplicate ZIP member names')
        if infos['OMFITsave.txt'].file_size > 32 * 1024 * 1024:
            raise ValueError('Project metadata exceeds 32 MiB')
        tree = rows(archive.read(infos['OMFITsave.txt']))
        if module not in tree or tree[module][1] != 'OMFITmodule':
            raise ValueError('Expected the unified CGYRO_TGLF_scan/CGYRO_scan project')
        if module + (STORE,) in tree:
            raise ValueError('Project already has indexed storage; use its in-app optimization action')
        owners = OrderedDict()
        for key, fields in tree.items():
            if key[:2] == module and fields[1] == 'OMFITcgyro':
                if not fields[2].startswith('./'):
                    raise ValueError('External CGYRO directory: ' + fields[0])
                directory = name(fields[2][2:])
                owners.setdefault(directory, dict(keys=[], fields=fields, files=[]))['keys'].append(key)
        if not owners:
            raise ValueError('No native CGYRO result directories found')
        owner_files = {}
        for path, info in infos.items():
            parent = path.rpartition('/')[0]
            while parent:
                if parent in owners:
                    relative = path[len(parent) + 1:]
                    owner_files[path] = parent
                    owners[parent]['files'].append((relative, info))
                    break
                parent = parent.rpartition('/')[0]
        groups = OrderedDict()
        checked = 0
        last = 0
        for directory, owner in owners.items():
            members = dict(owner['files'])
            for relative, info in owner['files']:
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Linked result member: ' + info.filename)
            omitted, checkpoint = select_checkpoint({key: info.file_size for key, info in owner['files']},
                lambda key: archive.open(members[key]))
            owner['checkpoint'] = checkpoint
            owner['omitted'] = [(key, members[key].file_size) for key in sorted(omitted)]
            owner['files'] = [(key, info) for key, info in owner['files'] if key not in omitted]
            files = []
            for relative, info in sorted(owner['files'], key=lambda item: item[0]):
                digest = hashlib.sha256()
                with archive.open(info) as handle:
                    for chunk in iter(lambda: handle.read(CHUNK), b''):
                        digest.update(chunk)
                        checked += len(chunk)
                files.append((relative, info.file_size, digest.hexdigest()))
            hashes = {row[0]: row[2] for row in files}
            for key, result in checkpoint['candidates'].items():
                if key in hashes and result.get('sha256', hashes[key]) != hashes[key]:
                    raise ValueError('Checkpoint changed while reading: ' + directory)
            if not files:
                raise ValueError('Empty CGYRO result directory: ' + directory)
            identity = content_key(files)
            owner['identity'], owner['inventory'] = identity, files
            if identity in groups and groups[identity]['fields'][3] != owner['fields'][3]:
                raise ValueError('Identical files have differing native reader properties')
            groups.setdefault(identity, owner)
            if checked - last >= 2_000_000_000:
                print(json.dumps(dict(phase='hash', bytes_checked=checked, unique_results=len(groups))), flush=True)
                last = checked
        # Every result directory remains native OMFITcgyro, but has one owner.
        tree[module + (STORE,)] = entry(module + (STORE,))
        tree[module + ('RESULT_STORAGE',)] = entry(module + ('RESULT_STORAGE',))
        tree[module + ('RESULT_STORAGE', 'version')] = entry(module + ('RESULT_STORAGE', 'version'), 'int', '_2')
        tree[module + ('RESULT_STORAGE', 'checkpoint_policy')] = entry(module + ('RESULT_STORAGE', 'checkpoint_policy'), 'int', '_1')
        tree[module + ('RESULT_STORAGE', 'bytes')] = entry(module + ('RESULT_STORAGE', 'bytes'))
        tree[module + ('RESULT_STORAGE', 'checkpoints')] = entry(module + ('RESULT_STORAGE', 'checkpoints'))
        for owner in owners.values():
            for key in owner['keys']:
                if any(other[:len(key)] == key and len(other) > len(key) for other in tree):
                    raise ValueError('Result has saved child metadata; review before migration')
                tree[key] = entry(key)
                tree[key + (REF,)] = entry(key + (REF,), 'str', '_' + repr(owner['identity']))
        for identity, owner in groups.items():
            prefix = module_path + '/' + STORE + '/' + identity + '/result'
            owner['target'] = prefix
            tree[module + (STORE, identity)] = entry(module + (STORE, identity), 'OMFITcgyro', './' + prefix, owner['fields'][3])
            size = sum(row[1] for row in owner['inventory'])
            key = module + ('RESULT_STORAGE', 'bytes', identity)
            tree[key] = entry(key, 'int', '_' + str(size))
            key = module + ('RESULT_STORAGE', 'checkpoints', identity)
            tree[key] = entry(key, 'str', '_' + repr(json.dumps(owner['checkpoint'], sort_keys=True)))
        # Install published code only. Existing inputs, settings, results,
        # custom code nodes and pickle blobs are preserved as data, never run.
        code_payloads = {}
        for key, fields in released.items():
            is_code = fields[1] in ('OMFITpythonTask', 'OMFITpythonPlot', 'OMFITpythonGUI')
            is_doc = fields[1] == 'OMFITascii' and 'DOCS' in key
            if not (is_code or is_doc) or not fields[2].startswith('./'):
                continue
            for length in range(1, len(key)):
                parent = key[:length]
                if parent not in tree:
                    if parent not in released or released[parent][1] != 'OMFITtree':
                        break
                    tree[parent] = released[parent]
            else:
                tree[key] = fields
                code_payloads[name(fields[2][2:])] = code.read(name(fields[2][2:]))
        metadata = metadata_bytes(tree)
        for key, fields in rows(metadata).items():
            if key[:2] == module and key[-1] == REF:
                identity = ast.literal_eval(fields[2][1:])
                if tree.get(module + (STORE, identity), ['', ''])[1] != 'OMFITcgyro':
                    raise ValueError('Unresolved output result reference')
        expected = {}
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(partial, 'x', compression=zipfile.ZIP_STORED, allowZip64=True) as target:
            # Native OMFIT infers the project root from the first ZIP member.
            target.writestr('OMFITsave.txt', metadata)
            expected['OMFITsave.txt'] = hashlib.sha256(metadata).hexdigest()

            def emit(path, handle, size):
                digest = hashlib.sha256()
                with target.open(path, 'w', force_zip64=size >= 2**31) as destination:
                    for chunk in iter(lambda: handle.read(CHUNK), b''):
                        digest.update(chunk)
                        destination.write(chunk)
                expected[path] = digest.hexdigest()

            for path, info in infos.items():
                if path in owner_files or path == 'OMFITsave.txt' or path in code_payloads:
                    continue
                with archive.open(info) as handle:
                    emit(path, handle, info.file_size)
            for index, (identity, owner) in enumerate(groups.items(), 1):
                hashes = {row[0]: row[2] for row in owner['inventory']}
                for relative, info in owner['files']:
                    path = owner['target'] + '/' + relative
                    with archive.open(info) as handle:
                        emit(path, handle, info.file_size)
                    if expected[path] != hashes[relative]:
                        raise ValueError('Source payload changed while writing: ' + path)
                if index % 80 == 0:
                    print(json.dumps(dict(phase='write', results_written=index, total=len(groups))), flush=True)
            for path, data in code_payloads.items():
                target.writestr(path, data)
                expected[path] = hashlib.sha256(data).hexdigest()
        with zipfile.ZipFile(partial) as target:
            if target.namelist()[0] != 'OMFITsave.txt':
                raise ValueError('Native OMFIT project entry must be the first member')
            if set(target.namelist()) != set(expected):
                raise ValueError('Output member list differs')
            checked = 0
            for info in target.infolist():
                digest = hashlib.sha256()
                with target.open(info) as handle:
                    for chunk in iter(lambda: handle.read(CHUNK), b''):
                        digest.update(chunk)
                        checked += len(chunk)
                if digest.hexdigest() != expected[info.filename]:
                    raise ValueError('Output payload checksum differs: ' + info.filename)
            if target.read('OMFITsave.txt') != metadata:
                raise ValueError('Output tree metadata differs')
        if (source.stat().st_size, source.stat().st_mtime_ns) != (original_stat.st_size, original_stat.st_mtime_ns):
            raise ValueError('Original archive changed during compaction')
        partial.rename(output)
        report = dict(source=str(source), output=str(output), original_bytes=original_stat.st_size,
                      output_bytes=output.stat().st_size, result_instances=sum(len(owner['keys']) for owner in owners.values()),
                      unique_result_directories=len(groups), physical_result_bytes=sum(sum(row[1] for row in owner['inventory']) for owner in groups.values()),
                      copied_payload_sha256_verified=True, crc_verified=True,
                      checkpoint_policy='validated_single_checkpoint',
                      selected_current=sum(owner['checkpoint']['selected'] == 'bin.cgyro.restart' for owner in groups.values()),
                      selected_backup=sum(owner['checkpoint']['selected'] == 'bin.cgyro.restart.old' for owner in groups.values()),
                      checkpoint_warnings=sum(bool(owner['checkpoint'].get('warning', '')) for owner in groups.values()),
                      omitted_checkpoint_instances=sum(len(owner['omitted']) for owner in owners.values()),
                      original_omitted_checkpoint_bytes=sum(size for owner in owners.values() for _, size in owner['omitted']),
                      original_modified=False, project_code_executed=False, gui_run=False)
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--output', required=True)
    parser.add_argument('--code-project', required=True)
    parser.add_argument('--report', required=True)
    options = parser.parse_args()
    compact(options.source, options.output, options.code_project, options.report)
