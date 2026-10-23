"""Compatibility entry for explicit maintenance of an already updated project.

This source script never downloads an older pinned release. Projects missing
current archive interfaces must use the release-specific offline updater built
by build_maintenance_commandbox.py. Actual compaction uses the same native task
as the GUI, so archive policy has only one implementation.
"""
from builtins import RuntimeError, any, callable, getattr, globals


UPGRADE_MESSAGE = (
    'Update the project and matching manager with the release-specific '
    'omfit-maintain-<version>.py before compaction. '
    'See COMMAND_BOX_COMPACTION.md. No project data was changed.'
)


def compact(omfit, proxy=None):
    """Keep the old call signature; proxy is obsolete because no download occurs."""
    if not callable(getattr(omfit, 'get', None)):
        raise RuntimeError(UPGRADE_MESSAGE)
    project = omfit.get('CGYRO_TGLF_scan', {})
    if not callable(getattr(project, 'get', None)):
        raise RuntimeError(UPGRADE_MESSAGE)
    library = project.get('LIB', {})
    scripts = project.get('SCRIPTS', {})
    if not callable(getattr(library, 'get', None)) or not callable(getattr(scripts, 'get', None)):
        raise RuntimeError(UPGRADE_MESSAGE)
    task = scripts.get('compact_cgyro_storage', None)
    # These interfaces distinguish the current contract from older readers
    # that used the same layout version number but lacked browsable references.
    required = ('OMFITlib_cgyro_reference', 'OMFITlib_cgyro_retention')
    if task is None or not callable(getattr(task, 'run', None)) or any(name not in library for name in required):
        raise RuntimeError(UPGRADE_MESSAGE)
    return task.run()


if 'OMFIT' in globals():
    _cgyro_compact_report = compact(globals()['OMFIT'])
elif __name__ == '__main__':
    raise RuntimeError('Run this script inside the OMFIT Command Box; ' + UPGRADE_MESSAGE)
