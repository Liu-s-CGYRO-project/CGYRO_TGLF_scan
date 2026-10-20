"""Stable case identities and independent parameter scans within each case."""
from builtins import (TypeError, ValueError, all, bool, dict, enumerate, float, getattr,
                      hasattr, len, list, max, set, sorted, str)
from collections import OrderedDict
from copy import deepcopy
import math
import re


def scan_key(info, fallback=''):
    """Identify the ordered axes, not their values, ky grid or run UUID.

    A complete rescan replaces this axis combination. Other combinations stay
    independent, including 1D versus 2D with the same first axis, linked axes,
    and the fixed reference coordinate used internally for ky-only scans.
    """
    axes = info.get('scan_axes', [])
    if info.get('scan_dimensions', None) == 0 or (axes and all(axis.get('fixed', False) for axis in axes)):
        return 'KY_ONLY'
    if axes:
        return '__'.join(str(axis['name']) + ''.join('+' + str(link['name'])
            for link in axis.get('linked', [])) for axis in axes)
    return str(info.get('scan_key', '') or fallback)


def case_scans(case):
    """Read new per-scan indexes and the former single-record case schema."""
    if '__SCANS__' in case:
        return [(str(key), record['info'], record['tasks'])
                for key, record in case['__SCANS__'].items()]
    info, tasks = case.get('__INFO__', None), case.get('__TASKS__', None)
    if info is None or tasks is None:
        return []
    parameters = info.get('parameters', [])
    return [(scan_key(info, parameters[0] if parameters else ''), info, tasks)]


def scan_branch(data, info, tasks):
    """Find the one public root owned by a scan, including old isotope suffixes."""
    roots = {str(row['result_path'][0]) for row in tasks.values() if row.get('result_path', [])}
    if not roots:
        roots = set(str(key) for key in info.get('parameters', []))
    if len(roots) != 1:
        raise ValueError('Cannot identify the archived scan branch; existing results are preserved')
    original = list(roots)[0]
    if original in data:
        return original
    legacy = original + '_' + str(info.get('ion_case', ''))
    if legacy in data:
        return legacy
    raise ValueError('Missing archived scan branch: ' + original)


def store_scan(destination, data, info, tasks, factory=dict):
    """Install one complete scan into an unpublished destination tree.

    Raw results have one owner. Only metadata is grouped in __SCANS__; point
    IDs such as p000001 are local to that scan, never merged across scans.
    The public branch key remains N_THETA / N_ENERGY for ordinary 1D scans.
    """
    original = scan_branch(data, info, tasks)
    key = scan_key(info, original)
    if not key or key.startswith('__'):
        raise ValueError('Invalid archived scan identity')
    saved_info, saved_tasks = factory(), factory()
    saved_info.update(deepcopy(dict(info)))
    for point, source in tasks.items():
        row = factory()
        row.update(deepcopy(dict(source)))
        path = list(row.get('result_path', []))
        if not path:
            raise ValueError('Missing archived result path: ' + str(point))
        path[0] = key
        row['result_path'] = path
        saved_tasks[point] = row
    saved_info.update(dict(scan_key=key, parameters=[key]))
    record = factory()
    record.update(dict(info=saved_info, tasks=saved_tasks))
    destination[key] = deepcopy(data[original])
    destination.setdefault('__SCANS__', factory())[key] = record
    # Compatibility views describe the most recently published scan only.
    # New readers use __SCANS__ to offer every retained parameter scan.
    destination['__INFO__'], destination['__TASKS__'] = saved_info, saved_tasks


def combine_cases(cases, factory=dict):
    """Coalesce old revisions off-tree; later scans replace matching axes only."""
    destination = factory()
    for case in cases:
        records = case_scans(case)
        owned = {scan_branch(case, info, tasks) for _, info, tasks in records}
        for key in case:
            if not str(key).startswith('__') and key not in owned:
                # Unindexed legacy branches remain available to plot readers.
                destination[key] = deepcopy(case[key])
        for _, info, tasks in records:
            store_scan(destination, case, info, tasks, factory)
    return destination


def matching_cases(module, runid, identity):
    """Return old case keys oldest-first, with the visible revision last."""
    run = module.get('RUN_DB', {}).get(runid, {})
    _, aliases = latest_cases(module, runid)
    keys = [key for key in run if not str(key).startswith('__') and hasattr(run[key], 'get')
            and canonical_case_key(key, run[key].get('__INFO__', {})) == identity]
    # __INFO__ carries the publication timestamp for old and new records.
    return sorted(keys, key=lambda key: (key == aliases.get(identity, None),
        str(run[key].get('__INFO__', {}).get('published_at', '') or '')))


