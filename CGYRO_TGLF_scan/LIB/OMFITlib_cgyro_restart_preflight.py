"""Compatibility entry points for scripts loaded before the optional-log fix.

``out.cgyro.timing.debug`` is a performance log, not checkpoint state. Its
absence or an empty file must not reject a restart, and a filename embedded in
the solver binary cannot establish a restart requirement. Current submission
scripts use the checkpoint validation in OMFITlib_cgyro_continue directly.

Keep these old callable names so updating an open project does not break a
previously loaded submission script. Neither entry point reads files, probes
the server, changes the selected points, nor creates synthetic timer history.
"""


def check_debug_history(directory, point, runtime, ui, server, workdir, tunnel, cache):
    """Deprecated compatibility no-op; the optional log is not validated."""
    return None


def filter_restart_points(plan, runtime, ui, server, workdir, tunnel, cache):
    """Deprecated compatibility no-op; actual checkpoint validators select points."""
    return plan
