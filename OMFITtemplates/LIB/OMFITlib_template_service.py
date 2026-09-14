"""Immutable template releases and reviewed, non-destructive project updates."""
from builtins import all, any, bool, bytes, dict, float, int, len, list, max, min, open, range, set, sorted, str, sum, tuple, type, zip
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import uuid
import zipfile

from OMFITlib_template_archive import (
    CHUNK, CODE_BRANCHES, MAX_METADATA, Project, TemplateError, contains_path,
    human_size, json_bytes, merge_defaults, parse_json, safe_name, tree_bytes,
)

FORMAT = 'omfit-template-v1'
EXTENSION = '.omfittpl.zip'


class Cancelled(TemplateError):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled('操作已取消，原工程和已发布版本未修改。')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def slug(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', value):
        raise TemplateError(label + '需使用 1–64 位英文字母、数字、点、下划线或短横线')
    if '__' in value:
        raise TemplateError(label + '不能包含连续下划线（用于分隔作者、模板与版本）')
    safe_name(value)
    return value


def release_name(metadata):
    return '__'.join(slug(metadata[k], k) for k in ('author', 'id', 'version')) + EXTENSION


@contextmanager
def new_file(destination):
    """Commit a completed sibling file without replacing an existing file."""
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise TemplateError('目标已存在，请使用新的文件名或版本号：' + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.' + destination.name + '.' + uuid.uuid4().hex + '.partial')
    try:
        yield temporary
        # Atomic, no-replace publication on Linux, including shared filesystems
        # that support hard links. Never fall back to a clobbering rename.
        os.link(temporary, destination)
        temporary.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()


def _copy_member(source, name, output, dest_name, expected=None, cancel=None, progress=None):
    check_cancel(cancel)
    info = source.files[name]
    target = zipfile.ZipInfo(dest_name, date_time=info.date_time)
    target.compress_type = info.compress_type
    target.external_attr = info.external_attr
    target.internal_attr = info.internal_attr
    target.create_system = info.create_system
    target.comment = info.comment
    digest = hashlib.sha256()
    with source.z.open(info) as reader, output.open(target, 'w', force_zip64=True) as writer:
        while True:
            check_cancel(cancel)
            block = reader.read(CHUNK)
            if not block:
                break
            writer.write(block)
            digest.update(block)
            if progress:
                progress(len(block))
    if expected and digest.hexdigest() != expected:
        raise TemplateError('文件校验失败：' + name)
    return digest.hexdigest()


def inspect_project(filename, roots=None):
    with Project(filename) as project:
        roots = roots or project.roots
        owned = project.ownership(roots)
        counts, sizes = {}, {}
        for filename, category in owned.items():
            counts[category] = counts.get(category, 0) + 1
            sizes[category] = sizes.get(category, 0) + project.files[filename].file_size
        return {'roots': roots, 'available_roots': project.roots, 'files': counts, 'bytes': sizes,
                'code_branches': sorted(CODE_BRANCHES), 'stamp': project.stamp()}


def publish(source_path, library, metadata, roots, include_examples=False, progress=None, cancel=None):
    if not isinstance(roots, (list, tuple)) or not all(isinstance(root, str) for root in roots):
        raise TemplateError('模块范围需要是模块名称列表')
    roots = sorted(set(roots))
    metadata = {k: str(metadata.get(k, '')).strip() for k in ('id', 'name', 'author', 'version', 'description')}
    filename = release_name(metadata)
    if not metadata['name'] or len(metadata['name']) > 200 or len(metadata['description']) > 20000:
        raise TemplateError('请填写模板名称（最长 200 字），说明最长 20000 字')
    destination = Path(library).expanduser().resolve() / filename
    with Project(source_path) as source:
        owned = source.ownership(roots)
        selected = {n: category for n, category in owned.items() if include_examples or category != 'data'}
        rows = []
        for row in source.rows:
            if not source.selected(row, roots):
                continue
            category = source.category(row)
            # Preserve empty top-level data containers, never their cases/results.
            shell = (row.kind == 'OMFITtree' and not row.ref and row.keys[:-1] in source.modules)
            if include_examples or category != 'data' or shell:
                rows.append(row)
        payload_tree = tree_bytes(rows)
        manifest = dict(metadata, format=FORMAT, created=now(), roots=list(roots),
                        examples=bool(include_examples), code_branches=sorted(CODE_BRANCHES),
                        files={}, source_name=source.path.name)
        total = sum(source.files[n].file_size for n in selected)
        done = 0

        def advance(amount):
            nonlocal done
            done += amount
            if progress:
                progress('正在发布模板', done, total)

        with new_file(destination) as temporary:
            with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as output:
                for name, category in sorted(selected.items()):
                    digest = _copy_member(source, name, output, 'payload/' + name,
                                          cancel=cancel, progress=advance)
                    manifest['files'][name] = {'sha256': digest, 'bytes': source.files[name].file_size, 'kind': category}
                output.writestr('payload/OMFITsave.txt', payload_tree)
                manifest['files']['OMFITsave.txt'] = {'sha256': hashlib.sha256(payload_tree).hexdigest(),
                                                     'bytes': len(payload_tree), 'kind': 'tree'}
                _empty_directories(output, rows, selected, 'payload/')
                output.writestr('manifest.json', json_bytes(manifest))
            check_cancel(cancel)
            if source.stamp() != source._stat:
                raise TemplateError('发布期间源工程发生变化，请重新发布')
            with Template(temporary) as template:
                template.verify(cancel=cancel)
    return str(destination)


class Template(Project):
    def __init__(self, path):
        super().__init__(path, payload=True)
        try:
            info = self.z.getinfo('manifest.json')
            if info.file_size > MAX_METADATA:
                raise TemplateError('模板清单过大')
            self.manifest = parse_json(self.z.read(info))
            manifest = self.manifest
            if not isinstance(manifest, dict) or manifest.get('format') != FORMAT:
                raise TemplateError('不支持的模板格式')
            release_name(manifest)
            if type(manifest.get('examples')) is not bool or not isinstance(manifest.get('files'), dict):
                raise TemplateError('模板清单字段无效')
            if not manifest.get('roots') or manifest['roots'] != self.roots:
                raise TemplateError('模板模块范围与树结构不一致')
            if any(row.keys[0] not in self.roots for row in self.rows):
                raise TemplateError('模板含范围外的树节点')
            if manifest.get('code_branches') != sorted(CODE_BRANCHES):
                raise TemplateError('模板代码范围与当前格式不兼容')
            if set(manifest['files']) != set(self.files):
                raise TemplateError('模板载荷与清单文件列表不一致')
            # No unlisted files, except empty directory entries.
            if any(not i.is_dir() and i.filename != 'manifest.json' and not i.filename.startswith('payload/')
                   for i in self.z.infolist()):
                raise TemplateError('模板含清单外文件')
            owned = self.ownership(self.roots)
            for name, spec in manifest['files'].items():
                safe_name(name)
                if (not isinstance(spec, dict) or type(spec.get('bytes')) is not int or
                    spec['bytes'] != self.files[name].file_size or
                    not re.fullmatch('[0-9a-f]{64}', str(spec.get('sha256', ''))) or
                    spec.get('kind') != ('tree' if name == 'OMFITsave.txt' else owned.get(name))):
                    raise TemplateError('模板文件描述不一致：' + name)
                if not manifest['examples'] and spec['kind'] == 'data':
                    raise TemplateError('无示例模板不能包含结果文件：' + name)
            if not manifest['examples']:
                for row in self.rows:
                    if self.category(row) == 'data' and not (
                            row.kind == 'OMFITtree' and not row.ref and row.keys[:-1] in self.modules):
                        raise TemplateError('无示例模板不能包含案例节点：' + row.fields[0])
        except Exception:
            self.close()
            raise

    def verify(self, cancel=None, progress=None):
        for name, spec in self.manifest['files'].items():
            check_cancel(cancel)
            def advance(amount):
                check_cancel(cancel)
                if progress:
                    progress(amount)
            if self.digest(name, advance) != spec['sha256']:
                raise TemplateError('模板文件 SHA-256 不匹配：' + name)


def _empty_directories(output, rows, filenames, prefix=''):
    names = set(filenames)
    directories = set()
    for row in rows:
        if row.ref and row.ref not in names and not any(n.startswith(row.ref + '/') for n in names):
            directories.add(row.ref)
    for directory in sorted(directories):
        output.writestr(prefix + directory + '/', b'')


def list_library(library):
    releases, errors = [], []
    directory = Path(library).expanduser()
    if not directory.exists():
        return releases, errors
    if not directory.is_dir():
        raise TemplateError('模板库路径需要是目录')
    for path in sorted(directory.rglob('*' + EXTENSION)):
        try:
            with Template(path) as template:
                releases.append(dict(template.manifest, path=str(path.resolve()), archive_bytes=path.stat().st_size))
        except (TemplateError, OSError, KeyError, zipfile.BadZipFile) as exc:
            errors.append(path.name + ': ' + str(exc))
    releases.sort(key=lambda m: (m.get('created', ''), m['version']), reverse=True)
    return releases, errors


def transfer(source, destination, cancel=None, progress=None):
    """Import/export/push/pull all use the same verified immutable package."""
    with Template(source) as template:
        template.verify(cancel=cancel)
        destination = Path(destination).expanduser().resolve()
        if template.path == destination:
            raise TemplateError('源模板与目标路径相同')
        size = template.path.stat().st_size
        done = 0
        with new_file(destination) as temporary:
            with open(template.path, 'rb') as reader, open(temporary, 'xb') as writer:
                while True:
                    check_cancel(cancel)
                    block = reader.read(CHUNK)
                    if not block:
                        break
                    writer.write(block)
                    done += len(block)
                    if progress:
                        progress('正在传输模板', done, size)
            with Template(temporary) as check:
                check.verify(cancel=cancel)
    return str(destination)


def _settings(current, template, roots, keep):
    """Merge JSON and its separately serialized expression rows as one unit."""
    current_nodes = {r.keys: r for r in current.rows if current.selected(r, roots) and current.category(r) == 'settings'}
    incoming = [r for r in template.rows if template.category(r) == 'settings']
    bases = [r for r in incoming if r.ref]
    output_rows, content = [], {}
    for base in bases:
        defaults = parse_json(template.read(base.ref))
        if not isinstance(defaults, dict):
            raise TemplateError('设置文件需要是 JSON 对象：' + base.ref)
        old = current_nodes.get(base.keys)
        existing = parse_json(current.read(old.ref)) if old and old.ref else {}
        if not isinstance(existing, dict):
            raise TemplateError('当前设置文件需要是 JSON 对象')
        merged = merge_defaults(defaults, existing) if keep else defaults
        if keep:
            for key in ('MODULE', 'DEPENDENCIES'):
                if key in defaults:
                    merged[key] = defaults[key]
        if old and old.ref and merged == existing:
            content[base.ref] = current.read(old.ref)
        elif merged == defaults:
            content[base.ref] = template.read(base.ref)
        else:
            content[base.ref] = json_bytes(merged)
        output_rows.append(base)
        new_children = {r.keys: r for r in incoming if r.keys[:len(base.keys)] == base.keys and r.keys != base.keys}
        old_children = {k: r for k, r in current_nodes.items() if k[:len(base.keys)] == base.keys and k != base.keys}
        for keys in dict.fromkeys(list(new_children) + list(old_children)):
            relative = keys[len(base.keys):]
            retain = keep and relative[0] not in ('MODULE', 'DEPENDENCIES') and contains_path(existing, relative)
            chosen = old_children.get(keys) if retain else new_children.get(keys)
            if chosen:
                if chosen.ref:
                    raise TemplateError('设置子节点含嵌套文件，需先转换为标准 OMFITsettings：' + chosen.fields[0])
                output_rows.append(chosen)
    if any(r.ref is None and not any(r.keys[:len(b.keys)] == b.keys for b in bases) for r in incoming):
        raise TemplateError('设置树缺少 JSON 根文件')
    return output_rows, content


def _build(current, template, data_policy, settings_policy):
    if data_policy not in ('keep', 'examples') or settings_policy not in ('keep', 'template'):
        raise TemplateError('无效的案例／设置策略')
    if data_policy == 'examples' and not template.manifest['examples']:
        raise TemplateError('此版本没有示例，不能切换到示例结果')
    roots = template.roots
    existing_roots = [name for name in roots if name in current.roots]
    added_roots = set(roots) - set(existing_roots)
    conflicts = sorted({row.keys[0] for row in current.rows if row.keys[0] in added_roots})
    if conflicts:
        raise TemplateError('无法新增模块：当前工程已有同名的非模块节点：' + ', '.join(conflicts))
    # Only existing modules own current files. Newly added modules must still
    # pass the retained-file and tree collision checks below.
    current_owned = current.ownership(existing_roots) if existing_roots else {}
    template_owned = template.ownership(roots)
    if data_policy == 'keep':
        removed_modules = {m for m in current.modules if m[0] in roots} - template.modules
        if removed_modules:
            raise TemplateError('模板删除了子模块，无法自动保留其案例；请先在 OMFIT 整理模块结构')
    settings_rows, generated = _settings(current, template, roots, settings_policy == 'keep')
    rows = [r for r in current.rows if r.keys[0] not in roots]
    rows += [r for r in template.rows if template.category(r) in ('structure', 'code')]
    rows += settings_rows
    if data_policy == 'keep':
        rows += [r for r in current.rows if r.keys[0] in roots and current.category(r) == 'data']
        present = {r.keys for r in rows}
        rows += [r for r in template.rows if template.category(r) == 'data' and r.keys not in present and
                 r.kind == 'OMFITtree' and not r.ref and r.keys[:-1] in template.modules]
    else:
        rows += [r for r in template.rows if template.category(r) == 'data']
    if len({r.keys for r in rows}) != len(rows):
        raise TemplateError('模板代码与当前数据树节点冲突，请重新划定模板模块')
    kept = {name for name in current.files if name != 'OMFITsave.txt' and
            (name not in current_owned or (data_policy == 'keep' and current_owned[name] == 'data'))}
    incoming = {name for name, kind in template_owned.items() if kind != 'settings' and
                (kind != 'data' or data_policy == 'examples')}
    collisions = kept & (incoming | set(generated))
    if collisions:
        raise TemplateError('模板将覆盖保留数据，已阻止：' + ', '.join(sorted(collisions)[:5]))
    unchanged_tree = {r.keys: r.text() for r in rows} == {r.keys: r.text() for r in current.rows}
    generated['OMFITsave.txt'] = current.read('OMFITsave.txt') if unchanged_tree else tree_bytes(rows)
    names = kept | incoming | set(generated)
    for name in names:
        parts = name.split('/')
        if any('/'.join(parts[:i]) in names for i in range(1, len(parts))):
            raise TemplateError('合并后文件与目录重名：' + name)
    # Reject omitted backing files, except genuine empty directory references.
    valid_empty = current.directories | template.directories
    for row in rows:
        if row.ref and row.ref not in names and not any(n.startswith(row.ref + '/') for n in names) and row.ref not in valid_empty:
            raise TemplateError('合并后树引用缺失：' + row.ref)
    return rows, kept, incoming, generated


def plan_update(current_path, template_path, data_policy='keep', settings_policy='keep', cancel=None, progress=None):
    with Project(current_path) as current, Template(template_path) as template:
        if progress:
            progress('正在校验模板并比较文件', 0, 0)
        template.verify(cancel=cancel)
        rows, kept, incoming, generated = _build(current, template, data_policy, settings_policy)
        final_names = kept | incoming | set(generated)
        changes = []
        for name in sorted((set(current.files) - kept) | incoming | set(generated)):
            check_cancel(cancel)
            old = current.files.get(name)
            if name not in final_names:
                changes.append({'action': 'delete', 'path': name, 'bytes': old.file_size})
                continue
            if name in generated:
                digest, size = hashlib.sha256(generated[name]).hexdigest(), len(generated[name])
            else:
                entry = template.manifest['files'][name]
                digest, size = entry['sha256'], entry['bytes']
            if old and current.digest(name, lambda amount: check_cancel(cancel)) == digest:
                continue
            changes.append({'action': 'replace' if old else 'add', 'path': name, 'bytes': size})
        old_rows = {r.keys: r.text() for r in current.rows}
        new_rows = {r.keys: r.text() for r in rows}
        tree_changes = [{'action': 'delete' if keys not in new_rows else 'add' if keys not in old_rows else 'replace',
                         'path': ''.join('[' + repr(k) + ']' for k in keys)}
                        for keys in dict.fromkeys(list(old_rows) + list(new_rows)) if old_rows.get(keys) != new_rows.get(keys)]
        return {'current': str(current.path), 'template': str(template.path),
                'current_stamp': current.stamp(), 'template_stamp': template.stamp(),
                'data_policy': data_policy, 'settings_policy': settings_policy,
                'release': {k: template.manifest[k] for k in ('id', 'name', 'author', 'version', 'roots', 'examples')},
                'updated_modules': sorted(set(template.roots) & set(current.roots)),
                'added_modules': sorted(set(template.roots) - set(current.roots)),
                'changes': changes, 'tree_changes': tree_changes, 'preserved_files': len(kept),
                'output_bytes_estimate': sum(current.files[n].file_size for n in kept) +
                    sum(template.files[n].file_size for n in incoming) + sum(len(v) for v in generated.values()),
                'reviewed_at': now()}


def apply_update(plan, output_path, progress=None, cancel=None):
    output_path = Path(output_path).expanduser().resolve()
    if output_path in (Path(plan['current']), Path(plan['template'])):
        raise TemplateError('输出必须是一个新的工程 ZIP')
    if output_path.suffix.lower() != '.zip':
        raise TemplateError('输出工程请使用 .zip 扩展名')
    with Project(plan['current']) as current, Template(plan['template']) as template:
        if current.stamp() != plan['current_stamp'] or template.stamp() != plan['template_stamp']:
            raise TemplateError('预览后源文件发生变化，请重新预览')
        rows, kept, incoming, generated = _build(current, template, plan['data_policy'], plan['settings_policy'])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Use uncompressed volume as the conservative streaming-space requirement.
        if shutil.disk_usage(output_path.parent).free < plan['output_bytes_estimate'] + 64 * 1024 * 1024:
            raise TemplateError('输出磁盘空间不足，预计需要 ' + human_size(plan['output_bytes_estimate']))
        done, total = 0, plan['output_bytes_estimate']

        def advance(amount):
            nonlocal done
            done += amount
            if progress:
                progress('正在生成工程；原工程保留', done, total)

        with new_file(output_path) as temporary:
            with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as output:
                output.comment = current.z.comment
                for name in sorted(kept):
                    _copy_member(current, name, output, name, cancel=cancel, progress=advance)
                for name in sorted(incoming):
                    _copy_member(template, name, output, name,
                                 expected=template.manifest['files'][name]['sha256'], cancel=cancel, progress=advance)
                for name, content in generated.items():
                    check_cancel(cancel)
                    output.writestr(name, content)
                    advance(len(content))
                _empty_directories(output, rows, kept | incoming | set(generated))
                # A receipt does not execute or enter the OMFIT tree.
                receipt_name = 'template-manager-history/' + uuid.uuid4().hex + '.json'
                output.writestr(receipt_name, json_bytes(dict(plan, completed_at=now(), output=str(output_path))))
            check_cancel(cancel)
            if current.stamp() != plan['current_stamp'] or template.stamp() != plan['template_stamp']:
                raise TemplateError('写入期间源文件发生变化，请重新预览')
            with Project(temporary) as result:
                for name in kept:
                    if (result.files[name].file_size, result.files[name].CRC) != (current.files[name].file_size, current.files[name].CRC):
                        raise TemplateError('结果保留校验失败：' + name)
                for name, content in generated.items():
                    if result.digest(name) != hashlib.sha256(content).hexdigest():
                        raise TemplateError('生成文件校验失败：' + name)
                for name in incoming:
                    if (result.files[name].file_size, result.files[name].CRC) != (template.files[name].file_size, template.files[name].CRC):
                        raise TemplateError('模板载荷校验失败：' + name)
    return str(output_path)


def read_history(project_path):
    with Project(project_path) as project:
        return [parse_json(project.read(n)) for n in sorted(project.files)
                if n.startswith('template-manager-history/') and n.endswith('.json')]
