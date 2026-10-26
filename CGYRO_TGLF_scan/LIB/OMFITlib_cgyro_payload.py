"""File-level storage for immutable CGYRO results.

RUN_DB owns each byte stream once in __STORE__/__FILES__. A result owner is a
small manifest of relative names, sizes and SHA256 digests. Native OMFIT save
therefore writes one physical file per digest, even if several runs share it.
Hard-linking ordinary result directories would not deduplicate a saved ZIP.

Readers receive private, disposable native directories. Never hard-link these
to the file pool: an editable input reader must not alter another result. The
bounded process cache lives on the native reader module, outside project data,
and is not saved. It survives OMFIT's per-callback project import cleanup.
"""
from builtins import (AttributeError, BaseException, RuntimeError, TypeError, ValueError, all, any, bool, dict, getattr, id,
                      int, isinstance, iter, len, list, object, open, property, range, set, sorted, str, sum, tuple, type)
from collections import OrderedDict
import hashlib
import json
import os
import re
from weakref import WeakValueDictionary, ref
import omfit_classes.omfit_gacode as native_readers
from omfit_classes.omfit_path import OMFITpath
from OMFITlib_cgyro_db import metadata_value, result_pool, rollback_actions, storage_state
from OMFITlib_cgyro_reference import is_native_file
from OMFITlib_cgyro_storage_files import FILE_STORE, file_digest, native_kind
from OMFITlib_cgyro_scratch import ensure_capacity

PACKED = '__CGYRO_FILES__'
FORMAT_VERSION = 1
VIEW_CACHE_SIZE = 4
COPY_CHUNK = 4 * 1024 * 1024


