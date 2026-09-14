"""Read-only compatibility inventory against an explicit OMFIT source checkout.

Checks every project Python file, saved expression, registered library import,
literal script call and OMFITx call. Dynamic data-dependent paths are reported
separately; a static pass is never a claim of complete runtime compatibility.
"""
import argparse
import ast
from collections import Counter
import copy
import hashlib
import inspect
import json
from pathlib import Path
import sys
import warnings

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'OMFITtemplates/LIB'))
from OMFITlib_template_archive import parse_tree


def api_signatures(source):
    signatures = {}
    for node in ast.parse(source.read_text(encoding='utf-8')).body:
        method = node
        if isinstance(node, ast.ClassDef):
            method = next((n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == '__init__'), None)
            if method is None and node.name == 'same_row':
                signatures[node.name] = inspect.Signature()
                continue
        if not isinstance(method, ast.FunctionDef):
            continue
        arguments = copy.deepcopy(method.args)
        if isinstance(node, ast.ClassDef):
            arguments.args = arguments.args[1:]
        arguments.defaults = [ast.Constant(None) for _ in arguments.defaults]
        arguments.kw_defaults = [ast.Constant(None) if value is not None else None for value in arguments.kw_defaults]
        function = ast.FunctionDef(name=node.name, args=arguments, body=[ast.Pass()], decorator_list=[], returns=None)
        scope = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), '<signature>', 'exec'), scope)
        signatures[node.name] = inspect.signature(scope[node.name])
    return signatures


def literal_path(node):
    keys = []
    while isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        keys.insert(0, node.slice.value)
        node = node.value
    return (node.id, tuple(keys)) if isinstance(node, ast.Name) else (None, ())


