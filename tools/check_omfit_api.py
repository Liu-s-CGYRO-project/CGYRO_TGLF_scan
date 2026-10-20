"""Static OMFIT API compatibility checks; never execute project scripts.

OMFIT SortedDict.get/setdefault require a default argument; update accepts one
mapping, unlike dict.update's keyword form. Use the stricter form throughout
project code so a plain dict can safely become a saved OMFIT tree.
OMFIT also wraps Tk StringVar/BooleanVar with name as the first parameter;
explicit keyword arguments work in both native Tk and the OMFIT wrapper.
"""
import ast
from pathlib import Path
import warnings


def validate_tk_variable_calls(tree, source):
    """Inspect imported Tk aliases without importing Tk or opening a window."""
    variables = {'Variable', 'StringVar', 'BooleanVar', 'IntVar', 'DoubleVar'}
    modules, constructors = set(), {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'tkinter':
                    modules.add(alias.asname or alias.name)
                elif alias.name.startswith('tkinter.') and alias.asname is None:
                    modules.add('tkinter')
        elif isinstance(node, ast.ImportFrom) and node.module == 'tkinter':
            for alias in node.names:
                if alias.name in variables:
                    constructors[alias.asname or alias.name] = alias.name
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = ''
        if (isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name)
                and function.value.id in modules and function.attr in variables):
            name = function.attr
        elif isinstance(function, ast.Name):
            name = constructors.get(function.id, '')
        if not name:
            continue
        count += 1
        if node.args or not any(item.arg == 'master' for item in node.keywords):
            raise ValueError('{}:{}：{} 必须显式传入 master=，并用 value= / name= 传参；'
                             'OMFIT 会将 StringVar / BooleanVar 的首个位置参数解释为 name'.format(
                                 source, node.lineno, name))
    return count


def _native_getter(node, tree):
    receiver = node.func.value
    if (isinstance(receiver, ast.Attribute) and receiver.attr == 'environ'
            and isinstance(receiver.value, ast.Name) and receiver.value.id == 'os'):
        return True
    # The legend editor's box is a Tk Listbox; get(index) is its native API.
    if isinstance(receiver, ast.Name) and receiver.id == 'box':
        assignments = [n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'box' for t in n.targets)]
        return bool(assignments) and all(
            isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
            and isinstance(value.func.value, ast.Name) and value.func.value.id == 'tk'
            and value.func.attr == 'Listbox' for value in assignments)
    return False


def validate_project_api(project_root, extra_sources=()):
    project_root = Path(project_root).resolve()
    sources = set(project_root.rglob('*.py'))
    sources.update(Path(path).resolve() for path in extra_sources)
    problems, methods, tk_variables = [], 0, 0
    for path in sorted(sources):
        if project_root not in path.parents or not path.is_file():
            raise ValueError('Invalid project source: ' + str(path))
        name = path.relative_to(project_root).as_posix()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=name,
                             feature_version=(3, 9))
        tk_variables += validate_tk_variable_calls(tree, name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            method = node.func.attr
            if method not in ('get', 'setdefault', 'update'):
                continue
            methods += 1
            keywords = {item.arg for item in node.keywords}
            message = ''
            has_key = len(node.args) == 1 or (not node.args and 'key' in keywords)
            if method in ('get', 'setdefault') and has_key and 'default' not in keywords and None not in keywords:
                if method != 'get' or not _native_getter(node, tree):
                    message = 'OMFIT 映射的 {} 必须明确传入默认值'.format(method)
            elif method == 'update' and node.keywords:
                message = 'OMFIT 映射的 update 需传入一个字典，请用 update(dict(...))'
            if message:
                problems.append('{}:{}：{}'.format(name, node.lineno, message))
    if problems:
        raise ValueError('\n'.join(problems))
    return {'files': len(sources), 'method_calls': methods, 'tk_variables': tk_variables}
