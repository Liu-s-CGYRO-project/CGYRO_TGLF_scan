"""The mapping contract used by the target OMFIT SortedDict/OMFITtree.

This lightweight fixture deliberately does not emulate the complete framework.
tools/validate_project_mapping.py also runs the compatibility tests with the
unchanged SortedDict class and lazy-loading decorators from an OMFIT checkout.
"""


class OMFITMapping(dict):
    def get(self, key, default):
        if key not in self:
            return default
        return self[key]

    def update(self, other):
        for key, value in other.items():
            self[key] = value

    def setdefault(self, key, default):
        if key not in self:
            self[key] = default
        return self[key]


def treeify(value, factory):
    """Convert fixture branches, retaining arrays and mocked solver boundaries."""
    if isinstance(value, dict):
        result = factory()
        for key, item in value.items():
            result[key] = treeify(item, factory)
        return result
    if isinstance(value, list):
        return [treeify(item, factory) for item in value]
    if isinstance(value, tuple):
        return tuple(treeify(item, factory) for item in value)
    return value