def audit(omfit_source):
    omfit_source = Path(omfit_source).resolve()
    signatures = api_signatures(omfit_source / 'omfit_classes/OMFITx.py')
    rows = parse_tree((REPO / 'OMFITsave.txt').read_bytes())
    rowmap = {row.keys: row for row in rows}
    modules = [row.keys for row in rows if row.kind == 'OMFITmodule']
    registered = {}
    for row in rows:
        if row.kind.startswith('OMFITpython'):
            owner = max((module for module in modules if row.keys[:len(module)] == module), key=len)
            registered.setdefault((REPO / row.ref).resolve(), []).append((row, owner))
    paths = sorted(p for root in ('CGYRO_TGLF_scan', 'OMFITtemplates')
                   for p in (REPO / root).rglob('*.py') if 'tests' not in p.parts)
    trees, inventory, findings = {}, [], []
    counts = Counter()

    def finding(path, line, category, detail, disabled=False):
        findings.append(dict(file=str(path.relative_to(REPO).as_posix()), line=line, category=category,
                             detail=detail, disabled_entry=disabled))

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', (SyntaxWarning, DeprecationWarning))
        for path in paths:
            raw = path.read_bytes()
            tree = ast.parse(raw.decode('utf-8-sig'), filename=str(path), feature_version=(3, 9))
            compile(tree, str(path), 'exec')
            trees[path.resolve()] = tree
            entries = registered.get(path.resolve(), [])
            statements = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
            disabled = bool(statements and isinstance(statements[0], ast.Raise))
            inventory.append(dict(file=path.relative_to(REPO).as_posix(), sha256=hashlib.sha256(raw).hexdigest(),
                                  lines=len(raw.splitlines()), entries=[row.fields[0] for row, _ in entries],
                                  disabled_entry=disabled))
            builtins = {alias.asname or alias.name for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == 'builtins'
                        for alias in n.names}
            parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
            for node in ast.walk(tree):
                library_names = ([node.module] if isinstance(node, ast.ImportFrom) and node.module
                                 else [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                for name in library_names:
                    if not entries or not name.startswith('OMFITlib_'):
                        continue
                    counts['registered_library_imports'] += 1
                    scope = parents.get(node)
                    while scope is not None:
                        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                            finding(path, node.lineno, 'deferred_library_import',
                                    name + ': may run after the native OMFIT import hook has been removed', disabled)
                            break
                        scope = parents.get(scope)
                if isinstance(node, ast.ImportFrom):
                    name = node.module or ''
                    if name.startswith('OMFITlib_'):
                        for row, owner in entries:
                            if owner + ('LIB', name) not in rowmap:
                                finding(path, node.lineno, 'library_registration', name, disabled)
                    elif name.startswith('classes.'):
                        finding(path, node.lineno, 'legacy_framework_import', name, disabled)
                    elif name in ('cgyro_read_xj', 'cgyro_ball', 'cgyro_ball_class'):
                        finding(path, node.lineno, 'private_python_path', name, disabled)
                if not isinstance(node, ast.Call):
                    continue
                if entries and isinstance(node.func, ast.Name) and node.func.id in ('all', 'any', 'sum') and node.func.id not in builtins:
                    if node.args and isinstance(node.args[0], ast.GeneratorExp):
                        finding(path, node.lineno, 'pylab_generator_reduction', ast.unparse(node), disabled)
                if isinstance(node.func, ast.Name) and node.func.id == 'exec' and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == 'line':
                    finding(path, node.lineno, 'line_by_line_helper', 'Helper must be executed as a complete program', disabled)
                if not isinstance(node.func, ast.Attribute):
                    continue
                receiver = ast.unparse(node.func.value)
                if receiver == 'sys.path' and node.func.attr in ('append', 'insert'):
                    if any(isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value.startswith('/') for a in node.args):
                        finding(path, node.lineno, 'absolute_import_path', ast.unparse(node), disabled)
                if receiver in ('OMFITx', 'self.ui', 'ui'):
                    signature = signatures.get(node.func.attr)
                    if signature is None:
                        finding(path, node.lineno, 'unknown_omfitx_api', node.func.attr, disabled)
                    elif any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                        counts['dynamic_omfitx_calls'] += 1
                    else:
                        counts['bound_omfitx_calls'] += 1
                        try:
                            signature.bind(*[None for _ in node.args], **{k.arg: None for k in node.keywords})
                        except TypeError as error:
                            finding(path, node.lineno, 'omfitx_signature', str(error), disabled)
                if node.func.attr in ('run', 'runNoGUI', 'plot', 'prun'):
                    base, keys = literal_path(node.func.value)
                    if base != 'root' or len(keys) < 2 or not any(k in keys for k in ('SCRIPTS', 'GUIS', 'PLOTS', 'LIB')):
                        counts['dynamic_script_calls'] += 1
                        continue
                    for row, owner in entries:
                        target = rowmap.get(owner + keys)
                        counts['literal_script_calls'] += 1
                        if target is None:
                            finding(path, node.lineno, 'missing_script_target', str(keys), disabled)
                        elif node.func.attr == 'plot' and target.kind != 'OMFITpythonPlot':
                            finding(path, node.lineno, 'script_type', target.kind + ' has no plot method', disabled)
    expressions = []
    for row in rows:
        if row.kind != 'OMFITexpression':
            continue
        text = ast.literal_eval(row.fields[2][1:])
        ast.parse(text, feature_version=(3, 9))
        expressions.append(dict(location=row.fields[0], syntax_python39=True))
    settings = []
    for path in sorted(REPO.rglob('SettingsNamelist.txt')):
        json.loads(path.read_bytes())
        settings.append(path.relative_to(REPO).as_posix())
    return dict(omfit_source=str(omfit_source), python_files=len(inventory), source_lines=sum(i['lines'] for i in inventory),
                registered_entries=sum(len(v) for v in registered.values()), modules=len(modules),
                syntax_python39=True, expressions=expressions, settings=settings, counters=dict(counts),
                inventory=inventory, findings=findings, complete_runtime_compatibility_proven=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('omfit_source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.omfit_source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps({key: value for key, value in result.items() if key not in ('inventory', 'settings', 'expressions', 'findings')}, indent=2))
    print('Findings:', dict(Counter(item['category'] for item in result['findings'])))
