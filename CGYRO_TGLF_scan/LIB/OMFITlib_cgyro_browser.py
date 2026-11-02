"""Lightweight, runtime-only entry for saved CGYRO browser expressions.

OMFIT evaluates every saved expression on reopen. Import this module once per
LIB file, without importing storage/reader helpers or inspecting result files.
The cached functions are attributes of native code-file nodes, never RUN_DB or
saved expression values. Source edits and template updates invalidate them.
"""
from builtins import (AttributeError, TypeError, ValueError, dict, getattr, id, len, object, property, str)
import os
import re
from weakref import WeakValueDictionary, ref
import omfit_classes.omfit_gacode as native_readers


class RuntimeCache(dict):
    """Native code-node deepcopy may pickle attributes: discard this cache.

    Restoring an ordinary empty dict needs no project import hook and cannot
    retain a callable's old root, module namespace or result readers.
    """
    def __reduce__(self):
        return dict, ()

    def __call__(self, module, key):
        return self['lookup'](module, key)


def source_stamp(task):
    stat = os.stat(task.filename)
    return task.filename, stat.st_mtime_ns, stat.st_size


def payload_api(module):
    """Load the reader library on first use of a selected result only."""
    task = module['LIB']['OMFITlib_cgyro_payload']
    stamp = source_stamp(task)
    cached = getattr(task, '_cgyro_payload_api', None)
    if not cached or cached['stamp'] != stamp:
        cached = RuntimeCache(stamp=stamp, api=task.importCode(_relLoc={'root': module}))
        task._cgyro_payload_api = cached
    return cached['api']


def resolve_browser(module, key):
    """Install one session-local lookup; a new code node starts a new cache."""
    task = module['LIB']['OMFITlib_cgyro_browser']
    stamp = source_stamp(task)
    views = WeakValueDictionary()

    def lookup(module, key):
        current = module['LIB']['OMFITlib_cgyro_browser']
        if current is not task or source_stamp(current) != stamp:
            return current.importCode(_relLoc={'root': module}).resolve_browser(module, key)
        if re.fullmatch(r'[0-9a-f]{64}', key) is None:
            raise ValueError('Invalid CGYRO result reference')
        # Only exact identity lookup. No inventory parsing, hashing, copying or
        # result iteration belongs in project-load / collapsed-row probes.
        owner = module['RUN_DB']['__STORE__'].get(key, None)
        if owner is None:
            raise ValueError('Missing physical CGYRO result: ' + str(key))
        cache_key = id(module), key, id(owner)
        view = views.get(cache_key, None)
        if view is None:
            view = deferred_view(module, key)
            views[cache_key] = view
        return view

    task._cgyro_browser_entry = RuntimeCache(lookup=lookup)
    return lookup(module, key)


def deferred_view(module, key, materialize=None, file_resolver=None):
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
            reader = (materialize or payload_api(module).materialize_owner)(module, key)
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
            return (file_resolver or payload_api(module).browser_file)(module, key, name)

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

