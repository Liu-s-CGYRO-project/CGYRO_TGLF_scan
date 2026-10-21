"""Bound CGYRO temporary copies and remove only verified staging directories.

The 100 GiB limit applies once at the start of a run/batch, not to its peak.
Every subsequent copy checks actual free space. Never sweep
/tmp by age/name, remove another session, or delete a RUN_DB physical owner.
"""
from builtins import (FileNotFoundError, RuntimeError, ValueError, any, dict, int, iter, len,
                      max, open, set, str)
import getpass
import hashlib
import os
import re
import shutil
import tempfile
import zipfile

LIMIT_BYTES = 100 * 1024 ** 3
START_LIMIT_POLICY_VERSION = 1


def _inside(path, parent):
    try:
        return os.path.commonpath((os.path.realpath(path), os.path.realpath(parent))) == os.path.realpath(parent)
    except ValueError:
        return False


def directory_bytes(directory):
    """Count regular files without following symlinks or reading file payloads."""
    total = 0
    def failed(error):
        raise error
    for parent, directories, names in os.walk(directory, followlinks=False, onerror=failed):
        directories[:] = [name for name in directories if not os.path.islink(os.path.join(parent, name))]
        for name in names:
            path = os.path.join(parent, name)
            if not os.path.islink(path):
                try:
                    total += os.stat(path).st_size
                except FileNotFoundError:
                    pass  # Another process may finish its own temporary file.
    return total


def _space_location(path, tmp_root=None):
    """Resolve the accounting scope without traversing its files."""
    path = os.path.abspath(path)
    existing = path
    while not os.path.exists(existing):
        parent = os.path.dirname(existing)
        if parent == existing:
            raise ValueError('No existing parent for temporary work directory')
        existing = parent
    temporary = os.path.realpath(tmp_root or tempfile.gettempdir())
    scope = ''
    if _inside(path, temporary):
        scope = temporary
        # Standard OMFIT uses /tmp/<user>/OMFIT/<session>. Count all that
        # user's sessions, while neither scanning nor deleting other users.
        user_root = os.path.join(temporary, getpass.getuser())
        if _inside(path, user_root):
            scope = user_root
    return path, scope, existing


def space_report(path, tmp_root=None):
    """Inspect the user's temp area, and free space on the destination device."""
    path, scope, existing = _space_location(path, tmp_root)
    return dict(path=path, scope=scope, used_bytes=directory_bytes(scope) if scope else 0,
                free_bytes=shutil.disk_usage(existing).free, limit_bytes=LIMIT_BYTES)


def check_start_capacity(path):
    """Check existing usage once, before this run's preparation/submission.

    The caller checks only the first case of a batch. A later peak above the
    start limit is allowed; this does not skip per-copy filesystem free space.
    """
    report = space_report(path)
    if report['scope'] and report['used_bytes'] > LIMIT_BYTES:
        raise RuntimeError('CGYRO cannot start above 100 GiB of existing temporary data: {} '
                           '({:.2f} GiB used). Compact or save existing data first; '
                           'RUN_DB and remote jobs are unchanged.'.format(
                               report['scope'], report['used_bytes'] / 1024**3))
    return report


def ensure_capacity(path, additional_bytes=0):
    """Check real free space for this copy, without rescanning all /tmp files."""
    required = max(0, int(additional_bytes))
    path, scope, existing = _space_location(path)
    free = shutil.disk_usage(existing).free
    if required > free:
        raise RuntimeError('Insufficient free space for CGYRO temporary copy: ' + str(path))
    return dict(path=path, scope=scope, used_bytes=None, free_bytes=free,
                limit_bytes=LIMIT_BYTES, start_limit_applied=False)


def _digest(stream):
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
        value.update(block)
    return value.hexdigest()


def clean_stage(workdir, token, point, packed, checksums, protected=()):
    """Delete this run's reproducible expansion only after its ZIP verifies.

    ZIP and RUN_DB owners are kept. The target must be runs/<UUID>/staging/pN,
    with no symlink component or protected reader. Unexpected paths fail shut.
    """
    workdir = os.path.abspath(workdir)
    if (re.fullmatch(r'[0-9a-f]{32}', str(token)) is None or
            os.path.basename(workdir) != str(token) or os.path.basename(os.path.dirname(workdir)) != 'runs' or
            re.fullmatch(r'p[0-9]{6,}', str(point)) is None):
        raise ValueError('Refusing cleanup of an unowned CGYRO staging path')
    stage = os.path.join(workdir, 'staging', str(point))
    if not os.path.exists(stage):
        return 0
    if os.path.realpath(stage) != stage or any(_inside(path, stage) for path in protected if path):
        raise ValueError('Staging is linked or still owned by a saved reader')
    for parent, directories, names in os.walk(stage, followlinks=False):
        if any(os.path.islink(os.path.join(parent, name)) for name in directories + names):
            raise ValueError('Linked staging file; original directory retained')
    with zipfile.ZipFile(packed) as archive:
        if (not checksums or len(archive.namelist()) != len(checksums)
                or set(archive.namelist()) != set(checksums)):
            raise ValueError('Submission ZIP member list changed; staging retained')
        for name, expected in checksums.items():
            if not name or name in ('.', '..') or '/' in name or '\\' in name:
                raise ValueError('Invalid staged ZIP member')
            with archive.open(name) as source, open(os.path.join(stage, name), 'rb') as expanded:
                if _digest(source) != expected or _digest(expanded) != expected:
                    raise ValueError('Staged input differs from its ZIP; directory retained')
    size = directory_bytes(stage)
    # Paths were resolved and validated above; recursive removal is confined
    # to this exact generated point staging directory, never the run root.
    shutil.rmtree(stage)
    return size