def content_key(files):
    raw = json.dumps(sorted(files), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def is_packed(owner):
    owner = metadata_value(owner)
    # Native OMFITcgyro is also a dict. Its membership operator loads pygacode
    # arrays, so test reader identity before inspecting any metadata keys.
    return not is_native_file(owner) and isinstance(owner, dict) and PACKED in owner


def inventory(owner, key):
    """Validate the complete manifest before resolving any filesystem path."""
    owner = metadata_value(owner)
    if (not is_packed(owner) or set(owner) != {PACKED, 'inventory', 'test_mode'} or
            owner[PACKED] != FORMAT_VERSION or not isinstance(owner['test_mode'], bool)):
        raise ValueError('Invalid CGYRO file manifest: ' + str(key))
    rows = json.loads(owner['inventory'])
    if not isinstance(rows, list) or not rows:
        raise ValueError('Empty CGYRO file manifest')
    names = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError('Invalid CGYRO file inventory row')
        name, size, digest = row
        if (not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name or
                any(part in ('', '.', '..') for part in name.split('/')) or name in names or
                not isinstance(size, int) or isinstance(size, bool) or size < 0 or
                not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None):
            raise ValueError('Unsafe or duplicate CGYRO file inventory row')
        names.add(name)
    if any('/'.join(name.split('/')[:i]) in names for name in names for i in range(1, len(name.split('/')))):
        raise ValueError('File/directory collision in CGYRO manifest')
    if content_key(rows) != key:
        raise ValueError('CGYRO file manifest does not match its result identity')
    return rows


def sources(module, owner, key):
    """Cheap structural validation; byte verification happens on copy/read."""
    pool = metadata_value(result_pool(module).get(FILE_STORE, {}))
    rows = []
    for name, size, digest in inventory(owner, key):
        blob = pool.get(digest, None)
        if blob is None or not native_kind(blob, 'OMFITpath'):
            raise ValueError('Missing physical CGYRO result file: ' + digest)
        path = blob.filename
        if not os.path.isfile(path) or os.path.islink(path) or os.path.getsize(path) != size:
            raise ValueError('Missing or changed CGYRO result file: ' + digest)
        rows.append((name, size, digest, path))
    return rows


def _copy_verified(source, target, size, expected, mode='xb'):
    digest, copied = hashlib.sha256(), 0
    with open(source, 'rb') as incoming, open(target, mode) as outgoing:
        for chunk in iter(lambda: incoming.read(COPY_CHUNK), b''):
            outgoing.write(chunk)
            digest.update(chunk)
            copied += len(chunk)
    if copied != size or digest.hexdigest() != expected:
        raise ValueError('CGYRO file changed while copying: ' + source)


def _stamps(paths):
    return tuple((path, os.stat(path).st_size, os.stat(path).st_mtime_ns) for path in paths)


def materialize_owner(module, key):
    """Create a private native directory only when a reader is actually used."""
    owner = result_pool(module).get(key, None)
    if native_kind(owner, 'OMFITcgyro'):
        return owner
    if not is_packed(owner):
        raise ValueError('Missing physical CGYRO result: ' + str(key))
    rows = sources(module, owner, key)
    stamp = _stamps([row[3] for row in rows])
    cache = getattr(native_readers, '_cgyro_file_views', None)
    if cache is None:
        cache = OrderedDict()
        native_readers._cgyro_file_views = cache
    cache_key = key, stamp, bool(owner['test_mode'])
    previous = cache.pop(cache_key, None)
    if previous is not None:
        reader, paths, expected = previous
        if all(os.path.isfile(path) for path in paths) and _stamps(paths) == expected:
            cache[cache_key] = previous
            return reader
    reader = native_readers.OMFITcgyro('', test_mode=owner['test_mode'])
    ensure_capacity(reader.filename, sum(row[1] for row in rows))
    paths = []
    for name, size, digest, source in rows:
        target = os.path.join(reader.filename, *name.split('/'))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        _copy_verified(source, target, size, digest)
        paths.append(target)
    if _stamps([row[3] for row in rows]) != stamp:
        raise RuntimeError('Stored CGYRO files changed during materialization')
    cache[cache_key] = (reader, paths, _stamps(paths))
    while len(cache) > VIEW_CACHE_SIZE:
        cache.popitem(last=False)  # Native OMFIT owns disposable-directory GC.
    return reader


def _deferred_reader(module, key):
    """Build a runtime-only native adapter, never a persisted custom class.

    Native execGlobLoc removes top-level subclasses of OMFITobject/SortedDict
    from LIB namespaces. Keep this class inside the factory. Listing scans
    must not expand result files; only actual reads need a private directory.
    """
    class DeferredResult(native_readers.OMFITcgyro):
        def __init__(self):
            object.__setattr__(self, '_payload_module', module)
            object.__setattr__(self, '_payload_key', key)

        def _payload_reader(self):
            reader = materialize_owner(module, key)
            try:
                object.__setattr__(self, '_payload_active', ref(reader))
            except TypeError:
                pass  # Plain mapping adapters need not support weak references.
            return reader

        def _payload_cached(self):
            active = object.__getattribute__(self, '__dict__').get('_payload_active', None)
            return None if active is None else active()

        @property
        def dynaLoad(self):
            # Native tree refresh probes collapsed rows. Never create a
            # directory just to ask whether that row has been opened. A weak
            # reference also lets the bounded runtime cache evict old views.
            reader = self._payload_cached()
            return True if reader is None else getattr(reader, 'dynaLoad', True)

        @dynaLoad.setter
        def dynaLoad(self, value):
            reader = self._payload_cached()
            if reader is not None:
                reader.dynaLoad = value

        def __tree_repr__(self):
            return ('CGYRO result (expand to load)' if self.dynaLoad else 'CGYRO result (loaded)'), []

        def _payload_file(self, name):
            owner = result_pool(module).get(key, None)
            if native_kind(owner, 'OMFITcgyro'):
                return os.path.join(owner.filename, name)
            for relative, size, digest, path in sources(module, owner, key):
                if relative == name:
                    if file_digest(path) != (size, digest):
                        raise ValueError('Stored CGYRO file was modified: ' + digest)
                    return path
            raise ValueError('Missing CGYRO result file: ' + name)

        def __getattribute__(self, name):
            if name.startswith('_payload_') or name in ('__class__', '__dict__', '__weakref__',
                                                       'dynaLoad', '__tree_repr__'):
                return object.__getattribute__(self, name)
            if name in ('modifyOriginal', 'readOnly'):
                reader = self._payload_cached()
                return False if reader is None else getattr(reader, name, False)
            return getattr(self._payload_reader(), name)

        def __getattr__(self, name):
            # Do not fall back to SortedDict.__getattr__, whose missing-attr
            # probe can dynamically load this uninitialised adapter itself.
            raise AttributeError(name)

        def __getitem__(self, name):
            return self._payload_reader()[name]

        def __iter__(self):
            # OMFIT evaluates every saved expression on reopen and calls iter
            # only to classify its value. A generator defers file copies and
            # native parsing until that iterator is actually consumed.
            yield from self._payload_reader()

        def __len__(self):
            return len(self._payload_reader())

        def __contains__(self, name):
            return name in self._payload_reader()

    return DeferredResult()


def resolve_owner(module, key, *, defer_native=False):
    """Defer file manifests; browser probes also defer legacy native owners."""
    owner = result_pool(module).get(key, None)
    native = native_kind(owner, 'OMFITcgyro')
    if native and not defer_native:
        return owner
    if not native:
        if not is_packed(owner):
            raise ValueError('Missing physical CGYRO result: ' + str(key))
        inventory(owner, key)
    cache = getattr(native_readers, '_cgyro_deferred_views', None)
    if cache is None:
        cache = WeakValueDictionary()
        native_readers._cgyro_deferred_views = cache
    cache_key = id(module), key, id(owner)
    reader = cache.get(cache_key, None)
    if reader is None:
        reader = _deferred_reader(module, key)
        cache[cache_key] = reader
    return reader


def deferred_key(module, reader):
    # Project modules are re-imported by native callbacks. A retained view can
    # belong to an earlier class definition, so compare the narrow protocol.
    if type(reader).__name__ != 'DeferredResult':
        return None
    if object.__getattribute__(reader, '_payload_module') is not module:
        raise ValueError('A deferred result belongs to another CGYRO module')
    key = object.__getattribute__(reader, '_payload_key')
    owner = result_pool(module).get(key, None)
    if not native_kind(owner, 'OMFITcgyro'):
        inventory(owner, key)
    return key


def resolve_browser(module, key):
    """Entry point for the fixed native expression, without a sys.path change."""
    # Expression evaluation also runs at project load, before any user expands
    # data. Keep the native reader type but defer its directory and arrays.
    return resolve_owner(module, key, defer_native=True)


class FilePlan:
    """Prepare independent native file owners before replacing any result."""
    def __init__(self, module, factory):
        self.module, self.factory = module, factory
        self.files = metadata_value(result_pool(module).get(FILE_STORE, {}))
        self.additions, self.manifests, self.verified, self.stamps = {}, {}, {}, {}
        self.sizes = dict(storage_state(module).get('file_bytes', {}))

    def add(self, key, reader, rows):
        if content_key(rows) != key:
            raise ValueError('Stored CGYRO result was modified: ' + key)
        for name, size, digest in rows:
            source = os.path.join(reader.filename, *name.split('/'))
            self.stamps[source] = _stamps([source])[0]
            if digest in self.files:
                owned = self.files[digest]
                if not native_kind(owned, 'OMFITpath'):
                    raise ValueError('Invalid CGYRO file owner: ' + digest)
                if digest not in self.verified:
                    self.verified[digest] = file_digest(owned.filename)
                if self.verified[digest] != (size, digest):
                    raise ValueError('Stored CGYRO file was modified: ' + digest)
            elif digest not in self.additions:
                owned = OMFITpath('')
                ensure_capacity(owned.filename, size)
                _copy_verified(source, owned.filename, size, digest, mode='wb')
                self.additions[digest] = owned
            self.sizes[digest] = size
        manifest = self.factory()
        manifest.update({PACKED: FORMAT_VERSION,
            'inventory': json.dumps(sorted(rows), ensure_ascii=False, separators=(',', ':')),
            'test_mode': bool(getattr(reader, 'test_mode', False))})
        self.manifests[key] = manifest

    def commit(self):
        # Do not delete source files. OMFIT's native object ownership controls
        # their lifetime; caller-held readers may still be in use by a plot.
        if any(_stamps([path])[0] != stamp or os.path.islink(path) for path, stamp in self.stamps.items()):
            raise RuntimeError('CGYRO result changed before file compaction commit')
        pool, state = result_pool(self.module), storage_state(self.module)
        original = {key: pool.get(key, None) for key in self.manifests}
        old_sizes, old_flag = state.get('file_bytes', None), state.get('file_dedup_version', None)
        created_files = FILE_STORE not in pool
        files = self.factory() if created_files else metadata_value(pool[FILE_STORE])
        try:
            if created_files:
                pool[FILE_STORE] = files
            for key, owner in self.additions.items():
                files[key] = owner
            for key, manifest in self.manifests.items():
                pool[key] = manifest
            state['file_bytes'] = self.sizes
            state['file_dedup_version'] = FORMAT_VERSION
        except BaseException as error:
            def restore(mapping, key, old):
                if old is None:
                    mapping.pop(key, None)
                else:
                    mapping[key] = old
            errors = rollback_actions(error, ((key, lambda key=key, old=old: restore(pool, key, old))
                                              for key, old in original.items()))
            rollback_actions(error, [('file_bytes', lambda: restore(state, 'file_bytes', old_sizes)),
                                     ('file_dedup_version', lambda: restore(state, 'file_dedup_version', old_flag))])
            if not errors:  # A rejected restore may still reference new blobs.
                rollback_actions(error, ((key, lambda key=key: files.pop(key, None)) for key in self.additions))
                if created_files and not files:
                    rollback_actions(error, [('file pool', lambda: pool.pop(FILE_STORE, None))])
            raise


def pack_results(module, inventory_reader, factory=dict):
    """Explicit maintenance: preserve identities, replace directory owners."""
    plan = FilePlan(module, factory)
    for key, owner in result_pool(module).items():
        if key == FILE_STORE:
            continue
        if is_packed(owner):
            sources(module, owner, key)
        elif native_kind(owner, 'OMFITcgyro'):
            plan.add(key, owner, inventory_reader(owner.filename))
        else:
            raise ValueError('Invalid CGYRO result owner: ' + str(key))
    if plan.manifests:
        plan.commit()
    return len(plan.manifests)
