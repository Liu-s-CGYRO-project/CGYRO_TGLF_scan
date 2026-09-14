"""Read OMFIT ZIPs without executing expressions or deserializing results.

The saved tree, rather than filename extensions, defines template ownership.
Only ordinary, self-contained OMFIT project ZIPs are accepted.
"""
from builtins import all, any, bool, bytes, dict, float, int, len, list, max, min, open, range, set, sorted, str, sum, tuple, zip
import ast
import hashlib
import json
import math
from pathlib import Path
import stat
import zipfile

SEPARATOR = ' <-:-:-> '
CODE_BRANCHES = frozenset(('SCRIPTS', 'PLOTS', 'GUIS', 'LIB', 'TEMPLATES', 'WORKFLOWS', 'SOURCE', 'DOCS', 'TESTS'))
SETTINGS_BRANCHES = frozenset(('SETTINGS', '__SETTINGS_AT_IMPORT__'))
MAX_METADATA = 32 * 1024 * 1024
CHUNK = 4 * 1024 * 1024


class TemplateError(ValueError):
    """A reviewable input/compatibility error, suitable for display in the UI."""


def safe_name(name):
    """Validate a relative POSIX member path without rewriting Linux names."""
    if not isinstance(name, str) or not name or any(ord(c) < 32 for c in name):
        raise TemplateError('无效的归档路径：' + repr(name))
    parts = (name[:-1] if name.endswith('/') else name).split('/')
    if any(not part or part in ('.', '..') for part in parts):
        raise TemplateError('归档路径必须是相对路径，不能跨目录或包含空路径段：' + name)
    return '/'.join(parts)


def member_name(name):
    # OMFIT writes some directory entries with a leading './'.
    return safe_name(name[2:] if name.startswith('./') else name)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise TemplateError('JSON 出现重复键：' + key)
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc:
        raise TemplateError('JSON 无法读取：' + str(exc)) from exc


def location_keys(text):
    """OMFIT locations allow literal subscripts only; never use eval()."""
    try:
        expr = ast.parse('tree' + text, mode='eval').body
        keys = []
        while isinstance(expr, ast.Subscript):
            key = ast.literal_eval(expr.slice)
            if not isinstance(key, (str, int, float, tuple)) or isinstance(key, bool):
                raise ValueError('unsupported key')
            hash(key)
            if isinstance(key, float) and not math.isfinite(key):
                raise ValueError('non-finite key')
            keys.append(key)
            expr = expr.value
        if not isinstance(expr, ast.Name) or expr.id != 'tree' or not keys:
            raise ValueError('not a literal location')
        return tuple(reversed(keys))
    except (SyntaxError, ValueError, TypeError) as exc:
        raise TemplateError('不支持的 OMFIT 树路径：' + text) from exc


class Row:
    def __init__(self, text):
        self.fields = text.split(SEPARATOR)
        if len(self.fields) != 4:
            raise TemplateError('OMFITsave.txt 行格式不支持：' + text[:120])
        self.keys = location_keys(self.fields[0])
        self.kind = self.fields[1]
        value = self.fields[2]
        self.ref = safe_name(value[2:]) if value.startswith('./') else None
        if value and not value.startswith(('./', '_')):
            raise TemplateError('模板需要自包含文件，发现外部引用：' + self.fields[0])

    def text(self):
        return SEPARATOR.join(self.fields)


def parse_tree(raw):
    try:
        rows = [Row(line) for line in raw.decode('utf-8-sig').splitlines() if line.strip()]
    except UnicodeError as exc:
        raise TemplateError('OMFITsave.txt 需要 UTF-8 编码') from exc
    keys = [r.keys for r in rows]
    if len(keys) != len(set(keys)):
        raise TemplateError('OMFITsave.txt 出现重复树节点')
    return rows


def tree_bytes(rows):
    # OMFIT's project-info reader associates SETTINGS with the latest open module.
    # Preserve a depth-first traversal, not just parent-before-child depth sorting.
    rows = list(rows)
    by_key = {row.keys: row for row in rows}
    if len(by_key) != len(rows):
        raise TemplateError('不能写入重复树节点')
    children = {}
    for row in rows:
        for depth in range(1, len(row.keys) + 1):
            prefix = row.keys[:depth]
            children.setdefault(prefix[:-1], {}).setdefault(prefix, None)
    ordered = []
    def visit(prefix):
        if prefix in by_key:
            ordered.append(by_key[prefix].text())
        for child in children.get(prefix, {}):
            visit(child)
    visit(())
    return ('\n'.join(ordered) + '\n').encode('utf-8')


def sha_stream(stream, progress=None):
    digest = hashlib.sha256()
    count = 0
    while True:
        block = stream.read(CHUNK)
        if not block:
            break
        digest.update(block)
        count += len(block)
        if progress:
            progress(len(block))
    return digest.hexdigest(), count


