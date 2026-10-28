"""Conservative cache provenance for TGLF; no external execution or pickle use.

SETUP.solver_sha256 is an optional, operator-recorded digest of the actual
solver binary. Without it we keep provenance for inspection but never reuse a
result. A mutable path or environment command is not a binary identity.
"""
from builtins import bool, dict, float, int, isinstance, len, list, sorted, str, tuple, type
import hashlib
import json
import math
import re
from collections.abc import Mapping


def _canonical(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return {"float": value.hex()}  # finite, nan and infinity are unambiguous
    if isinstance(value, Mapping) or hasattr(value, "items"):
        pairs = [(_canonical(k), _canonical(v)) for k, v in value.items()]
        return {"mapping": sorted(pairs, key=lambda kv: json.dumps(kv[0], sort_keys=True))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if hasattr(value, "tolist"):
        return _canonical(value.tolist())
    raise TypeError("Cache identity cannot encode " + type(value).__name__)


def _source_texts(branch, prefix=""):
    texts = []
    for key, value in branch.items():
        path = prefix + "/" + str(key)
        if hasattr(value, "read"):
            texts.append((path, value.read()))
        elif isinstance(value, str):  # supports isolated tests and in-memory code
            texts.append((path, value))
        elif hasattr(value, "items"):
            texts.extend(_source_texts(value, path))
        else:
            raise TypeError("Cannot read workflow source " + path)
    return sorted(texts)


def provenance(module, input_tglf, mode, extra=None):
    """Hash the complete input, constraints, settings and executable workflow.

    Missing/unsupported inputs or code disable reuse rather than falling back
    to a path, object repr, or an incomplete identity.
    """
    try:
        settings = module["SETTINGS"]
        solver = str(settings.get("SETUP", {}).get("solver_sha256", "")).strip().lower()
        known_solver = re.fullmatch(r"[0-9a-f]{64}", solver) is not None
        payload = {
            "schema": 1, "mode": mode, "input": input_tglf,
            "constraints": list(module.get("constraint_vars", {}).items()),
            "settings": settings, "extra": extra,
            "source": {name: _source_texts(module.get(name, {}), name) for name in ("SCRIPTS", "LIB")},
        }
        if not payload["source"]["SCRIPTS"]:
            raise ValueError("Workflow source is missing")
        encoded = json.dumps(_canonical(payload), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return {"schema": 1, "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                "solver_sha256": solver if known_solver else None, "reusable": known_solver,
                "reason": "operator-recorded solver digest" if known_solver else "solver digest unavailable; recompute"}
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return {"schema": 1, "sha256": None, "solver_sha256": None, "reusable": False, "reason": str(exc)}


def matches(previous, current):
    return bool(previous and current and current.get("reusable", None) and previous.get("reusable", None)
                and current.get("sha256", None) and previous.get("sha256", None) == current["sha256"]
                and previous.get("solver_sha256", None) == current.get("solver_sha256", None))


def forget_workbench(module, prefix):
    """Invalidate metadata only for the native branch being replaced."""
    index = module.get('_workbench_index', {})
    prefix = tuple(prefix)
    for path in list(index):
        if path[:len(prefix)] == prefix:
            del index[path]


def flux_data(result):
    """Return a usable legacy flux row set, or report the saved point failure.

    The batch runner returns either an OMFIT TGLF result or a diagnostic mapping
    with ``_load_error``. Both the radial and parameter scans must distinguish
    these outcomes before adding a point to their public result branches.
    """
    if result is None:
        raise ValueError('No result returned')
    if result.get('_load_error', None):
        raise ValueError(result['_load_error'])
    data = result['gbflux']['data']
    if not len(data) or data[0][0] != 'elec':
        raise ValueError('TGLF flux output is missing the electron row')
    return data


def prepare(results, spectra, key, records, current, factory=dict):
    """Invalidate result pairs together; only proven identical inputs may resume.

    Metadata stays outside numeric result keys consumed by legacy plotters.
    A matching digest does not imply all points exist: callers must check both
    the flux and spectrum records before deciding a point can be skipped.
    """
    if not matches(records.get(key, None), current):
        results[key] = factory()
        spectra[key] = factory()
    results.setdefault(key, factory())
    spectra.setdefault(key, factory())
    records[key] = current
