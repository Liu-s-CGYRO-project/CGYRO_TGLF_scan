"""Stage template files and patch an existing OMFIT tree without project I/O."""
from builtins import BaseException, Exception, all, any, bool, bytes, dict, float, getattr, hasattr, id, int, isinstance, iter, len, list, object, open, repr, reversed, set, setattr, sorted, str, tuple, type, zip
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
import weakref
import uuid

from OMFITlib_template_archive import CHUNK, CODE_BRANCHES, SETTINGS_BRANCHES, TemplateError, tree_bytes
from OMFITlib_template_service import Template, check_cancel
from OMFITlib_template_migration import (ArchiveIndex, GROUP, LEGACY, Layout,
                                        branch, kind, rebind, relocated_expression, structure)

CODE = CODE_BRANCHES | {'help', 'license', 'README'}
MISSING = object()


def raw(node, key, default=MISSING):
    # Bypass SortedDict's lazy child loading, particularly for result branches.
    return dict.get(node, key, default)


def keys(node):
    return list(dict.keys(node))


def materialize(node, path):
    # Only called for module scaffolding, code and settings, never result trees.
    if isinstance(node, dict) and getattr(node, '__dict__', {}).get('dynaLoad', False):
        try:
            node.keys()
        except Exception as exc:
            raise TemplateError('无法读取更新节点 ' + location(path) + '：' + str(exc)) from exc


def module(node):
    return any(base.__name__ == 'OMFITmodule' for base in type(node).__mro__)


def python_node(node):
    return any(base.__name__.startswith('OMFITpython') for base in type(node).__mro__)


def file_node(node):
    # OMFITgacode, OMFIThelp and other file objects can also inherit dict.
    # They are complete file payloads, not ordinary tree branches to merge.
    return any(base.__name__ == 'OMFITobject' for base in type(node).__mro__)


def location(path):
    return ''.join('[' + repr(key) + ']' for key in path)


def lookup(tree, path):
    for key in path:
        if not isinstance(tree, dict):
            return MISSING
        tree = raw(tree, key)
    return tree