class Project:
    def __init__(self, filename, payload=False):
        self.path = Path(filename).expanduser().resolve()
        self.z = zipfile.ZipFile(self.path)
        try:
            infos = self.z.infolist()
            if len(infos) > 500000:
                raise TemplateError('归档文件条目过多')
            # Use the stored POSIX name, including case and literal backslashes.
            names = [member_name(i.orig_filename) for i in infos]
            if len(names) != len(set(names)):
                raise TemplateError('归档含重复路径')
            for info in infos:
                if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                    raise TemplateError('不支持符号链接或加密 ZIP：' + info.filename)
            self.prefix = 'payload/' if payload else ''
            if not payload and 'OMFITsave.txt' not in names:
                candidates = [n[:-len('OMFITsave.txt')] for n in names
                              if n.count('/') == 1 and n.endswith('/OMFITsave.txt')]
                if len(candidates) != 1 or not all(n.startswith(candidates[0]) or n + '/' == candidates[0] for n in names):
                    raise TemplateError('ZIP 根目录或单一顶层目录下需要 OMFITsave.txt')
                self.prefix = candidates[0]
            self.files = {name[len(self.prefix):]: info for name, info in zip(names, infos)
                          if not info.is_dir() and name.startswith(self.prefix)}
            self.directories = {name[len(self.prefix):] for name, info in zip(names, infos)
                                if info.is_dir() and name.startswith(self.prefix)}
            if 'OMFITsave.txt' not in self.files:
                raise TemplateError('归档缺少 OMFITsave.txt')
            self.rows = parse_tree(self.read('OMFITsave.txt'))
            self.modules = {r.keys for r in self.rows if r.kind == 'OMFITmodule'}
            self.roots = sorted({r.keys[0] for r in self.rows if len(r.keys) == 1 and r.kind == 'OMFITmodule'})
            self._stat = self.stamp()
        except Exception:
            self.z.close()
            raise

    def close(self):
        self.z.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def stamp(self):
        st = self.path.stat()
        entries = [(i.filename, i.file_size, i.CRC, i.compress_size) for i in self.z.infolist()]
        return [st.st_size, st.st_mtime_ns, hashlib.sha256(json_bytes(entries)).hexdigest()]

    def read(self, name, limit=MAX_METADATA):
        info = self.files.get(name)
        if info is None:
            raise TemplateError('归档缺少引用文件：' + name)
        if info.file_size > limit:
            raise TemplateError('元数据文件过大：' + name)
        return self.z.read(info)

    def selected(self, row, roots):
        return row.keys[0] in roots

    def category(self, row):
        if row.kind == 'OMFITmodule':
            return 'structure'
        parents = [row.keys[:i] for i in range(1, len(row.keys)) if row.keys[:i] in self.modules]
        module = parents[-1] if parents else ()
        rest = row.keys[len(module):]
        branch = rest[0]
        if branch in CODE_BRANCHES or branch in ('help', 'license', 'README'):
            return 'code'
        if branch in SETTINGS_BRANCHES:
            return 'settings'
        if len(rest) == 1 and row.kind.startswith('OMFITpython'):
            return 'code'
        return 'data'

    def ownership(self, roots):
        if not roots or not all(isinstance(root, str) and root in self.roots for root in roots):
            raise TemplateError('请选择 ZIP 中存在的顶层 OMFIT 模块')
        refs = {}
        for row in self.rows:
            if row.ref and self.selected(row, roots):
                category = self.category(row)
                if row.ref in refs and refs[row.ref] != category:
                    raise TemplateError('代码与数据共用一个文件引用：' + row.ref)
                refs[row.ref] = category
        used = set()
        owned = {}
        for filename in self.files:
            parts = filename.split('/')
            matches = [p for p in ('/'.join(parts[:i]) for i in range(len(parts), 0, -1)) if p in refs]
            if matches:
                if len({refs[p] for p in matches}) > 1:
                    raise TemplateError('文件夹引用的代码／数据范围冲突：' + filename)
                owned[filename] = refs[matches[0]]
                used.update(matches)
            elif parts[0] in roots:
                # Unreferenced files are data, never silently part of the code release.
                owned[filename] = 'data'
        missing = set(refs) - used
        if missing:
            # Empty serialized directory objects are represented by ZIP directory entries.
            missing -= self.directories
        if missing:
            raise TemplateError('归档缺少引用文件：' + ', '.join(sorted(missing)[:5]))
        # A selected module must not own a file also referenced outside its scope.
        for row in self.rows:
            if row.ref and not self.selected(row, roots):
                if any(n == row.ref or n.startswith(row.ref + '/') for n in owned):
                    raise TemplateError('模块和外部树共用文件；请先在 OMFIT 另存完整独立工程：' + row.ref)
        return owned

    def digest(self, name, progress=None):
        with self.z.open(self.files[name]) as stream:
            return sha_stream(stream, progress)[0]

    def require_entry_first(self):
        """Our output convention for native OMFIT ZIP loading.

        cherry_pick_OMFITsave derives the project directory from namelist()[0].
        Keep accepting historical input order, but always emit the actual tree
        entry first so both complete and selective native loads find it.
        """
        if self.z.infolist()[0].filename != self.files['OMFITsave.txt'].filename:
            raise TemplateError('ZIP 首个条目不是工程入口 OMFITsave.txt；请使用“修复 ZIP 入口”另存新工程。')


def merge_defaults(defaults, current):
    """Retain existing values; add new keys. Module identity comes from release."""
    if isinstance(defaults, dict) and isinstance(current, dict):
        result = dict(defaults)
        for key, value in current.items():
            result[key] = merge_defaults(defaults[key], value) if key in defaults else value
        return result
    return current


def contains_path(mapping, keys):
    for key in keys:
        if not isinstance(mapping, dict) or key not in mapping:
            return False
        mapping = mapping[key]
    return True


def human_size(size):
    size = float(size)
    for suffix in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if size < 1024 or suffix == 'TiB':
            return '{:.1f} {}'.format(size, suffix)
        size /= 1024
