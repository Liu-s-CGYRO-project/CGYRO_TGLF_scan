"""Check workbench extension contracts from AST, without importing application code."""
import argparse
import ast
import json
from pathlib import Path


def gui_inventory(repo):
    """Source inventory, not a claim that every callback was executed.

    Include extensionless native GUIs from OMFITsave.txt and callback sites in
    libraries. This keeps legacy entry points visible in future boundary audits.
    """
    repo = Path(repo).resolve()
    entries, controls, sources = [], [], set()
    widgets = {'Button', 'CheckBox', 'ComboBox', 'Entry', 'ObjectPicker', 'ModulePicker',
               'Slider', 'ShotTimeDevice', 'Tab', 'TabPages', 'deferred_section',
               'Checkbutton', 'Combobox', 'Radiobutton', 'Spinbox', 'Scale', 'bind'}
    for package in ('CGYRO_TGLF_scan', 'OMFITtemplates'):
        folder = repo / package
        for line in (folder / 'OMFITsave.txt').read_text(encoding='utf-8-sig').splitlines():
            parts = [part.strip() for part in line.split('<-:-:->')]
            if len(parts) < 3 or parts[1] != 'OMFITpythonGUI':
                continue
            path = (folder / parts[2]).resolve()
            if folder not in path.parents or not path.is_file():
                raise ValueError('Missing or external GUI source: ' + parts[2])
            sources.add(path)
            entries.append(dict(package=package, tree=parts[0], file=path.relative_to(repo).as_posix()))
        sources.update(path for path in folder.rglob('*.py')
                       if 'tests' not in path.relative_to(folder).parts)

    class Calls(ast.NodeVisitor):
        def __init__(self, path):
            self.path, self.context = path.relative_to(repo).as_posix(), []

        def visit_FunctionDef(self, node):
            self.context.append(node.name)
            self.generic_visit(node)
            self.context.pop()

        def visit_ClassDef(self, node):
            self.context.append(node.name)
            self.generic_visit(node)
            self.context.pop()

        def visit_Call(self, node):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else '')
            if name in widgets:
                flags = {kw.arg: ast.unparse(kw.value) for kw in node.keywords
                         if kw.arg in {'updateGUI', 'refresh_tree', 'refresh_scope', 'local', 'action',
                                       'command', 'postcommand', 'state'}}
                controls.append(dict(file=self.path, line=node.lineno, context='.'.join(self.context),
                                     call=ast.unparse(node.func), args=[ast.unparse(arg) for arg in node.args],
                                     options=flags))
            self.generic_visit(node)

    for path in sorted(sources):
        Calls(path).visit(ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path), feature_version=(3, 9)))
    return dict(gui_entries=entries, callback_sites=controls,
                counts=dict(entries=len(entries), sources=len(sources), sites=len(controls)),
                limitation='Static call sites; dynamic controls, callback execution and result I/O require runtime tests.')


def validate_workbench(project_root):
    library = Path(project_root) / 'LIB'

    def parse(name):
        return ast.parse((library / (name + '.py')).read_text(encoding='utf-8-sig'), feature_version=(3, 9))

    def assignment(tree, name):
        return next(node.value for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))

    catalog = parse('OMFITlib_workbench_catalog')
    pages = dict(ast.literal_eval(assignment(catalog, 'PAGES').args[0]))
    modules = ast.literal_eval(assignment(catalog, 'MODULES'))
    labels = ast.literal_eval(assignment(catalog, 'LABELS'))
    if len(set(pages.values())) != len(pages) or set(modules) != set(labels):
        raise ValueError('Workbench page keys must be unique; each module needs a label.')
    if any(not isinstance(path, tuple) or not path or any(not isinstance(key, str) or '/' in key for key in path)
           for path in modules.values()):
        raise ValueError('Module paths must be tuples of native OMFIT tree keys.')

    facade_tree = parse('OMFITlib_project_ui')
    facade = next(node for node in facade_tree.body if isinstance(node, ast.ClassDef) and node.name == 'ProjectUI')
    imported = {alias.asname or alias.name: (node.module, alias.name)
                for node in facade_tree.body if isinstance(node, ast.ImportFrom) for alias in node.names}
    owners, reviewed = {}, []
    for base in facade.bases:
        module, name = imported[base.id]
        tree = parse(module)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
        if any(isinstance(node, ast.FunctionDef) and node.name == '__init__' for node in cls.body):
            raise ValueError(name + ' must use the shared ProjectUI context, not replace its constructor.')
        reviewed.append((module, cls))
    reviewed.append(('OMFITlib_project_ui', facade))
    for module, cls in reviewed:
        for method in cls.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            if method.name in owners:
                raise ValueError('Workbench method shadowed: ' + method.name)
            owners[method.name] = module
    for key in list(pages.values()) + ['multi']:
        if 'render_' + key not in owners:
            raise ValueError('Registered workbench page has no renderer: ' + key)

    # Callbacks must outlive native execGlobLoc cleanup. Detect accidental
    # function-local imports in the newly split public interface modules.
    interface_modules = [module for module, _ in reviewed] + [
        'OMFITlib_workbench_catalog', 'OMFITlib_cgyro_workflow', 'OMFITlib_cgyro_present']
    for module in interface_modules:
        tree = parse(module)
        for node in ast.walk(tree):
            dependencies = ([node.module] if isinstance(node, ast.ImportFrom) and node.module else
                            [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            if node not in tree.body and any(name.startswith('OMFITlib_') for name in dependencies):
                raise ValueError('Callback dependency must be imported at module scope: ' + module)

    workflow = parse('OMFITlib_cgyro_workflow')
    batch = next(node for node in workflow.body if isinstance(node, ast.FunctionDef) and node.name == 'collect_batch')
    automatic = dict(zip((arg.arg for arg in batch.args.kwonlyargs), batch.args.kw_defaults))
    if 'automatic' not in automatic or ast.literal_eval(automatic['automatic']) is not False:
        raise ValueError('Manual collection must default to no waiting or solver retry.')
    single = next(node for node in workflow.body if isinstance(node, ast.FunctionDef) and node.name == 'collect_run')
    calls = [node for node in ast.walk(single) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == 'run_script']
    if len(calls) != 1 or not any(keyword.arg == 'allow_solver_retries' and isinstance(keyword.value, ast.Constant)
                                 and keyword.value.value is False for keyword in calls[0].keywords):
        raise ValueError('Single-run manual collection must explicitly forbid solver retry.')
    return dict(pages=len(pages), page_mixins=len(facade.bases), public_methods=len(owners),
                callback_imports='module_scope', collection_default='read_only', application_imported=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', nargs='?', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan')
    parser.add_argument('--gui-inventory', type=Path, help='Write all registered GUI and control/callback source locations')
    args = parser.parse_args()
    print(json.dumps(validate_workbench(args.project), indent=2))
    if args.gui_inventory is not None:
        inventory = gui_inventory(args.project.parent)
        args.gui_inventory.parent.mkdir(parents=True, exist_ok=True)
        args.gui_inventory.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(inventory['counts']))
