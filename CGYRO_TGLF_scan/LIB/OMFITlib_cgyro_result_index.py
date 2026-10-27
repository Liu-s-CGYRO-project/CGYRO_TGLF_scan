"""Read the existing RUN_DB indexes without consulting job ancestry.

The public __SCANS__ tables own current coordinates. Unpublished partial
results remain available in __RUNS__/cases until publication. Selections carry that immutable owner ID and the
full coordinate, not an instruction to find another job with the same p ID.
No persistent catalog, payload copy or implicit storage maintenance lives here.
"""
from builtins import (BaseException, KeyError, TypeError, ValueError, all, any, dict, float, hasattr,
                      id, int, len, list, max, set, sorted, str, tuple, zip)
from collections import OrderedDict
from copy import deepcopy
import json
import re

from OMFITlib_cgyro_archive import (RESULT_INFO_FIELDS, canonical_case_key, case_destination,
                                   case_parts, case_scans, catalog_runs, clean_run_id,
                                   grouped_case_path, identity_key, normalized_info, result_identity, scan_key)
from OMFITlib_cgyro_db import metadata_value, run_records, rollback_actions
from OMFITlib_cgyro_reference import make_reference, is_native_file
from OMFITlib_cgyro_storage import is_result, reference_id, resolve_result
from OMFITlib_cgyro_run_state import collection_recorded, point_complete, run_settled


def at(node, path):
    for key in path:
        node = metadata_value(node)[key]
    return node


def _headers(case):
    """Inspect scan headers only; even a lazy task table must stay unopened."""
    case = metadata_value(case)
    if is_native_file(case) or not hasattr(case, 'get'):
        return []
    if '__SCANS__' in case:
        return [(str(key), metadata_value(record['info']))
                for key, record in metadata_value(case['__SCANS__']).items()]
    info = metadata_value(case.get('__INFO__', {}))
    if not info:
        return []
    return [(scan_key(info, (list(info.get('parameters', [])) or [''])[0]), info)]


def _public_headers(module):
    """The selector needs scan names, never every point of every scan."""
    records = OrderedDict()
    for runid, run in module.get('RUN_DB', {}).items():
        if str(runid).startswith('__') or is_native_file(run):
            continue
        for key, case in metadata_value(run).items():
            if str(key).startswith('__') or is_native_file(case):
                continue
            radial = re.fullmatch(r'nr=(.+)_rho=([^_/]+)', str(key))
            sources = [(key, case, [runid, key])]
            if radial:
                case = metadata_value(case)
                direct = _headers(case)
                owned = {name for scan, info in direct for name in list(info.get('parameters', [])) + [scan]}
                sources = [('nr={}__rho={}__ion=BASE'.format(*radial.groups()), case, [runid, key])]
                sources += [('nr={}__rho={}__ion={}'.format(*radial.groups(), ion), child, [runid, key, ion])
                            for ion, child in case.items() if not str(ion).startswith('__') and ion not in owned]
            for caseid, source, location in sources:
                for scan, info in _headers(source):
                    selection = 'scan:' + json.dumps([runid, caseid, scan], separators=(',', ':'))
                    if selection in records:
                        raise ValueError('Ambiguous result scan index: ' + selection)
                    entry = normalized_info(info, runid, caseid)
                    entry.update(dict(selection_key=selection, destination=location, kind='scan'))
                    records[selection] = entry
    return records


