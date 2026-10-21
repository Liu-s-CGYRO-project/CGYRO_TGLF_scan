"""Recognize old scan indexes without reading or copying solver payloads.

Preview builds ordinary Python blueprints. Existing OMFIT objects are attached
only when the live transaction commits; rollback restores their tree owners.
Names and archived metadata are evidence. Current GUI settings are never used
to guess the radius, isotope, time or remote directory of an old calculation.
"""
from builtins import (KeyError, TypeError, ValueError, all, any, bool, dict, enumerate, float, getattr,
                      id, isinstance, len, list, object, range, repr, set, sorted, str, tuple, type, vars, zip)
import ast
import hashlib
import math
from pathlib import Path
import re

GROUP = 'CGYRO_TGLF_scan'
LEGACY = ('CGYRO_scan', 'TGLF_scan', 'Transfer_tool')


def kind(value, name):
    return any(base.__name__ == name for base in type(value).__mro__)


def branch(value):
    return isinstance(value, dict) and not kind(value, 'OMFITobject')


def rebind(value):
    """Restore native parent links after moving a metadata tree or undoing it."""
    if branch(value):
        for key in list(dict.keys(value)):
            child = dict.__getitem__(value, key)
            value[key] = child
            rebind(child)
    return value


def structure(value):
    """Track metadata edits for undo, stopping at arrays and solver objects."""
    if branch(value):
        return (id(value), tuple((key, structure(dict.__getitem__(value, key))) for key in dict.keys(value)))
    if isinstance(value, (tuple, list)):
        return (id(value), tuple(structure(child) for child in value))
    if kind(value, 'OMFITexpression'):
        return (id(value), value.expression)
    return (id(value),)


class Reference:
    def __init__(self, value):
        self.value = value


class Layout:
    def __init__(self, value):
        self.value = value

    def check(self, path=()):
        """Check new tree keys without constructing or reparenting payloads."""
        def visit(value, here):
            if isinstance(value, Reference):
                return  # The retained object keeps its existing internal keys.
            if isinstance(value, dict):
                for key, child in value.items():
                    target = child.value if isinstance(child, Reference) else child
                    tree = kind(target, 'OMFITtree') or isinstance(child, dict)
                    # Match native OMFITtree.__setitem__: a slash is forbidden
                    # when the child is another tree, not in ordinary strings
                    # such as result directories stored as metadata values.
                    if kind(key, 'OMFITexpression') or (tree and isinstance(key, (str, tuple)) and '/' in key):
                        raise ValueError('旧归档含不兼容的树键：' + repr(here + (key,)))
                    visit(child, here + (key,))
            elif isinstance(value, (tuple, list)):
                for number, child in enumerate(value):
                    visit(child, here + (number,))
        visit(self.value, tuple(path))

    def build(self, factory):
        def convert(value):
            if isinstance(value, Reference):
                return rebind(value.value)
            if isinstance(value, dict):
                node = factory()
                for key, child in value.items():
                    node[key] = convert(child)
                return node
            if isinstance(value, (tuple, list)):
                return [convert(child) for child in value]
            return value
        return convert(self.value)


def relocated_expression(value, mapping):
    """Change explicit absolute module references without evaluating them."""
    if not kind(value, 'OMFITexpression'):
        return value
    code = value.expression
    lines, offsets, current = code.encode('utf-8').splitlines(keepends=True), [], 0
    for line in lines:
        offsets.append(current)
        current += len(line)
    changes = []
    for node in ast.walk(ast.parse(code)):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == 'OMFIT' and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
                and node.slice.value in mapping):
            text = 'OMFIT' + ''.join('[' + repr(key) + ']' for key in mapping[node.slice.value])
            changes.append((offsets[node.lineno - 1] + node.col_offset,
                            offsets[node.end_lineno - 1] + node.end_col_offset, text.encode('utf-8')))
    if not changes:
        return value
    content = code.encode('utf-8')
    for start, end, text in sorted(changes, reverse=True):
        content = content[:start] + text + content[end:]
    # Native __init__/deepcopy evaluate expressions. A preview must do neither.
    result = object.__new__(type(value))
    result.expression = content.decode('utf-8')
    result.lastEval = object.__getattribute__(value, 'lastEval')
    return result