def stamp(value):
    """Detect edits to touched code/settings; never inspect calculation data."""
    if any(base.__name__ == 'OMFITexpression' for base in type(value).__mro__):
        return (id(value), str(value.expression))
    if file_node(value):
        digest = hashlib.sha256()
        with open(value.filename, 'rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        # Read the existing dictionary without invoking its lazy loader. This
        # also protects unsaved edits to an already opened input/help file.
        memory = tuple((key, stamp(raw(value, key))) for key in keys(value)) if isinstance(value, dict) else None
        return (id(value), str(value.filename), digest.hexdigest(), memory)
    if isinstance(value, dict):
        return (id(value), tuple((key, stamp(raw(value, key))) for key in keys(value)))
    if isinstance(value, (list, tuple)):
        return (id(value), tuple(stamp(item) for item in value))
    if python_node(value):
        return (id(value), hashlib.sha256(value.read().encode('utf-8')).hexdigest())
    if hasattr(value, 'expression'):
        return (id(value), str(value.expression))
    if hasattr(value, 'dtype') and hasattr(value, 'tobytes'):
        return (id(value), str(value.dtype), value.shape, hashlib.sha256(value.tobytes()).hexdigest())
    return (id(value),)


def same_content(old, new):
    """Compare owned code/settings without filenames, identities or evaluation."""
    if old is new:
        return True
    if old is MISSING or new is MISSING:
        return False
    if (type(old).__module__, type(old).__name__) != (type(new).__module__, type(new).__name__):
        return False
    if any(base.__name__ == 'OMFITexpression' for base in type(old).__mro__):
        return str(old.expression) == str(new.expression)
    if python_node(old):
        # Compare source bytes without parsing, executing or relying on locale.
        def source(value):
            if file_node(value):
                with open(value.filename, 'rb') as stream:
                    text = stream.read()
            else:
                text = value.read().encode('utf-8')
            return text.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        return source(old) == source(new)
    if file_node(old):
        # Do not force parsing of file-backed inputs. Already loaded dictionaries
        # must also match, otherwise keep the conservative replacement operation.
        if isinstance(old, dict) and (keys(old) != keys(new) or not all(
                same_content(raw(old, key), raw(new, key)) for key in keys(old))):
            return False
        def digest(value):
            result = hashlib.sha256()
            with open(value.filename, 'rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    result.update(block)
            return result.digest()
        return digest(old) == digest(new)
    if isinstance(old, dict):
        return keys(old) == keys(new) and all(same_content(raw(old, key), raw(new, key)) for key in keys(old))
    if isinstance(old, (list, tuple)):
        return len(old) == len(new) and all(same_content(before, after) for before, after in zip(old, new))
    if type(old) in (bool, int, float, str, bytes, type(None)):
        return old == new
    if hasattr(old, 'dtype') and hasattr(old, 'tobytes'):
        return (not getattr(old.dtype, 'hasobject', True) and
                str(old.dtype) == str(new.dtype) and old.shape == new.shape and old.tobytes() == new.tobytes())
    # Unknown wrappers can overload equality or evaluate expressions.
    return False


def payload_size(value):
    if file_node(value) and Path(value.filename).is_file():
        return Path(value.filename).stat().st_size
    if python_node(value):
        return len(value.read().encode('utf-8'))
    return None


def _staging_path(directory, name):
    """Validate extraction using the host's path rules, including empty dirs.

    Archive names preserve literal backslashes on Linux. On Windows those same
    bytes may mean traversal or a drive path, so validation belongs immediately
    before filesystem writes rather than rewriting names in the ZIP parser.
    """
    destination = (directory / name).resolve()
    try:
        destination.relative_to(directory)
    except ValueError:
        raise TemplateError('模板路径超出暂存目录：' + name) from None
    return destination


def _stage_member(source, name, destination, cancel):
    """Verify the adopted payload while copying it once into private staging."""
    digest, size = hashlib.sha256(), 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.z.open(source.files[name]) as reader, destination.open('xb') as writer:
        while True:
            check_cancel(cancel)
            block = reader.read(CHUNK)
            if not block:
                break
            writer.write(block)
            digest.update(block)
            size += len(block)
    spec = source.manifest['files'][name]
    if size != spec['bytes'] or digest.hexdigest() != spec['sha256']:
        raise TemplateError('模板文件大小或 SHA-256 不匹配：' + name)


class Prepared:
    def __init__(self, template_path, data_policy='keep', settings_policy='keep', cancel=None):
        if data_policy not in ('keep', 'examples') or settings_policy not in ('keep', 'template'):
            raise TemplateError('不支持的更新选项')
        self.path = Path(tempfile.mkdtemp(prefix='omfit-live-template-')).resolve()
        self.path.relative_to(Path(tempfile.gettempdir()).resolve())
        self._cleanup = weakref.finalize(self, shutil.rmtree, str(self.path), True)
        self.data_policy, self.settings_policy = data_policy, settings_policy
        try:
            with Template(template_path) as source:
                # Template validates every index entry/path. Keep-mode does not
                # adopt example results, so only the tree and adopted payloads
                # need content verification; unused data is never opened.
                tree_digest = source.digest('OMFITsave.txt', lambda _: check_cancel(cancel))
                if tree_digest != source.manifest['files']['OMFITsave.txt']['sha256']:
                    raise TemplateError('模板文件 SHA-256 不匹配：OMFITsave.txt')
                if data_policy == 'examples' and not source.manifest['examples']:
                    raise TemplateError('此版本没有示例，不能切换到示例结果')
                self.release = dict(source.manifest)
                self.modules = source.modules
                rows = [row for row in source.rows if data_policy == 'examples' or
                        source.category(row) != 'data' or
                        (row.kind == 'OMFITtree' and not row.ref and row.keys[:-1] in source.modules)]
                for name, spec in source.manifest['files'].items():
                    check_cancel(cancel)
                    if name == 'OMFITsave.txt' or (spec['kind'] == 'data' and data_policy == 'keep'):
                        continue
                    destination = _staging_path(self.path, name)
                    _stage_member(source, name, destination, cancel)
                for row in rows:
                    if row.ref and row.ref in source.directories:
                        _staging_path(self.path, row.ref).mkdir(parents=True, exist_ok=True)
                self.entry = self.path / 'OMFITsave.txt'
                self.entry.write_bytes(tree_bytes(rows))
                if source.stamp() != source._stat:
                    raise TemplateError('校验期间模板包已改变，请重新预览')
        except BaseException:
            self._cleanup()
            raise

    def discard(self):
        """Remove unclaimed staging files; never call after session adoption.

        LivePlan/session storage owns successfully delivered instances because
        lazy code nodes may continue reading these files. Only the task queue
        may discard a prepared result which was cancelled before delivery.
        The finalizer remains the fallback and makes this operation idempotent.
        """
        self._cleanup()


class LivePlan:
    def __init__(self, omfit, prepared, factory):
        self.omfit, self.prepared = omfit, prepared
        self.factory = factory
        try:
            self.incoming = factory(str(prepared.entry), quiet=True, developerMode=False)
        except Exception as exc:
            raise TemplateError('无法载入模板树，尚未更新当前工程：' + str(exc)) from exc
        self.operations, self.guards, self.gui_paths = [], [], {}
        self.relocations, self.scaffold = {}, None
        self.bare_output_source = MISSING
        self.archive_index = ArchiveIndex()
        # An independent old module is moved as an object, never deep-copied.
        # The incoming wrapper exists only off-tree until the transaction starts.
        if GROUP in prepared.release['roots'] and raw(omfit, GROUP) is MISSING:
            for name in LEGACY:
                old = raw(omfit, name)
                if old is not MISSING:
                    if not module(old) or not module(lookup(self.incoming, (GROUP, name))):
                        raise TemplateError('旧模块与模板结构不一致：' + name)
                    self.relocations[name] = old
            if ('CGYRO_scan' not in self.relocations and self._supports_archive_index()
                    and (branch(raw(omfit, 'OUTPUTScan')) or kind(raw(omfit, 'OUTPUTScan'), 'OMFITcgyro'))
                    and not module(raw(omfit, 'OUTPUTScan'))):
                self.bare_output_source = raw(omfit, 'OUTPUTScan')
            if self.relocations or self.bare_output_source is not MISSING:
                self.scaffold = raw(self.incoming, GROUP)
                self.scaffold.filename = ''
        elif GROUP in prepared.release['roots']:
            duplicates = [name for name in LEGACY if raw(omfit, name) is not MISSING]
            if duplicates:
                raise TemplateError('总模块与独立旧模块同时存在，不能确定结果归属：' + '、'.join(duplicates)
                                    + '。请保留旧工程，并先明确需要迁入的那套模块。')
        self.added_modules = [name for name in prepared.release['roots'] if raw(omfit, name) is MISSING]
        for name in prepared.release['roots']:
            new, old = raw(self.incoming, name), raw(omfit, name)
            if not module(new) or (old is not MISSING and not module(old)):
                raise TemplateError('模板与当前工程的模块类型不一致：' + name)
            if name == GROUP and self.scaffold is not None:
                for child, previous in self.relocations.items():
                    self._module((GROUP, child), previous, raw(new, child))
            else:
                self._module((name,), old, new)
        if self.prepared.data_policy == 'keep':
            self._archives()
        if self.bare_output_source is not MISSING:
            if self.prepared.data_policy != 'keep':
                raise TemplateError('迁移顶层 OUTPUTScan 需要选择“保留当前案例 / 结果”')
            self._operation(('OUTPUTScan',), self.bare_output_source, MISSING, data=True)
        if self.relocations:
            self._expressions()
        self._check_layouts()
        self.applied = False

    def _before(self, path):
        if len(path) > 1 and path[0] == GROUP and path[1] in self.relocations:
            return path[1:]
        return path

    def _lookup(self, path):
        return lookup(self.omfit, self._before(path))

    def _supports_archive_index(self):
        release = self.prepared.release
        if (GROUP not in release['roots'] or release.get('id', '') != 'cgyro-tglf'
                or release.get('author', '') != 'tdxy-liu'):
            return False
        try:
            version = tuple(int(part) for part in release['version'].split('.'))
        except ValueError:
            return False
        return version >= (1, 22, 20)

    def _archives(self):
        if not self._supports_archive_index():
            return
        for name, method in (('CGYRO_scan', self.archive_index.cgyro), ('TGLF_scan', self.archive_index.tglf)):
            path = (GROUP, name)
            node = self._lookup(path)
            if node is MISSING and name == 'CGYRO_scan' and self.bare_output_source is not MISSING:
                node = {'OUTPUTScan': self.bare_output_source}
            if node is MISSING:
                continue
            sources, issues = len(self.archive_index.sources), len(self.archive_index.issues)
            try:
                replacements = method(node)
            except Exception as exc:
                raise TemplateError('无法安全识别旧扫描归档，当前工程未修改：' + str(exc)) from exc
            for key, value in (replacements or {}).items():
                self._operation(path + (key,), raw(node, key), value, data=True)
            # Current RUN_DB layouts need no archive migration, but a code-only
            # update must also retire pre-deferred browser expression text.
            # Older target releases do not provide this lazy browser contract.
            version = tuple(int(part) for part in self.prepared.release['version'].split('.'))
            if name == 'CGYRO_scan' and replacements is None and version >= (1, 24, 20):
                for relative, old, new in self.archive_index.deferred_browser_links(node):
                    self._operation(path + relative, old, new, data=True)
            for row in self.archive_index.sources[sources:] + self.archive_index.issues[issues:]:
                row['module'] = name
        if (self.relocations or self.bare_output_source is not MISSING or self.archive_index.sources or
                self.archive_index.issues and any(isinstance(op['new'], Layout) for op in self.operations)):
            path = (GROUP, 'MIGRATION_LOG')
            old = self._lookup(path)
            # One persistent report is sufficient to recover every original
            # name; previous reports are kept when another migration is needed.
            records = {} if old is MISSING else {key: value for key, value in dict.items(old)}
            records[uuid.uuid4().hex] = dict(format='omfit-archive-migration-v1',
                created=datetime.now(timezone.utc).isoformat(), release=self.prepared.release['version'],
                module_mapping={name: [GROUP, name] for name in self.relocations},
                standalone_output=self.bare_output_source is not MISSING,
                sources=self.archive_index.sources, unresolved=self.archive_index.issues)
            parent = self.scaffold if self.scaffold is not None else lookup(self.omfit, (GROUP,))
            self.operations.append(dict(path=path, parent=parent, old=raw(parent, 'MIGRATION_LOG'),
                new=Layout(records), stamp=None, data=True, staged=self.scaffold is not None))

    def _expressions(self):
        mapping = {name: (GROUP, name) for name in self.relocations}
        owned = {op['path'] for op in self.operations}
        def visit(node, path):
            if path in owned:
                return
            if any(base.__name__ == 'OMFITexpression' for base in type(node).__mro__):
                new = relocated_expression(node, mapping)
                if new is not node:
                    self._operation(path, node, new)
            elif branch(node) or (path[-1] in SETTINGS_BRANCHES and isinstance(node, dict)):
                materialize(node, path)
                for key in keys(node):
                    if key not in CODE:
                        visit(raw(node, key), path + (key,))
        for name, node in self.relocations.items():
            visit(node, (GROUP, name))
        for name in keys(self.omfit):
            node = raw(self.omfit, name)
            if name not in self.prepared.release['roots'] and name not in self.relocations and module(node):
                visit(node, (name,))
        for op in self.operations:
            if not op['data']:
                op['new'] = relocated_expression(op['new'], mapping)

    def _idle(self):
        # Moving a module while an execution window still holds its old root
        # would make its eventual collector write to the wrong project layout.
        if self.scaffold is None:
            return
        node = self.relocations.get('CGYRO_scan', {})
        manifests = [raw(node, 'RUN_MANIFEST', {})]
        for record in manifests:
            if isinstance(record, dict) and raw(record, 'status', '') in (
                    'prepared', 'submitted', 'submitted_or_finished', 'running', 'loaded', 'cancel_requested'):
                raise TemplateError('旧工程仍有未收集的 CGYRO 运行，请先结束并归档，再迁移模块')

    def _move(self):
        self.omfit[GROUP] = self.scaffold
        for name, node in self.relocations.items():
            del self.omfit[name]
            self.scaffold[name] = node

    def _restore_roots(self):
        for name, node in self.relocations.items():
            self.omfit[name] = node
        if raw(self.omfit, GROUP) is self.scaffold:
            del self.omfit[GROUP]
        if self.bare_output_source is not MISSING and raw(self.omfit, 'OUTPUTScan') is self.bare_output_source:
            self.omfit['OUTPUTScan'] = rebind(self.bare_output_source)

    def _operation(self, path, old, new, data=False):
        parent = self._lookup(path[:-1])
        staged = parent is MISSING and self.scaffold is not None and path[0] == GROUP
        if staged:
            parent = lookup(self.scaffold, path[1:-1])
            if not isinstance(parent, dict):
                raise TemplateError('新模块缺少迁移目标：' + location(path))
            old = raw(parent, path[-1])
        for op in self.operations:
            if op['path'] == path:
                if op['parent'] is not parent or op['old'] is not old:
                    raise TemplateError('更新规划出现重复节点冲突：' + location(path))
                op.update(dict(new=new, data=data, stamp=None if data else stamp(old)))
                return
        try:
            if old is new or (not data and same_content(old, new)):
                return
            fingerprint = None if data else stamp(old)
        except Exception as exc:
            raise TemplateError('无法比较更新节点 ' + location(path) + '：' + str(exc)) from exc
        self.operations.append(dict(path=path, parent=parent, old=old, new=new,
                                    stamp=fingerprint, data=data, staged=staged))

    def _tree(self, path, old, new, keep=False, merge_settings=False):
        if not merge_settings and (file_node(old) or file_node(new)):
            if not keep or old is MISSING:
                self._operation(path, old, new)
            return
        materialize(old, path)
        materialize(new, path)
        if isinstance(old, dict) and isinstance(new, dict):
            self.guards.append((path, old, tuple(keys(old))))
            for key in keys(new):
                value = raw(old, key)
                if keep and value is not MISSING and not (isinstance(value, dict) and isinstance(raw(new, key), dict)):
                    continue
                self._tree(path + (key,), value, raw(new, key), keep)
            if not keep:
                for key in keys(old):
                    if raw(new, key) is MISSING:
                        self._operation(path + (key,), raw(old, key), MISSING)
        elif not keep or old is MISSING:
            self._operation(path, old, new)

    def _settings(self, path, old, new):
        materialize(old, path)
        materialize(new, path)
        if self.prepared.settings_policy != 'keep' or not isinstance(old, dict) or not isinstance(new, dict):
            self._tree(path, old, new, merge_settings=True)
            return
        self.guards.append((path, old, tuple(keys(old))))
        for key in keys(new):
            self._tree(path + (key,), raw(old, key), raw(new, key), key not in ('MODULE', 'DEPENDENCIES'))

    def _guis(self, node, path):
        materialize(node, path)
        if python_node(node):
            self.gui_paths[id(node)] = path
        elif isinstance(node, dict):
            for key in keys(node):
                self._guis(raw(node, key), path + (key,))

    def current_gui_paths(self):
        self.gui_paths = {}
        def visit(node, path):
            if not module(node):
                return
            self._guis(raw(node, 'GUIS'), path + ('GUIS',))
            for key in keys(node):
                child = raw(node, key)
                if module(child):
                    visit(child, path + (key,))
        for name in self.prepared.release['roots']:
            visit(raw(self.omfit, name), (name,))
        if raw(self.omfit, GROUP) is MISSING:
            for name, node in self.relocations.items():
                visit(node, (GROUP, name))
        return self.gui_paths

    def _module(self, path, old, new):
        materialize(old, path)
        materialize(new, path)
        if old is MISSING:
            new.filename = ''
            self._operation(path, old, new, data=True)
            return
        self.guards.append((path, old, tuple(keys(old))))
        self._guis(raw(old, 'GUIS'), path + ('GUIS',))
        for key in list(dict.fromkeys(keys(new) + keys(old))):
            before, after = raw(old, key), raw(new, key)
            child = path + (key,)
            if module(before) or module(after):
                if after is MISSING:
                    if self.prepared.data_policy == 'keep':
                        raise TemplateError('模板删除了子模块，无法自动保留案例：' + location(child))
                    self._operation(child, before, MISSING, data=True)
                elif not module(after) or (before is not MISSING and not module(before)):
                    raise TemplateError('模块与普通节点冲突：' + location(child))
                else:
                    self._module(child, before, after)
            elif key in CODE or python_node(before) or python_node(after):
                if key not in CODE and before is not MISSING and not python_node(before) and python_node(after):
                    raise TemplateError('新代码与当前数据节点冲突：' + location(child))
                self._tree(child, before, after)
            elif key in SETTINGS_BRANCHES:
                if after is not MISSING:
                    self._settings(child, before, after)
            elif self.prepared.data_policy == 'examples':
                self._operation(child, before, after, data=True)
            elif before is MISSING and isinstance(after, dict) and not keys(after):
                self._operation(child, before, after, data=True)

    def report(self):
        scope = {op['path'][0] for op in self.operations}
        if self.scaffold is not None:
            scope.add(GROUP)
        return dict(mode='live', release=self.prepared.release,
                    module_mapping={name: [GROUP, name] for name in self.relocations},
                    standalone_output=self.bare_output_source is not MISSING,
                    archive_sources=list(self.archive_index.sources), archive_issues=list(self.archive_index.issues),
                    data_policy=self.prepared.data_policy, settings_policy=self.prepared.settings_policy,
                    updated_modules=[name for name in self.prepared.release['roots']
                                     if name in scope and name not in self.added_modules],
                    added_modules=[name for name in self.added_modules if name in scope],
                    changes=[dict(path=location(op['path']), bytes=None if op['data'] else
                                  payload_size(op['old'] if op['new'] is MISSING else op['new']),
                        action='add' if op['old'] is MISSING else 'delete' if op['new'] is MISSING else 'replace')
                             for op in self.operations] +
                    [dict(path=location((name,)) + ' → ' + location((GROUP, name)), bytes=None, action='move')
                     for name in self.relocations])

    def _check_layouts(self):
        for op in self.operations:
            if isinstance(op['new'], Layout):
                try:
                    op['new'].check(op['path'])
                except ValueError as exc:
                    raise TemplateError('旧归档键名检查失败，当前工程未修改：' + str(exc)) from exc

    def _check(self, undo=False):
        if self.scaffold is not None:
            expected = self.scaffold if undo else MISSING
            if raw(self.omfit, GROUP) is not expected:
                raise TemplateError('工程根模块已改变，请重新预览')
            for name, node in self.relocations.items():
                if (lookup(self.omfit, (GROUP, name)) if undo else raw(self.omfit, name)) is not node:
                    raise TemplateError('待迁移模块已改变：' + name)
                if undo and raw(self.omfit, name) is not MISSING:
                    raise TemplateError('旧模块位置已被占用，不能撤销：' + name)
            if undo and structure(self.scaffold) != self.scaffold_stamp:
                raise TemplateError('迁移后工程数据或设置已改变，不能撤销；原结果保留在当前工程')
        if not undo:
            self._idle()
            self.archive_index.check()
            self._check_layouts()
        find = lookup if undo else lambda tree, path: self._lookup(path)
        for path, node, old_keys in self.guards:
            if find(self.omfit, path) is not node:
                raise TemplateError('工程结构已改变，请重新预览：' + location(path))
            if not undo and tuple(keys(node)) != old_keys:
                raise TemplateError('预览后节点已改变，请重新预览：' + location(path))
        for op in self.operations:
            expected = op['new'] if undo else op['old']
            parent = op['parent'] if op.get('staged', False) and not undo else find(self.omfit, op['path'][:-1])
            actual = raw(parent, op['path'][-1]) if isinstance(parent, dict) else MISSING
            if parent is not op['parent'] or actual is not expected:
                raise TemplateError('待更新节点已改变，请重新预览：' + location(op['path']))
            if not op['data'] and stamp(expected) != op['stamp']:
                raise TemplateError('代码或设置已修改，不能覆盖：' + location(op['path']))
            if undo and op.get('layout_stamp', None) is not None and structure(expected) != op['layout_stamp']:
                raise TemplateError('迁移后的扫描索引已改变，不能撤销：' + location(op['path']))

    def _put(self, op, value):
        if value is MISSING:
            del op['parent'][op['path'][-1]]
        else:
            if isinstance(value, Layout):
                value = value.build(self.factory)
            elif op['data']:
                value = rebind(value)
            op['parent'][op['path'][-1]] = value

    def apply(self, refresh):
        if self.applied:
            raise TemplateError('此预览已经应用，请重新预览')
        self.rollback_errors = []
        self._check()
        completed = []
        try:
            if self.scaffold is not None:
                self._move()
            for op in self.operations:
                completed.append(op)
                self._put(op, op['new'])
                # Native SortedDict copies expressions when attaching them.
                op['new'] = lookup(self.omfit, op['path'])
            refresh(self, False)
            for op in self.operations:
                op['stamp'] = None if op['data'] else stamp(op['new'])
                if op['data']:
                    op['layout_stamp'] = structure(op['new'])
            if self.scaffold is not None:
                self.scaffold_stamp = structure(self.scaffold)
            self.applied = True
        except BaseException as exc:
            # OMFIT Abort can raise KeyboardInterrupt. Restore every touched
            # node, even if a second interruption/write failure affects one
            # rollback step; preserve the original exception as the cause.
            for op in reversed(completed):
                if op['old'] is MISSING and raw(op['parent'], op['path'][-1]) is MISSING:
                    continue
                self._rollback_step(location(op['path']), self._put, op, op['old'])
            if self.scaffold is not None:
                self._rollback_step('module roots', self._restore_roots)
            self._rollback_step('GUI refresh', refresh, self, True)
            setattr(exc, 'template_rollback_errors', list(self.rollback_errors))
            if not isinstance(exc, Exception):
                raise
            message = ('更新失败，部分回滚步骤失败，请保留当前会话并检查错误：' if self.rollback_errors
                       else '更新失败，已恢复原节点：')
            failure = TemplateError(message + str(exc))
            failure.template_rollback_errors = list(self.rollback_errors)
            raise failure from exc

    def _rollback_step(self, label, callback, *args):
        """Continue recovery after secondary failures without hiding Abort.

        Keep strings rather than exception frames, which could otherwise pin
        large live result trees. Callers retain the original exception object.
        """
        try:
            callback(*args)
        except BaseException as exc:
            self.rollback_errors.append(dict(step=label, error=type(exc).__name__ + ': ' + str(exc)))

    def undo(self, refresh):
        if not self.applied:
            raise TemplateError('没有可撤销的更新')
        self.rollback_errors = []
        self._check(undo=True)
        completed = []
        try:
            for op in reversed(self.operations):
                completed.append(op)
                self._put(op, op['old'])
            if self.scaffold is not None:
                self._restore_roots()
            refresh(self, True)
        except BaseException as exc:
            if self.scaffold is not None and raw(self.omfit, GROUP) is MISSING:
                self._rollback_step('module roots', self._move)
            for op in reversed(completed):
                self._rollback_step(location(op['path']), self._put, op, op['new'])
            self._rollback_step('GUI refresh', refresh, self, False)
            setattr(exc, 'template_rollback_errors', list(self.rollback_errors))
            raise
        self.applied = False
