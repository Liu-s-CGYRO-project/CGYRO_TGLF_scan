"""Static OMFIT mapping compatibility checks; never execute project scripts.

OMFIT SortedDict.get/setdefault require a default argument; update accepts one
mapping, unlike dict.update's keyword form. Use the stricter form throughout
project code so a plain dict can safely become a saved OMFIT tree.
"""
import ast
from pathlib import Path
import warnings


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
    problems, methods = [], 0
    for path in sorted(sources):
        if project_root not in path.parents or not path.is_file():
            raise ValueError('Invalid project source: ' + str(path))
        name = path.relative_to(project_root).as_posix()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=name,
                             feature_version=(3, 9))
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
    return {'files': len(sources), 'method_calls': methods}