class ArchiveIndex:
    """Plan lossless reclassification of known CGYRO and TGLF layouts."""
    def __init__(self):
        self.guards, self.sources, self.issues = [], [], []
        self.input_guards = {}
        self.cgyro_pool = {}

    def materialize(self, value):
        """Read a native metadata pickle, never a solver output reader.

        Native reloads can wrap ordinary metadata dictionaries and strings.
        Record that exact loader replacement in earlier guards; all unrelated
        edits still invalidate the preview. Without this, valid scan indexes
        can be misclassified merely because their metadata was unopened.
        """
        if (kind(value, 'OMFITlazyLoad') and vars(value).get('tp', '') in
                ('OMFITpickle', 'OMFITtree', 'OMFITmodule', 'SortedDict', 'OMFITlist')):
            loaded = value.__lazy_load__()
            for index, (parent, expected) in enumerate(self.guards):
                adjusted = []
                for key, identity in expected:
                    if identity == id(value):
                        if dict.__getitem__(parent, key) is not loaded:
                            raise ValueError('Archived metadata changed during native loading')
                        identity = id(loaded)
                    adjusted.append((key, identity))
                self.guards[index] = (parent, tuple(adjusted))
            return loaded
        return value

    @staticmethod
    def cgyro_object(value):
        return kind(value, 'OMFITcgyro') or (kind(value, 'OMFITlazyLoad') and
            vars(value).get('tp', vars(value).get('cls', '')) == 'OMFITcgyro')

    def cgyro_payload(self, value):
        """Recognize indexed output without materializing it in a second tree.

        The updater runs before new application libraries are installed, so
        this small format check is independent of the project's import hook.
        """
        value = self.materialize(value)
        if self.cgyro_object(value):
            return True
        if not branch(value):
            return False
        contents = self.read(value)
        if '__RESULT_REF__' not in contents:
            return False
        key = self.materialize(contents['__RESULT_REF__'])
        if len(contents) != 1 or not isinstance(key, str) or re.fullmatch(r'[0-9a-f]{64}', key) is None:
            raise ValueError('Invalid CGYRO result reference')
        if not self.cgyro_object(self.get(self.cgyro_pool, key, None)):
            raise ValueError('Missing CGYRO result owner: ' + key)
        return True

    def read(self, node):
        node = self.materialize(node)
        if not branch(node):
            raise ValueError('Expected a metadata tree')
        if getattr(node, '__dict__', {}).get('dynaLoad', False):
            node.keys()  # Load only tree scaffolding, never an OMFIT result file.
        names = list(dict.keys(node))
        self.guards.append((node, tuple((key, id(dict.__getitem__(node, key))) for key in names)))
        return {key: dict.__getitem__(node, key) for key in names}

    def get(self, node, key, default=None):
        node = self.materialize(node)
        return self.read(node).get(key, default) if branch(node) else default

    def metadata(self, value):
        value = self.materialize(value)
        if kind(value, 'OMFITexpression'):
            raise ValueError('Archived identity contains a dynamic expression')
        if branch(value):
            return {key: self.metadata(child) for key, child in self.read(value).items()}
        if isinstance(value, (list, tuple)):
            return [self.metadata(child) for child in value]
        return value

    def check(self):
        for node, expected in self.guards:
            actual = tuple((key, id(dict.__getitem__(node, key))) for key in dict.keys(node))
            if actual != expected:
                raise ValueError('旧扫描索引在预览后已改变，请重新预览')
        for name, expected in self.input_guards.items():
            path = Path(name)
            data = path.read_bytes() if path.is_file() and path.stat().st_size <= 262144 else None
            if (hashlib.sha256(data).hexdigest() if data is not None else None) != expected:
                raise ValueError('归类使用的原始 input.cgyro 已改变，请重新预览：' + name)

    def issue(self, path, error, retained=None):
        row = dict(path=[str(part) for part in path], reason=str(error))
        if retained is not None:
            row['target'] = ['LEGACY_UNCLASSIFIED', retained]
        self.issues.append(row)

    @staticmethod
    def retain(pending, label, value):
        # Labels describe paths; native OMFITtree keys cannot contain '/'.
        # Escape '%' first so the spelling remains reversible. Existing keys
        # are reserved below, including literal percent-encoded old names.
        label = str(label).replace('%', '%25').replace('/', '%2F')
        key, number = label, 1
        while key in pending:
            number += 1
            key = label + ' [' + str(number) + ']'
        pending[key] = Reference(value)
        return key

    @staticmethod
    def number(value):
        if kind(value, 'OMFITexpression'):
            raise ValueError('Dynamic coordinate')
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Non-finite coordinate')
        return result

    def points(self, name, data):
        """Inspect parameter/value/lin/ky metadata, stopping before result files."""
        points, order, values = [], None, {}
        def visit(parameter, node, axes, coordinates, path):
            nonlocal order
            if not re.fullmatch(r'[A-Z][A-Z0-9_]*(?:\+[A-Z][A-Z0-9_]*)*', parameter) or len(axes) >= 3:
                raise ValueError('Unsupported parameter axis: ' + str(parameter))
            axes = axes + [parameter]
            for key, child in self.read(node).items():
                self.number(key)
                values.setdefault(parameter, []).append(key)
                coordinate, here = coordinates + [key], path + [key]
                contents = self.read(child)
                if 'lin' in contents:
                    if set(contents) != {'lin'}:
                        raise ValueError('Mixed linear/nonlinear branch')
                    if order is not None and order != axes:
                        raise ValueError('Mixed scan axes')
                    order = axes
                    for ky, payload in self.read(contents['lin']).items():
                        self.number(ky)
                        if not self.cgyro_payload(payload):
                            raise ValueError('Unrecognized CGYRO payload')
                        points.append((here + ['lin', ky], coordinate, ky))
                elif len(contents) == 1:
                    inner, nested = list(contents.items())[0]
                    visit(str(inner), nested, axes, coordinate, here + [inner])
                else:
                    raise ValueError('Ambiguous nested scan')
        declared = str(name).split('__')
        visit(declared[0], data, [], [], [name])
        if not points:
            raise ValueError('Empty scan')
        if len(set(order)) != len(order) or len(declared) > 1 and order != declared:
            raise ValueError('Composite scan name conflicts with its stored axes')
        return order, values, points

    def identity(self, name, info, ion=''):
        text = re.sub(r'(?:__run=[0-9a-fA-F]{8})+$', '', str(name))
        match = re.fullmatch(r'nr=(.+?)(?:__rho=([^_]+))?(?:__ion=([^_]+))?', text)
        if match is None:
            raise ValueError('Missing archived radial identity: ' + str(name))
        nr, rho, named_ion = match.groups()
        if nr in ('', 'unknown'):
            raise ValueError('Missing archived radial index')
        saved_nr = info.get('source_nr', info.get('nr', nr))
        if str(saved_nr) != nr:
            raise ValueError('Conflicting archived radial index')
        saved_ion = str(info.get('ion_case', None) or info.get('mass', None) or named_ion or ion)
        if named_ion and saved_ion != named_ion or ion and saved_ion != ion:
            raise ValueError('Conflicting isotope labels')
        if not saved_ion:
            raise ValueError('Missing archived isotope (current settings are not evidence)')
        archived_rho = info.get('rho', None)
        if rho not in (None, 'unknown') and archived_rho is not None:
            if not math.isclose(self.number(rho), self.number(archived_rho), rel_tol=1e-8, abs_tol=1e-10):
                raise ValueError('Conflicting archived rho')
        rho = archived_rho if archived_rho is not None else rho
        rho = 'unknown' if rho in (None, 'unknown') else '{:.8g}'.format(self.number(rho))
        identity = 'nr={}__rho={}__ion={}'.format(nr, rho, saved_ion)
        if '/' in identity:
            raise ValueError('Archived case identity contains a slash')
        return identity, nr, rho, saved_ion

    def output_case(self, module, output):
        """Bind a latest-output cache only when the saved point paths prove it."""
        contents = self.read(output)
        info = self.metadata(contents.get('__INFO__', {}))
        if not info:
            manifest = self.metadata(self.get(module, 'RUN_MANIFEST', {}))
            table = manifest.get('point_table', {})
            if manifest.get('status', '') in ('loaded', 'published'):
                if not table:
                    for point in manifest.get('loaded_points', []):
                        parts = str(point).split('~')
                        if len(parts) in (4, 6, 8) and parts[-2].lower() == 'ky':
                            table[point] = dict(result_path=parts[:-2] + ['lin', parts[-1]], point_dir=point)
                paths = {tuple(row.get('result_path', [])) for row in table.values()}
                leaves = set()
                def visit(node, path):
                    if self.cgyro_payload(node):
                        leaves.add(tuple(path))
                    elif branch(node) and len(path) < 9:
                        for key, child in self.read(node).items():
                            if not str(key).startswith('__'):
                                visit(child, path + [key])
                    else:
                        raise ValueError('Unrecognized latest-output cache')
                try:
                    visit(output, [])
                except ValueError:
                    leaves = set()
                if table and len(paths) == len(table) and paths == leaves:
                    info = dict(manifest)
                    info.update(dict(ion_case=manifest.get('mass', ''), source_nr=manifest.get('nr', 'unknown')))
                    contents['__TASKS__'] = table
        contents['__INFO__'] = info
        case = info.get('case_id', 'nr=' + str(info.get('source_nr', info.get('nr', 'unknown'))))
        return {info.get('runid', 'Legacy OUTPUTScan'): {case: contents}}

    def input_identity(self, payload):
        """Read frozen scalar input text, never the current input or output arrays."""
        if not self.cgyro_object(payload):
            if not self.cgyro_payload(payload):
                raise ValueError('Unrecognized CGYRO result')
            payload = self.get(self.cgyro_pool, self.get(payload, '__RESULT_REF__', ''), None)
        path = Path(payload.filename) / 'input.cgyro'
        if not path.is_file() or path.stat().st_size > 262144:
            self.input_guards[str(path)] = None
            raise ValueError('原结果目录中没有可读取的 input.cgyro')
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        self.input_guards[str(path)] = digest
        values = {}
        for line in content.decode('utf-8-sig').splitlines():
            line = re.split(r'[#!]', line, maxsplit=1)[0].strip()
            match = re.fullmatch(r'([A-Z][A-Z0-9_]*)\s*=\s*([+\-0-9.eEdD]+)', line)
            if match:
                key, text = match.groups()
                number = self.number(text.replace('D', 'e').replace('d', 'e'))
                if key in values and values[key] != number:
                    raise ValueError('原始输入含重复且不一致的参数：' + key)
                values[key] = number
        return values, dict(path=str(path), sha256=digest)

    def bare_output(self, module, output, header):
        """Recover a bare OUTPUTScan, including files with no run metadata.

        Missing rho is not replaced by RMIN. RMIN has its own visible radial
        identifier; fully unidentified points remain plottable in a separate
        labelled source group, without invented job/restart provenance.
        """
        runs, pending = {}, {}
        self.cgyro_pool = self.get(module, 'RESULT_STORE', {})
        previous = self.get(module, 'LEGACY_UNCLASSIFIED', {})
        if branch(previous):
            pending.update({key: Reference(value) for key, value in self.read(previous).items()})
        elif previous is not None:
            self.retain(pending, 'Previous unclassified archive', previous)
        old_run_db = self.get(module, 'RUN_DB', None)
        if branch(old_run_db) and self.read(old_run_db):
            self.retain(pending, 'Prior empty RUN_DB structure', old_run_db)
        single = self.cgyro_payload(output)
        if single:
            try:
                scalar, _ = self.input_identity(output)
                branches = {'lin': {repr(scalar['KY']): output}}
            except (AttributeError, KeyError, OSError, UnicodeError, TypeError, ValueError) as exc:
                self.retain(pending, 'OUTPUTScan', output)
                self.issue(['OUTPUTScan'], '单结果没有可核对的 KY，保留原节点：' + str(exc))
                return dict(RUN_DB=Layout({}), OUTPUTScan=Layout({}), LEGACY_UNCLASSIFIED=Layout(pending))
        else:
            branches = self.read(output)
        direct_ky = bool(branches) and all(self.cgyro_payload(value) for value in branches.values())
        if direct_ky:
            try:
                for ky in branches:
                    self.number(ky)
            except (TypeError, ValueError):
                direct_ky = False
            if direct_ky:
                branches = {'lin': output}
        for index, (source, data) in enumerate(branches.items(), 1):
            if str(source).startswith('__'):
                # Keep an original header once, not in each reconstructed case.
                self.retain(pending, 'OUTPUTScan metadata ' + str(source), data)
                continue
            try:
                match = re.fullmatch(r'([A-Z][A-Z0-9_]*?)(?:_([HDT]))?(?:__previous_[0-9a-fA-F]+)?', str(source))
                if str(source) == 'lin':
                    parameter, named_ion = 'KY_ONLY', ''
                    axes, points = ['REFERENCE'], []
                    for ky, payload in self.read(data).items():
                        self.number(ky)
                        if not self.cgyro_payload(payload):
                            raise ValueError('Unrecognized ky-only CGYRO result')
                        points.append((['KY_ONLY', '0.00000', 'lin', ky], [0], ky))
                    key, ky_only = 'KY_ONLY', True
                else:
                    if match is None:
                        raise ValueError('无法识别 OUTPUTScan 参数分支')
                    parameter, named_ion = match.groups()
                    axes, _, points = self.points(parameter, data)
                    key, ky_only = '__'.join(axes), False
                if not points:
                    raise ValueError('Empty latest-output branch')
                grouped = {}
                for number, (path, coordinates, ky) in enumerate(points, 1):
                    payload = data
                    tail = path[3:] if ky_only else path[1:]
                    for part in tail:
                        payload = self.read(payload)[part]
                    evidence, scalar, input_issue = None, {}, ''
                    try:
                        scalar, evidence = self.input_identity(payload)
                    except (AttributeError, OSError, UnicodeError, TypeError, ValueError) as exc:
                        scalar, input_issue = {}, str(exc)
                    if 'KY' in scalar and not math.isclose(scalar['KY'], self.number(ky), rel_tol=1e-7, abs_tol=1e-10):
                        raise ValueError('原 input.cgyro 的 KY 与结果树坐标不一致，保留原分支待核对')
                    for axis, coordinate in zip(axes, coordinates):
                        if axis in scalar and not math.isclose(scalar[axis], self.number(coordinate), rel_tol=1e-7, abs_tol=1e-10):
                            raise ValueError('原输入与扫描坐标不一致，保留原分支待核对：' + axis)
                    masses = {value for name, value in scalar.items() if name.startswith('MASS_')
                              and scalar.get('Z_' + name[5:], 0) == 1 and scalar.get('DENS_' + name[5:], 1) > 0}
                    pure = {0.5: 'H', 1.0: 'D', 1.5: 'T'}.get(list(masses)[0], '') if len(masses) == 1 else ''
                    composition_scan = any(axis.startswith(('MASS_', 'Z_', 'DENS_')) for axis in axes)
                    ion = named_ion or ('' if composition_scan else pure) or ('BASE' if masses else 'UNKNOWN')
                    if named_ion and pure and pure != named_ion and not composition_scan:
                        raise ValueError('原始输入质量与参数后缀的离子不一致，保留原分支待核对')
                    info = dict(header) if len([name for name in branches if not str(name).startswith('__')]) == 1 else {}
                    try:
                        identity, nr, rho, saved_ion = self.identity(info.get('case_id', 'nr=' + str(info.get('source_nr', info.get('nr', 'unknown')))), info, ion if ion != 'UNKNOWN' else '')
                        ion = saved_ion
                        radial_source = 'archived_header'
                    except (TypeError, ValueError):
                        rho = 'unknown'
                        if 'RMIN' in scalar and 'RMIN' not in axes:
                            nr, radial_source = 'RMIN=' + repr(scalar['RMIN']), 'saved_input_RMIN'
                        else:
                            nr, radial_source = 'legacy-output-' + str(index), 'unidentified'
                        identity = 'nr={}__rho={}__ion={}'.format(nr, rho, ion)
                    group = grouped.setdefault(identity, dict(info=dict(case_id=identity, source_nr=nr,
                        rho=None if rho == 'unknown' else self.number(rho), ion_case=ion,
                        radial_source=radial_source, status='legacy_imported', dimensions=len(axes),
                        scan_dimensions=0 if ky_only else len(axes), scan_axes=[dict(name=axis, values=[],
                            linked=[], fixed=ky_only) for axis in axes]), tasks={}, payload={}))
                    target = list(path)
                    target[0] = key
                    node = group['payload']
                    for part in target[1:-1]:
                        node = node.setdefault(part, {})
                    node[target[-1]] = Reference(payload)
                    original_path = ['OUTPUTScan'] if single else ['OUTPUTScan'] + tail if direct_ky else ['OUTPUTScan', source] + tail
                    row = dict(result_path=target, original_result_path=original_path,
                        values=dict(zip(axes, coordinates)), ky=self.number(ky), status='loaded',
                        case_id=identity, source_nr=nr, rho=group['info']['rho'], ion_case=ion)
                    if evidence is not None:
                        row['archived_input'] = evidence
                    if input_issue:
                        row['identity_note'] = input_issue
                    group['tasks']['legacy{:06d}'.format(number)] = row
                    for axis, coordinate in zip(group['info']['scan_axes'], coordinates):
                        if coordinate not in axis['values']:
                            axis['values'].append(coordinate)
                for identity, group in grouped.items():
                    info = group['info']
                    info['points'] = len(group['tasks'])
                    self.install(runs, 'Legacy OUTPUTScan', identity, key, Layout(group['payload']), info,
                                 group['tasks'], ['OUTPUTScan', source])
                    if info['radial_source'] == 'unidentified' or info['ion_case'] == 'UNKNOWN':
                        self.issue(['OUTPUTScan', source], '已归为未标识旧结果；不使用当前设置补历史身份')
            except (KeyError, TypeError, ValueError) as exc:
                retained = self.retain(pending, 'OUTPUTScan / ' + str(source), data)
                self.issue(['OUTPUTScan', source], exc, retained)
        return dict(RUN_DB=Layout(runs), OUTPUTScan=Layout({}), LEGACY_UNCLASSIFIED=Layout(pending))

    def cgyro(self, module):
        start = len(self.sources)
        original = self.get(module, 'RUN_DB', None)
        self.cgyro_pool = self.get(original, '__STORE__', self.get(module, 'RESULT_STORE', {}))
        if self.get(self.get(original, '__STORAGE__', {}), 'version', 0) >= 4:
            return None  # Current application owns RUN_DB; preserve its exact layout.
        output = self.get(module, 'OUTPUTScan', None)
        has_records = original is not None and (not branch(original) or
            any(not branch(run) or bool(self.read(run)) for run in self.read(original).values()))
        from_output = not has_records and (self.cgyro_payload(output) or branch(output) and bool(self.read(output)))
        if from_output:
            if self.cgyro_payload(output):
                return self.bare_output(module, output, {})
            original = self.output_case(module, output)
            case = list(list(original.values())[0].values())[0]
            if '__TASKS__' not in case:
                return self.bare_output(module, output, case['__INFO__'])
        if not branch(original):
            if original is not None:
                self.issue(['RUN_DB'], '归档不是可识别的元数据树，保留原节点')
            return None
        runs, changed = {}, bool(from_output)
        pending = {key: Reference(value) for key, value in self.read(self.get(module, 'LEGACY_UNCLASSIFIED', {})).items()}
        for runid, run in self.read(original).items():
            if str(runid).startswith('__'):
                runs[runid] = Reference(run)
                continue
            if isinstance(runid, str) and '/' in runid:
                retained = self.retain(pending, 'RUN_DB / ' + runid, run)
                self.issue(['RUN_DB', runid], '结果集名称包含斜杠，保留原节点待核对', retained)
                changed = True
                continue
            target = runs.setdefault(runid, {})
            if not branch(run):
                self.retain(pending, str(runid), run)
                self.issue(['RUN_DB', runid], '无法识别的结果集，保留原节点')
                changed = True
                continue
            for caseid, case in self.read(run).items():
                if str(caseid).startswith('__'):
                    target[caseid] = Reference(case)
                    continue
                try:
                    contents = self.read(case)
                    if not contents:
                        target[caseid] = Reference(case)
                        continue
                    unexpected = {key for key in contents if str(key).startswith('__')} - {'__SCANS__', '__INFO__', '__TASKS__'}
                    if unexpected:
                        raise ValueError('Unrecognized case metadata: ' + str(sorted(unexpected)))
                    index = contents.get('__SCANS__', None)
                    records, candidates = [], []
                    if index is not None:
                        for scanid, record in self.read(index).items():
                            if set(self.read(record)) != {'info', 'tasks'}:
                                raise ValueError('Unrecognized per-scan metadata')
                            records.append((scanid, self.metadata(self.get(record, 'info', {})),
                                            self.metadata(self.get(record, 'tasks', {}))))
                    elif '__INFO__' in contents and '__TASKS__' in contents:
                        info = self.metadata(contents['__INFO__'])
                        records.append(('', info, self.metadata(contents['__TASKS__'])))
                    owned = set()
                    if records:
                        for scanid, info, tasks in records:
                            roots = {row['result_path'][0] for row in tasks.values() if row.get('result_path', [])}
                            if len(roots) != 1:
                                raise ValueError('Missing or ambiguous archived point paths')
                            root = list(roots)[0]
                            source = root if root in contents else root + '_' + str(info.get('ion_case', ''))
                            if source not in contents:
                                raise ValueError('Missing archived result branch: ' + str(root))
                            if source in owned:
                                raise ValueError('Two scan indexes claim the same result branch')
                            for row in tasks.values():
                                node = contents[source]
                                for part in row['result_path'][1:]:
                                    node = self.read(node)[part]
                                if not self.cgyro_payload(node):
                                    raise ValueError('Archived task does not point to a CGYRO result')
                            axes = info.get('scan_axes', [])
                            key = ('KY_ONLY' if info.get('scan_dimensions', None) == 0 else
                                   '__'.join(axis['name'] + ''.join('+' + item['name'] for item in axis.get('linked', []))
                                             for axis in axes) if axes else str(scanid or root))
                            if not key or key.startswith('__') or '/' in key:
                                raise ValueError('Invalid archived scan identity')
                            identity, nr, rho, ion = self.identity(caseid, info)
                            candidates.append((runid, identity, key, contents[source], info, tasks,
                                               ['OUTPUTScan', source] if from_output else ['RUN_DB', runid, caseid, source]))
                            owned.add(source)
                            changed = changed or identity != caseid or '__SCANS__' not in contents
                    for source, payload in contents.items():
                        if str(source).startswith('__') or source in owned:
                            continue
                        match = re.fullmatch(r'([A-Z][A-Z0-9_]*?)(?:_([HDT]))?(?:__previous_[0-9a-fA-F]+)?', str(source))
                        if match is None:
                            raise ValueError('Unrecognized legacy parameter branch: ' + str(source))
                        parameter, ion = match.groups()
                        identity_info = self.metadata(contents.get('__INFO__', {})) if not records else {}
                        identity, nr, rho, ion = self.identity(caseid, identity_info, ion or '')
                        # A case-level header is not provenance for an unindexed
                        # old branch, especially a __previous_... revision.
                        info = {}
                        axes, values, points = self.points(parameter, payload)
                        key = '__'.join(axes)
                        tasks = {}
                        for number, (path, coordinates, ky) in enumerate(points, 1):
                            path[0] = key
                            tasks['legacy{:06d}'.format(number)] = dict(result_path=path, ky=self.number(ky),
                                axis_values=dict(zip(axes, coordinates)), case_id=identity, ion_case=ion,
                                source_nr=nr, rho=None if rho == 'unknown' else self.number(rho), status='loaded')
                        info.update(dict(case_id=identity, source_nr=nr, rho=None if rho == 'unknown' else self.number(rho),
                            ion_case=ion, dimensions=len(axes), scan_dimensions=len(axes), points=len(tasks),
                            scan_axes=[dict(name=axis, values=list(dict.fromkeys(values[axis])), linked=[])
                                       for axis in axes], status='legacy_imported'))
                        candidates.append((runid, identity, key, payload, info, tasks,
                                           ['OUTPUTScan', source] if from_output else ['RUN_DB', runid, caseid, source]))
                        changed = True
                    # Do not index a subset and also retain the complete source
                    # case: a native result object must have only one tree owner.
                    for candidate in candidates:
                        self.install(runs, *candidate)
                except (TypeError, ValueError, KeyError) as exc:
                    # Keep the complete source case when any part is uncertain.
                    retained = self.retain(pending, str(runid) + ' / ' + str(caseid), output if from_output else case)
                    self.issue(['OUTPUTScan'] if from_output else ['RUN_DB', runid, caseid], exc, retained)
                    changed = True
        if not changed:
            del self.sources[start:]
            return None
        replacements = dict(RUN_DB=Layout(runs), LEGACY_UNCLASSIFIED=Layout(pending))
        if from_output:
            replacements['OUTPUTScan'] = Layout({})
        return replacements

    def install(self, runs, runid, identity, key, payload, info, tasks, source):
        run, revision = runid, 1
        while key in runs.setdefault(run, {}).setdefault(identity, {}).get('__SCANS__', {}):
            revision += 1
            run = str(runid) + ' [legacy revision ' + str(revision) + ']'
        case = runs[run][identity]
        info.update(dict(case_id=identity, runid=run, scan_key=key, parameters=[key], migration_source=list(source)))
        for row in tasks.values():
            row.update(dict(case_id=identity, runid=run))
            row['result_path'][0] = key
        case[key] = payload.value if isinstance(payload, Layout) else Reference(payload)
        # Metadata can legitimately use file paths as dictionary keys. Keep
        # these freshly copied mappings as plain dicts, as the runner does,
        # rather than converting every nested mapping into an OMFITtree.
        case.setdefault('__SCANS__', {})[key] = dict(info=Reference(info), tasks=Reference(tasks))
        case['__INFO__'], case['__TASKS__'] = Reference(info), Reference(tasks)
        self.sources.append(dict(source=[str(part) for part in source],
            target=[str(part) for part in ['RUN_DB', run, identity, key]], points=len(tasks)))

    def tglf(self, module):
        """Index old 1D/2D radial scans as explicit records, preserving payloads."""
        current = self.get(module, 'RUN_DB', {})
        runs = {key: Reference(value) for key, value in self.read(current).items()}
        replacements, grouped = {}, {}
        for depth, name in ((1, 'scanResults'), (2, 'scanResults2D')):
            for suffix in ('', '_spectra'):
                field = name + suffix
                original = self.get(module, field, None)
                if not branch(original) or not self.read(original):
                    continue
                remaining = {}
                source_count = len(self.sources)
                for radius, cases in self.read(original).items():
                    if not branch(cases):
                        remaining[radius] = Reference(cases)
                        self.issue([field, radius], '无法识别的 TGLF 半径分支，保留原节点')
                        continue
                    for parameter, data in self.read(cases).items():
                        path = [field, radius, parameter]
                        try:
                            axes = str(parameter).split('+')
                            if len(axes) != depth or not all(re.fullmatch(r'[A-Z][A-Z0-9_]*', axis) for axis in axes):
                                raise ValueError('Unrecognized TGLF parameter axes')
                            points = {}
                            def visit(node, coordinates):
                                if len(coordinates) == depth:
                                    if suffix:
                                        if not kind(node, 'OMFITtglf'):
                                            columns = self.read(node)
                                            if 'eigenvalue_spectrum' not in columns and 'gbflux' not in columns:
                                                raise ValueError('Unrecognized TGLF result columns')
                                        result = Reference(node)
                                    else:
                                        # The old flux branch stores a row array,
                                        # while the current reader expects gbflux.
                                        if branch(node) or node is None:
                                            raise ValueError('Unrecognized legacy TGLF flux array')
                                        result = dict(gbflux=dict(data=Reference(node)))
                                    point = 'legacy{:06d}'.format(len(points) + 1)
                                    points[point] = dict(status='complete', source=[field, radius], label=str(radius),
                                        parameters=dict(zip(axes, coordinates)), result=result)
                                    return
                                for value, child in self.read(node).items():
                                    self.number(value)
                                    visit(child, coordinates + [value])
                            visit(data, [])
                            if not points:
                                raise ValueError('Empty TGLF scan')
                            group = (field, parameter)
                            if group not in grouped:
                                base = 'legacy-' + field + '-' + str(parameter)
                                run, number = base, 1
                                while run in runs:
                                    number += 1
                                    run = base + '-' + str(number)
                                grouped[group] = run
                                runs[run] = dict(mode='1d' if depth == 1 else '2d', migration_source=[field, parameter],
                                    plan=dict(axes=[dict(name=axis) for axis in axes], sources=[]), points={})
                            run = grouped[group]
                            try:
                                rho = self.number(radius)
                            except (TypeError, ValueError):
                                rho = None
                            record = runs[run]
                            record['plan']['sources'].append(dict(path=[field, radius], label=str(radius), rho=rho))
                            offset = len(record['points'])
                            for number, point in enumerate(points.values(), offset + 1):
                                record['points']['legacy{:06d}'.format(number)] = point
                            self.sources.append(dict(source=[str(part) for part in path], target=['RUN_DB', run], points=len(points)))
                        except (TypeError, ValueError, KeyError) as exc:
                            remaining.setdefault(radius, {})[parameter] = Reference(data)
                            self.issue(path, exc)
                if len(self.sources) > source_count:
                    replacements[field] = Layout(remaining)
        if replacements:
            replacements['RUN_DB'] = Layout(runs)
        return replacements
