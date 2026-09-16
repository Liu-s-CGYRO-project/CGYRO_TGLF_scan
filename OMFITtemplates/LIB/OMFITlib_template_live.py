"""Stage template files and patch an existing OMFIT tree without project I/O."""
from builtins import all, any, bytes, dict, getattr, hasattr, id, isinstance, iter, len, list, object, open, repr, reversed, set, sorted, str, tuple, type
import hashlib
from pathlib import Path
import shutil
import tempfile
import weakref

from OMFITlib_template_archive import CODE_BRANCHES, SETTINGS_BRANCHES, TemplateError, tree_bytes
from OMFITlib_template_service import Template, check_cancel

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
                source.verify(cancel=cancel)
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
                    destination = (self.path / name).resolve()
                    destination.relative_to(self.path)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with source.z.open(source.files[name]) as reader, destination.open('xb') as writer:
                        shutil.copyfileobj(reader, writer)
                for row in rows:
                    if row.ref and row.ref in source.directories:
                        (self.path / row.ref).mkdir(parents=True, exist_ok=True)
                self.entry = self.path / 'OMFITsave.txt'
                self.entry.write_bytes(tree_bytes(rows))
                if source.stamp() != source._stat:
                    raise TemplateError('校验期间模板包已改变，请重新预览')
        except Exception:
            self._cleanup()
            raise


class LivePlan:
    def __init__(self, omfit, prepared, factory):
        self.omfit, self.prepared = omfit, prepared
        try:
            self.incoming = factory(str(prepared.entry), quiet=True, developerMode=False)
        except Exception as exc:
            raise TemplateError('无法载入模板树，尚未更新当前工程：' + str(exc)) from exc
        self.operations, self.guards, self.gui_paths = [], [], {}
        for name in prepared.release['roots']:
            new, old = raw(self.incoming, name), raw(omfit, name)
            if not module(new) or (old is not MISSING and not module(old)):
                raise TemplateError('模板与当前工程的模块类型不一致：' + name)
            self._module((name,), old, new)
        self.applied = False

    def _operation(self, path, old, new, data=False):
        parent = lookup(self.omfit, path[:-1])
        try:
            fingerprint = None if data else stamp(old)
        except Exception as exc:
            raise TemplateError('无法比较更新节点 ' + location(path) + '：' + str(exc)) from exc
        self.operations.append(dict(path=path, parent=parent, old=old, new=new,
                                    stamp=fingerprint, data=data))

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
        return dict(mode='live', release=self.prepared.release,
                    data_policy=self.prepared.data_policy, settings_policy=self.prepared.settings_policy,
                    updated_modules=list(self.prepared.release['roots']),
                    changes=[dict(path=location(op['path']), bytes=0,
                        action='add' if op['old'] is MISSING else 'delete' if op['new'] is MISSING else 'replace')
                             for op in self.operations])

    def _check(self, undo=False):
        for path, node, old_keys in self.guards:
            if lookup(self.omfit, path) is not node:
                raise TemplateError('工程结构已改变，请重新预览：' + location(path))
            if not undo and tuple(keys(node)) != old_keys:
                raise TemplateError('预览后节点已改变，请重新预览：' + location(path))
        for op in self.operations:
            expected = op['new'] if undo else op['old']
            if lookup(self.omfit, op['path'][:-1]) is not op['parent'] or lookup(self.omfit, op['path']) is not expected:
                raise TemplateError('待更新节点已改变，请重新预览：' + location(op['path']))
            if not op['data'] and stamp(expected) != op['stamp']:
                raise TemplateError('代码或设置已修改，不能覆盖：' + location(op['path']))

    def _put(self, op, value):
        if value is MISSING:
            del op['parent'][op['path'][-1]]
        else:
            op['parent'][op['path'][-1]] = value

    def apply(self, refresh):
        if self.applied:
            raise TemplateError('此预览已经应用，请重新预览')
        self._check()
        completed = []
        try:
            for op in self.operations:
                completed.append(op)
                self._put(op, op['new'])
                # Native SortedDict copies expressions when attaching them.
                op['new'] = lookup(self.omfit, op['path'])
            refresh(self, False)
        except Exception as exc:
            for op in reversed(completed):
                if op['old'] is MISSING and raw(op['parent'], op['path'][-1]) is MISSING:
                    continue
                self._put(op, op['old'])
            try:
                refresh(self, True)
            except Exception:
                pass
            raise TemplateError('更新失败，已恢复原节点：' + str(exc)) from exc
        for op in self.operations:
            op['stamp'] = None if op['data'] else stamp(op['new'])
        self.applied = True

    def undo(self, refresh):
        if not self.applied:
            raise TemplateError('没有可撤销的更新')
        self._check(undo=True)
        completed = []
        try:
            for op in reversed(self.operations):
                completed.append(op)
                self._put(op, op['old'])
            refresh(self, True)
        except Exception:
            for op in reversed(completed):
                self._put(op, op['new'])
            refresh(self, False)
            raise
        self.applied = False
