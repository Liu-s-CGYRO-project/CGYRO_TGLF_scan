"""Freeze submission ZIPs once, independently of result-directory readers.

Cases/history contain ordinary file references. Expanded restart files are
removed from a saved branch only when the frozen ZIP contains identical bytes.
Source files, remote work directories and editable input readers are untouched.
"""
from builtins import (RuntimeError, ValueError, any, dict, getattr, hasattr, isinstance,
                      iter, len, list, open, set, str, sum, type, vars)
import hashlib
import os
import re
import zipfile
from omfit_classes.omfit_path import OMFITpath
from OMFITlib_cgyro_db import metadata_value, result_pool, storage_state
from OMFITlib_cgyro_scratch import ensure_capacity

FILE_STORE = '__FILES__'
FILE_REF = '__FILE_REF__'


def native_kind(node, name):
    """Inspect lazy reader identity without invoking its __getattr__/loader."""
    if type(node).__name__ == name:
        return True
    if any(base.__name__ == 'OMFITlazyLoad' for base in type(node).__mro__):
        attributes = vars(node)
        return attributes.get('tp', attributes.get('cls', '')) == name
    return False


def file_reference_id(node):
    node = metadata_value(node)
    if not isinstance(node, dict) or FILE_REF not in node:
        return None
    key = metadata_value(node[FILE_REF])
    if len(node) != 1 or not isinstance(key, str) or re.fullmatch(r'[0-9a-f]{64}', key) is None:
        raise ValueError('Invalid CGYRO file reference')
    return key


def resolve_file(module, node):
    node = metadata_value(node)
    key = file_reference_id(node)
    if key is None:
        return node
    owned = result_pool(module).get(FILE_STORE, {}).get(key, None)
    if owned is None or not native_kind(owned, 'OMFITpath'):
        raise ValueError('Missing physical CGYRO submission file: ' + key)
    return owned


def file_digest(path):
    if not os.path.isfile(path) or os.path.islink(path):
        raise ValueError('Missing or linked submission file: ' + str(path))
    before = os.stat(path)
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    after = os.stat(path)
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Submission file changed during validation: ' + str(path))
    return after.st_size, digest.hexdigest()


def zip_inventory(path):
    """Read every member (including CRC), never extract or execute it."""
    inventory = {}
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            name = item.filename
            if (item.is_dir() or not name or '/' in name or '\\' in name or name in ('.', '..')
                    or ':' in name or name in inventory
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe or duplicate submission ZIP member: ' + name)
            digest = hashlib.sha256()
            with archive.open(item) as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                    digest.update(block)
            inventory[name] = (item.file_size, digest.hexdigest())
    if 'input.cgyro' not in inventory:
        raise ValueError('Submission ZIP lacks input.cgyro')
    return inventory


class SubmissionFiles:
    """An off-tree transaction plan; compact_storage owns commit/rollback."""
    def __init__(self, module, factory):
        self.module, self.factory = module, factory
        self.pool = metadata_value(result_pool(module).get(FILE_STORE, {}))
        self.sizes = dict(storage_state(module).get('file_bytes', {}))
        self.additions, self.paths, self.inventories, self.stamps = {}, {}, {}, {}
        self.converted, self.raw_bytes, self.omitted_bytes = 0, 0, 0
        self.retained_files = 0

    def remember_source(self, path):
        stat = os.stat(path)
        stamp = (stat.st_size, stat.st_mtime_ns)
        if path in self.stamps and self.stamps[path] != stamp:
            raise RuntimeError('Submission source changed during planning: ' + path)
        self.stamps[path] = stamp

    def verify_sources(self):
        """Check planned omissions again immediately before replacing trees."""
        for path, expected in self.stamps.items():
            stat = os.stat(path)
            if os.path.islink(path) or (stat.st_size, stat.st_mtime_ns) != expected:
                raise RuntimeError('Submission source changed before commit: ' + path)

    def reference(self, key):
        node = self.factory()
        node[FILE_REF] = key
        return node

    def bundle(self, node):
        return (isinstance(node, dict) and 'zip' in node and
                ('input.cgyro' in node or set(node) == {'zip'}) and
                (native_kind(node['zip'], 'OMFITpath') or file_reference_id(node['zip']) is not None))

    def pending(self, node):
        if not self.bundle(node):
            return False
        return native_kind(node['zip'], 'OMFITpath') or any(
            key != 'zip' and native_kind(value, 'OMFITpath') for key, value in node.items())

    def convert_bundle(self, node, convert):
        source = resolve_file(self.module, node['zip'])
        path = os.path.abspath(source.filename)
        if path not in self.paths:
            self.remember_source(path)
            size, digest = file_digest(path)
            self.paths[path] = size, digest
        size, digest = self.paths[path]
        previous = file_reference_id(node['zip'])
        if previous is not None and previous != digest:
            raise ValueError('Frozen submission ZIP no longer matches its content key')
        if digest not in self.inventories:
            self.inventories[digest] = zip_inventory(path)
            if file_digest(path) != (size, digest):
                raise RuntimeError('Submission ZIP changed while inspecting members')
        inventory = self.inventories[digest]
        omitted = set()
        for name, value in node.items():
            # Only plain file objects can be dropped. OMFITgacode and other
            # editable readers may have unsaved changes in their Python state.
            if name != 'zip' and native_kind(value, 'OMFITpath'):
                self.remember_source(value.filename)
                if name in inventory and file_digest(value.filename) == inventory[name]:
                    omitted.add(name)
                    self.omitted_bytes += inventory[name][0]
                else:
                    self.retained_files += 1
        if digest not in self.pool and digest not in self.additions:
            owned = OMFITpath('')
            if os.path.realpath(owned.filename) == os.path.realpath(path):
                raise RuntimeError('Submission owner unexpectedly shares its source')
            ensure_capacity(owned.filename, size)
            with open(path, 'rb') as incoming, open(owned.filename, 'wb') as outgoing:
                for block in iter(lambda: incoming.read(4 * 1024 * 1024), b''):
                    outgoing.write(block)
            if file_digest(owned.filename) != (size, digest):
                raise RuntimeError('Submission ZIP changed while copying')
            self.additions[digest] = owned
        elif digest in self.pool and not native_kind(self.pool[digest], 'OMFITpath'):
            raise ValueError('Invalid submission file owner: ' + digest)
        elif digest in self.pool and file_digest(self.pool[digest].filename) != (size, digest):
            raise ValueError('Stored submission ZIP was modified: ' + digest)
        self.sizes[digest] = size
        if file_reference_id(node['zip']) is None:
            self.converted += 1
            self.raw_bytes += size
        result = self.factory()
        for name, value in node.items():
            if name not in omitted:
                result[name] = self.reference(digest) if name == 'zip' else convert(value)
        return result