def _scan_record(module, selection, header=None):
    """Direct lookup of one existing scan; no catalog walk or history join."""
    if header is None:
        try:
            runid, caseid, scan = json.loads(selection[5:])
            run = module.get('RUN_DB', {})[runid]
            locations = [[runid, caseid]] if caseid in run else []
            path = grouped_case_path(caseid, {'scan_key': scan})
            locations.append([runid] + path)
            if case_parts(caseid)[2] == 'BASE' and len(path) == 1:
                locations.append([runid] + path + ['BASE'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('The selected result scan is unavailable: ' + str(selection))
        matches = []
        for location in locations:
            try:
                source = at(module['RUN_DB'], location)
            except KeyError:
                continue
            for name, info in _headers(source):
                if name == scan:
                    matches.append((location, info))
        if len(matches) != 1:
            raise ValueError('The selected result scan is unavailable or ambiguous: ' + selection)
        location, info = matches[0]
        header = normalized_info(info, runid, caseid)
        header.update(dict(selection_key=selection, destination=location, kind='scan'))
    entry = dict(header)
    case = at(module['RUN_DB'], entry['destination'])
    scan = json.loads(selection[5:])[2]
    tasks = metadata_value(case['__SCANS__'][scan]['tasks'] if '__SCANS__' in case else case['__TASKS__'])
    entry.update(dict(tasks=tasks, result_locations={point: entry['destination'] + list(row['result_path'])
                         for point, row in tasks.items() if row.get('result_path', None)}))
    return entry


def result_records(module, include_tasks=True):
    """List headers; hydrate points only when a caller explicitly needs them."""
    records = _public_headers(module)
    if include_tasks:
        records = OrderedDict((key, _scan_record(module, key, header)) for key, header in records.items())
    for token, source in run_records(module).items():
        entry = _version_record(module, token, source, headers=records, include_tasks=include_tasks)
        if entry is not None:
            records[entry['selection_key']] = entry
    return records


def _version_record(module, token, source, headers=None, include_tasks=True):
    """Pending-task payloads are local to this job's case and scan only."""
    source = metadata_value(source)
    manifest = metadata_value(source.get('manifest', {}))
    if source.get('payload_retired', False):
        return None
    if not include_tasks:
        if 'unpublished_points' in manifest and not manifest['unpublished_points']:
            return None
        if 'unpublished_points' not in manifest:
            if manifest.get('status', '') == 'published' or manifest.get('collection_status', '') == 'complete':
                return None
            if not source.get('cases', {}) and manifest.get('collection_status', '') not in ('partial', 'empty'):
                return None
        # Old projects have no pending-point summary. Show the saved job
        # header; resolve its local point table only if the user selects it.
        # Do not rebuild missing summaries by scanning every legacy job.
        entry = normalized_info(manifest)
        entry.update(dict(selection_key='version:' + str(token), kind='version', stopped_run=True))
        return entry
    cases = metadata_value(source.get('cases', {}))
    if not cases and manifest.get('collection_status', '') not in ('partial', 'empty'):
        return None
    table = metadata_value(manifest.get('point_table', {}))
    public = set()
    try:
        caseid = canonical_case_key(manifest.get('case_id', ''), manifest)
        selection = 'scan:' + json.dumps([manifest['runid'], caseid, scan_key(manifest)], separators=(',', ':'))
        header = headers.get(selection, None) if headers is not None else None
        entry = _scan_record(module, selection, header)
    except (KeyError, TypeError, ValueError):
        entry = None
    if entry is not None:
        for row in entry['tasks'].values():
            try:
                public.add(identity_key(result_identity(entry, row)))
            except (KeyError, TypeError, ValueError):
                pass
    retired = set(source.get('retired_points', {}))
    points = {}
    for point, row in table.items():
        if point in retired:
            continue
        try:
            if not row.get('archive_pending', False) and identity_key(result_identity(manifest, row)) in public:
                continue
        except (KeyError, TypeError, ValueError):
            pass
        points[point] = row
    readable = {point: row for point, row in points.items() if point not in manifest.get('load_errors', {}) and point in cases and
                (is_result(metadata_value(cases[point])) or
                 (not is_native_file(metadata_value(cases[point])) and
                  hasattr(metadata_value(cases[point]), 'keys') and '__RESULT_REF__' in metadata_value(cases[point])))}
    if (not readable and manifest.get('collection_status', '') not in ('partial', 'empty')) or not points:
        return None
    key = 'version:' + str(token)
    entry = normalized_info(manifest)
    entry.setdefault('run_token', str(token))
    entry.update(dict(selection_key=key, kind='version',
                     stopped_run=manifest.get('collection_status', '') in ('partial', 'empty')))
    if include_tasks:
        rows = {}
        for point, source_row in readable.items():
            row = dict(metadata_value(source_row))
            row.setdefault('status', 'loaded' if point in manifest.get('loaded_points', []) else 'partial')
            row.setdefault('resume_pending', row['status'] != 'loaded')
            rows[point] = row
        entry.update(dict(tasks=rows, resume_tasks=points,
                         result_locations={point: ['__RUNS__', str(token), 'cases', point] for point in readable}))
    return entry


def find_record(module, selection):
    if str(selection).startswith('scan:'):
        return _scan_record(module, selection)
    token = str(selection).removeprefix('version:')
    source = run_records(module).get(token, None)
    if source is not None:
        entry = _version_record(module, token, source)
        if entry is not None:
            return entry
    # Legacy saved choices can carry a job token. Resolve headers once; do not
    # inspect other scans' point tables, payloads, or source-token ancestors.
    matches = [entry for entry in _public_headers(module).values() if str(entry.get('run_token', '')) == token]
    if len(matches) != 1:
        raise ValueError('The selected result version is unavailable or ambiguous. Reopen the result table.')
    return _scan_record(module, matches[0]['selection_key'], matches[0])


def select_result(module, entry, point):
    """Freeze one version using existing metadata; never open its files."""
    if point not in entry.get('tasks', {}):
        if point in entry.get('resume_tasks', {}) and entry.get('input_sha256', {}).get(point, None):
            return dict(mode='input', record_token=str(entry['run_token']),
                        row=deepcopy(dict(entry['resume_tasks'][point])),
                        info={key: deepcopy(value) for key, value in entry.items()
                              if key not in ('tasks', 'resume_tasks', 'result_locations')},
                        input_hashes=deepcopy(dict(entry['input_sha256'][point])))
        raise ValueError(str(point) + ': no retained result files in this version')
    row = deepcopy(dict(metadata_value(entry['tasks'][point])))
    location = list(entry['result_locations'][point])
    node = at(module['RUN_DB'], location)
    key = reference_id(node)
    info = {name: deepcopy(entry[name]) for name in RESULT_INFO_FIELDS if name in entry}
    info.update(dict(row.get('result_info', {})))
    binding = dict(result_id=key, identity=result_identity(info, row), row=row, info=info, location=location)
    if key is None:
        # Old native leaves are supported without hashing the whole project.
        # A dialog can only reuse the exact old object it displayed; save/reload
        # closes that lifetime, so a new dialog obtains a fresh binding.
        if not is_result(node):
            raise ValueError(str(point) + ': unsupported retained result reference')
        binding['legacy_object_id'] = id(node)
    return binding


def selected_result(module, binding):
    """Resolve exactly the selected owner, independent of all job records."""
    if binding.get('error', None):
        raise ValueError(binding['error'])
    if identity_key(result_identity(binding['info'], binding['row'])) != identity_key(binding['identity']):
        raise ValueError('Selected result coordinate changed')
    if binding.get('result_id', None):
        try:
            current = at(module['RUN_DB'], binding['location'])
        except KeyError:
            # Publication can move an unpublished alias into the public tree.
            # Only the same owner at the same coordinate can preserve a choice.
            matches = []
            identity = binding['identity']
            selection = 'scan:' + json.dumps([identity['runid'], identity['case_id'], identity['scan']], separators=(',', ':'))
            try:
                entries = [_scan_record(module, selection)]
            except ValueError:
                entries = []
            for entry in entries:
                for point, row in entry['tasks'].items():
                    try:
                        if identity_key(result_identity(entry, row)) == identity_key(binding['identity']):
                            matches.append(select_result(module, entry, point))
                    except (KeyError, TypeError, ValueError):
                        continue
            if not any(item.get('result_id', None) == binding['result_id'] for item in matches):
                raise ValueError('Selected result was replaced; reopen the result table')
        else:
            if reference_id(current) != binding['result_id']:
                raise ValueError('Selected result was replaced; reopen the result table')
        return resolve_result(module, make_reference(binding['result_id'], browse=False))
    node = at(module.get('RUN_DB', {}), binding['location'])
    if id(node) != binding.get('legacy_object_id', None) or not is_result(node):
        raise ValueError('The unindexed result changed; reopen its point table')
    return node


def scan_scope(entry):
    """Freeze known coordinates, separately recording unknown legacy coverage."""
    if entry.get('planned_coordinates', None) is not None:
        return deepcopy(dict(entry['planned_coordinates']))
    identities, issues = [], []
    for point, row in entry.get('resume_tasks', entry.get('tasks', {})).items():
        try:
            identities.append(result_identity(entry, row))
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(str(point) + ': ' + str(exc))
    known = set(entry.get('resume_tasks', entry.get('tasks', {})))
    planned = set(entry.get('planned_points', entry.get('continuation', {}).get('source_points', known)))
    return dict(coordinates=identities, unknown=sorted(planned - known), issues=issues)


def merge_scopes(*scopes):
    """Coverage is a union of coordinate metadata, never ancestor point IDs."""
    coordinates, unknown, issues = {}, set(), set()
    for scope in scopes:
        for item in scope.get('coordinates', []):
            coordinates[identity_key(item)] = item
        unknown.update(scope.get('unknown', []))
        issues.update(scope.get('issues', []))
    return dict(coordinates=list(coordinates.values()), unknown=sorted(unknown), issues=sorted(issues))


def release_published_results(module, case, verified_cases=()):
    """Remove obsolete job payload aliases by coordinates, never ancestry.

    This is publication/explicit-maintenance work, not an index-query side
    effect. Job manifests remain for scheduler operations and provenance.
    Uncovered or unidentified old points remain untouched. The caller prunes
    the returned owner IDs only after the public merge has committed.
    """
    public, candidates, verified = {}, set(), {}
    for previous_case in verified_cases:
        for _, info, tasks in case_scans(previous_case):
            for row in tasks.values():
                if row.get('input_parameters', None) is None:
                    continue
                identity = result_identity(info, row)
                owner = reference_id(at(previous_case, row['result_path']))
                verified[(owner, identity['runid'], identity['case_id'], identity['scan'])] = identity_key(identity)
    for _, info, tasks in case_scans(case):
        for row in tasks.values():
            try:
                coordinate = identity_key(result_identity(info, row))
            except (KeyError, TypeError, ValueError):
                continue
            node = at(case, row['result_path'])
            public[coordinate] = (reference_id(node), str(row.get('run_token', info.get('run_token', ''))))
    edits = []
    affected_cases = {(identity['runid'], identity['case_id'])
                      for coordinate in public for identity in [json.loads(coordinate)]}
    for token, record in run_records(module).items():
        manifest = metadata_value(record.get('manifest', {}))
        if not collection_recorded(manifest) or not run_settled(manifest):
            continue  # Live/requeued jobs still own their exact input/retry state.
        if (clean_run_id(manifest.get('runid', '')), canonical_case_key(manifest.get('case_id', ''), manifest)) not in affected_cases:
            continue  # No point-table traversal for other radii/ions/runs.
        cases = metadata_value(record.get('cases', {}))
        retired = dict(metadata_value(record.get('retired_points', {})))
        remove = set()
        for point, node in cases.items():
            row = manifest.get('point_table', {}).get(point, None)
            if row is None or row.get('archive_pending', False):
                continue
            try:
                identity = result_identity(manifest, row)
                coordinate = identity_key(identity)
            except (KeyError, TypeError, ValueError):
                continue
            previous = reference_id(node)
            if row.get('input_parameters', None) is None:
                coordinate = verified.get((previous, identity['runid'], identity['case_id'], identity['scan']), coordinate)
            if coordinate not in public:
                continue
            winner, owner = public[coordinate]
            # The active collector may still need its same-owner alias until
            # save_current finishes. It cannot expose a second result version.
            if str(token) == owner and previous == winner:
                continue
            remove.add(point)
            if previous:
                candidates.add(previous)
            retired[point] = dict(result=winner, run_token=owner, reason='coordinate_published')
        if remove:
            updates = dict(cases={point: node for point, node in cases.items() if point not in remove},
                           retired_points=retired)
            if 'inputs' in record:
                updates['inputs'] = {key: node for key, node in metadata_value(record['inputs']).items() if key not in remove}
            edits.append((record, {key: record[key] for key in updates if key in record}, updates))
    try:
        for record, _, updates in edits:
            for key, value in updates.items():
                record[key] = value
    except BaseException as error:
        actions = []
        for record, old, updates in edits:
            for key in updates:
                actions.append((key, (lambda record=record, key=key: record.pop(key, None)) if key not in old else
                                (lambda record=record, key=key, value=old[key]: record.__setitem__(key, value))))
        rollback_actions(error, actions)
        raise
    return candidates


def scan_completion(info, tasks, scope):
    """Bad legacy metadata makes coverage unknown, not a valid archive fail."""
    coverage, issues = [], list(scope.get('issues', []))
    for point, row in tasks.items():
        try:
            if point_complete(row, legacy_default=True):
                coverage.append(result_identity(info, row))
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(str(point) + ': ' + str(exc))
    # A planned point predates input.cgyro.gen and has no expanded defaults.
    # Every known coordinate must match; extra solver defaults only strengthen
    # the collected identity. No absent planned point is manufactured here.
    return (not scope.get('unknown', []) and not issues and
            all(any(all(actual.get(key, None) == value for key, value in coordinate.items() if key != 'values')
                    and all(actual['values'].get(name, None) == value for name, value in coordinate['values'].items())
                    for actual in coverage) for coordinate in scope['coordinates']))
