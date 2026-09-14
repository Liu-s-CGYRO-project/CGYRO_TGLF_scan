"""Conservative cache provenance for TGLF; no external execution or pickle use.

SETUP.solver_sha256 is an optional, operator-recorded digest of the actual
solver binary. Without it we keep provenance for inspection but never reuse a
result. A mutable path or environment command is not a binary identity.
"""
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


def prepare(results, spectra, key, records, current, factory=dict):
    """Discard stale or unproven derived data before running any new points."""
    if not matches(records.get(key, None), current):
        results[key] = factory()
        spectra[key] = factory()
    results.setdefault(key, factory())
    spectra.setdefault(key, factory())
    records[key] = current