def canonical_case_key(value, info=None):
    """Strip only the UUID suffix formerly generated by the publisher."""
    text = re.sub(r'(?:__run=[0-9a-fA-F]{8})+$', '', str(value))
    if re.fullmatch(r'nr=.+?__rho=[^_]+__ion=[^_]+', text):
        return text
    # Give old nr-only records an isotope identity when their metadata has it.
    match = re.fullmatch(r'nr=(.+?)(?:__ion=([^_]+))?', text)
    if match is not None and info is not None:
        nr, ion = match.groups()
        ion = ion or str(info.get('ion_case', info.get('mass', '')) or '')
        if ion:
            rho = info.get('rho', None)
            try:
                rho = '{:.8g}'.format(float(rho)) if math.isfinite(float(rho)) else 'unknown'
            except (TypeError, ValueError):
                rho = 'unknown'
            return 'nr={}__rho={}__ion={}'.format(nr, rho, ion)
    return text


def case_parts(value):
    text = canonical_case_key(value)
    match = re.fullmatch(r'nr=(.+?)__rho=([^_]+)__ion=([^_]+)', text)
    if match is not None:
        return match.groups()
    match = re.fullmatch(r'nr=(.+?)__ion=([^_]+)', text)
    return None if match is None else (match.group(1), 'unknown', match.group(2))


def latest_cases(module, runid):
    """Return actual readable keys and alias lookup; never delete old results.

    Former publishers inserted RUN_HISTORY and RUN_DB entries in publication
    order. Use that recorded order, never the random UUID's lexical order.
    """
    run = module.get('RUN_DB', {}).get(runid, {})
    history = module.get('RUN_HISTORY', {})
    order = {str(token): index for index, token in enumerate(history.keys())}
    current = module.get('RUN_MANIFEST', {})
    current_token = str(current.get('run_token', '')) if current.get('status', '') == 'published' else ''
    groups = OrderedDict()
    for index, key in enumerate(run.keys()):
        if str(key).startswith('__'):
            continue
        if not hasattr(run[key], 'get'):
            continue
        info = run[key].get('__INFO__', {})
        if not hasattr(info, 'get'):
            info = {}
        identity = canonical_case_key(key, info)
        groups.setdefault(identity, []).append((key, info, index))
    visible, aliases = [], {}
    for identity, candidates in groups.items():
        tokens = [str(info.get('run_token', '')) for _, info, _ in candidates]
        have_history = not getattr(history, 'sorted', False) and all(token in order for token in tokens)
        def rank(item):
            _, info, index = item
            token = str(info.get('run_token', ''))
            return (bool(current_token and token == current_token),
                    str(info.get('published_at', '') or ''), order[token] if have_history else index)
        key, _, _ = max(candidates, key=rank)
        visible.append(key)
        aliases[identity] = key
        for original, info, _ in candidates:
            aliases[str(original)] = key
            for replaced in info.get('replaced_case_keys', []):
                aliases[str(replaced)] = key
    return visible, aliases


def remap_case(value, aliases):
    return aliases.get(str(value), aliases.get(canonical_case_key(value), value))


def _remap_flags(state, key, transform):
    history = state.get('_selector_keys', {})
    if key not in history:
        return
    old_tokens = history[key]
    old_flags = state.get(key, {})
    enabled = {str(transform(token)) for index, token in enumerate(old_tokens)
               if old_flags.get(index, old_flags.get(str(index), False))}
    tokens = list(dict.fromkeys(str(transform(token)) for token in old_tokens))
    history[key] = tokens
    state[key] = {index: token in enabled for index, token in enumerate(tokens)}


def remap_case_selection(state, aliases):
    """Keep previous choices when a former revision maps to the latest case."""
    transform = lambda value: remap_case(value, aliases)
    for key in ('nr_selected', 'nr_CGYRO'):
        if key in state:
            state[key] = list(dict.fromkeys(transform(value) for value in state[key]))
    _remap_flags(state, 'nr_flag', transform)
    def radius(value):
        text = str(value)
        if text.startswith('legacy:'):
            parts = case_parts(transform(text[7:]))
            if parts is not None:
                return 'nr={}__rho={}'.format(parts[0], parts[1])
        return value
    if 'cgyro_radius_selected' in state:
        state['cgyro_radius_selected'] = list(dict.fromkeys(radius(value) for value in state['cgyro_radius_selected']))
    _remap_flags(state, 'cgyro_radius_flag', radius)
    for field in ('selected_paras_by_nr', 'para_list_flag_by_nr'):
        if field not in state:
            continue
        old, remapped = state[field], {}
        for key, values in old.items():
            target = str(transform(key))
            if target not in remapped or str(key) == target:
                remapped[target] = values
        state[field] = remapped


def remap_pair_flags(state, aliases):
    old = state.get('rho_pair_flags', None)
    if old is None:
        return
    remapped = {}
    for case, flags in old.items():
        target = str(remap_case(case, aliases))
        merged = remapped.setdefault(target, {})
        for rho, enabled in flags.items():
            merged[rho] = bool(merged.get(rho, False) or enabled)
    state['rho_pair_flags'] = remapped
