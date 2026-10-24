"""The small persisted contract for browsable, single-owner CGYRO indexes.

``__RESULT_REF__`` is the identity used by readers and garbage collection.
The optional visible ``data`` entry is only a native OMFIT expression: native
save writes its expression text and never traverses or deploys its target.
Do not replace it with a Python object alias or a copied OMFITcgyro instance.
Metadata walks must stop at the reference before inspecting ``data``.
"""
from builtins import (ImportError, ValueError, any, dict, hasattr, id, isinstance,
                      list, object, set, str, tuple, type, vars)
from copy import deepcopy
import re

REF, BROWSE = '__RESULT_REF__', 'data'


def is_native_file(node):
    """Classify opaque native file leaves without touching reader attributes.

    A tree also has ``filename``; checking that attribute can both misclassify
    a container and trigger lazy I/O. Call metadata_value first when traversing
    persisted metadata, then treat the remaining wrappers as opaque owners.
    """
    return any(base.__name__ in ('OMFITobject', 'OMFITlazyLoad') for base in type(node).__mro__)


def metadata_value(node):
    """Materialize persisted metadata containers, retaining lazy file readers."""
    if any(base.__name__ == 'OMFITlazyLoad' for base in type(node).__mro__):
        attributes = vars(node)
        kind = attributes.get('tp', attributes.get('cls', ''))
        if kind in ('OMFITpickle', 'OMFITtree', 'OMFITmodule', 'SortedDict', 'OMFITlist'):
            return node.__lazy_load__()
    return node


def browse_code(key):
    """Generate one fixed lookup; no user-supplied Python or tree path."""
    if not isinstance(key, str) or re.fullmatch(r'[0-9a-f]{64}', key) is None:
        raise ValueError('Invalid CGYRO result reference')
    # ``root`` is the containing native CGYRO module. Unlike an absolute path,
    # this keeps working after project/module renaming and save/reload.
    return "root['RUN_DB']['__STORE__']['" + key + "']"


def browse_matches(value, key):
    """Validate without calling _value_, getattr, repr, or a reader method."""
    return (any(base.__name__ == 'OMFITexpression' for base in type(value).__mro__)
            and object.__getattribute__(value, 'expression') == browse_code(key))


def validate_reference(node, key):
    """Permit legacy indexes and exactly one controlled browser convenience."""
    browse_code(key)
    names = set(node.keys())
    if names == {REF}:
        return key
    if names != {REF, BROWSE} or not browse_matches(node[BROWSE], key):
        raise ValueError('Invalid CGYRO result reference')
    return key


def same_result_reference(first, second):
    """Compare immutable owner identities without evaluating browser links.

    Rebuilding an index creates a fresh ``data`` expression. Dictionary equality
    would invoke OMFITexpression.__eq__ and read/evaluate that GUI convenience,
    even when both indexes have the same verified digest. Validate each index
    shape, then compare its sole persisted owner key. Unindexed file readers
    can only prove identity by being the very same object, never by filename.
    """
    first, second = metadata_value(first), metadata_value(second)
    def key(node):
        if not is_native_file(node) and hasattr(node, 'items') and REF in node:
            return validate_reference(node, metadata_value(node[REF]))
        return None
    first_key, second_key = key(first), key(second)
    if first_key is not None or second_key is not None:
        return first_key is not None and second_key is not None and first_key == second_key
    return first is second and is_native_file(first)


def browse_expression(key):
    """Build inert native metadata; construction must not load a result.

    The native expression constructor/deepcopy eagerly tries evaluating the
    lookup. Assemble its documented state directly while this index is still
    off-tree; the browser evaluates it after native assignment sets its parent.
    Plain Python/headless hosts may omit this optional browser convenience.
    """
    code = browse_code(key)
    try:
        from omfit_classes.omfit_base import OMFITiterableExpression
    except ImportError:
        return None
    value = object.__new__(OMFITiterableExpression)
    value.expression, value.lastEval = code, None
    return value


def make_reference(key, factory=dict, browse=True):
    browse_code(key)
    result = factory()
    result[REF] = key
    if browse:
        value = browse_expression(key)
        if value is not None:
            result[BROWSE] = value
    return result


def copy_result_tree(value, factory=dict):
    """Copy archive indexes without evaluating off-tree browser expressions.

    Only containers holding result references need rebuilding. Ordinary
    metadata (including mappings with path keys) and native file owners keep
    their normal deepcopy behavior, including custom reader types and state.
    """
    def contains_reference(node, seen):
        node = metadata_value(node)
        if id(node) in seen:
            return False
        seen.add(id(node))
        if is_native_file(node):
            return False
        if hasattr(node, 'items'):
            if REF in node:
                validate_reference(node, metadata_value(node[REF]))
                return True
            return any(contains_reference(child, seen) for child in node.values())
        if isinstance(node, (list, tuple)):
            return any(contains_reference(child, seen) for child in node)
        return False

    def clone(node, memo):
        node = metadata_value(node)
        if id(node) in memo:
            return memo[id(node)]
        if not contains_reference(node, set()):
            return deepcopy(node, memo)
        if hasattr(node, 'items'):
            if REF in node:
                key = validate_reference(node, metadata_value(node[REF]))
                copied = make_reference(key, factory)
                memo[id(node)] = copied
                return copied
            copied = factory()
            memo[id(node)] = copied
            for key, child in node.items():
                copied[deepcopy(key, memo)] = clone(child, memo)
            return copied
        copied = []
        memo[id(node)] = copied
        copied.extend(clone(child, memo) for child in node)
        if isinstance(node, tuple):
            copied = tuple(copied)
            memo[id(node)] = copied
        return copied

    return clone(value, {})
