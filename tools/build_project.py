"""Build a result-free, self-contained OMFIT project from reviewed tree references."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from omfit_help import validate_module_help, validate_module_settings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'OMFITtemplates/LIB'))
from OMFITlib_template_archive import Project, TemplateError, json_bytes, parse_tree, tree_bytes
from OMFITlib_template_service import new_file


def validate_tgyro_seed(data, name):
    """Match native OMFITgacode's requirement for leading DIR directives."""
    past_directories = False
    for number, line in enumerate(data.decode('utf-8').splitlines(), 1):
        if line.lstrip().startswith('DIR '):
            if past_directories or not line.startswith('DIR '):
                raise TemplateError(name + ':' + str(number) + '：DIR 行必须连续放在文件开头，注释在其后')
            fields = line.split()
            if len(fields) != 3 or not fields[2].isdigit():
                raise TemplateError(name + ':' + str(number) + '：内置 TGYRO 模板需使用 DIR 目录名 进程数')
        else:
            past_directories = True
            text = line.strip()
            if text and not text.startswith('#') and '=' not in text:
                raise TemplateError(name + ':' + str(number) + '：参数行缺少等号')


def validate_library_imports(rows, base):
    """Statically match native OMFIT's current-root LIB lookup, without execution."""
    modules = {row.keys for row in rows if row.kind == 'OMFITmodule'}
    by_key = {row.keys: row for row in rows}
    imports = {}
    for row in rows:
        if not row.ref or not row.kind.startswith('OMFITpython'):
            continue
        module = max((key for key in modules if row.keys[:len(key)] == key), key=len, default=())
        if row.ref not in imports:
            path = (base / row.ref).resolve()
            if base.resolve() not in path.parents or not path.is_file():
                raise TemplateError('无效的 Python 文件引用：' + row.ref)
            tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=row.ref, feature_version=(3, 9))
            names = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.extend((item.name, node.lineno) for item in node.names if item.name.startswith('OMFITlib_'))
                elif isinstance(node, ast.ImportFrom) and (node.module or '').startswith('OMFITlib_'):
                    names.append((node.module, node.lineno))
            imports[row.ref] = names
        for name, line in imports[row.ref]:
            library = by_key.get(module + ('LIB', name))
            if library is None or library.kind != 'OMFITpythonTask' or not library.ref:
                raise TemplateError('{}:{}：模块 {} 的 LIB 未登记 {}'.format(
                    row.ref, line, '/'.join(map(str, module)) or 'root', name))


def build(output):
    output = Path(output).expanduser().resolve()
    rows = parse_tree((ROOT / 'OMFITsave.txt').read_bytes())
    selected = {'OMFITsave.txt', 'MainSettingsNamelist.txt', 'VALIDATION.md', 'OMFIT_COMPATIBILITY.md'}
    directories = set()
    for row in rows:
        if not row.ref:
            continue
        target = (ROOT / row.ref).resolve()
        if ROOT.resolve() not in target.parents:
            raise TemplateError('工程引用跨出仓库：' + row.ref)
        if target.is_file():
            if row.kind == 'OMFIThelp':
                validate_module_help(target.read_bytes(), row.ref)
            elif row.kind == 'OMFITsettings':
                validate_module_settings(target.read_bytes(), row.ref)
            elif row.kind == 'OMFITgacode' and target.name == 'input.tgyro':
                validate_tgyro_seed(target.read_bytes(), row.ref)
            selected.add(row.ref)
        elif target.is_dir():
            contents = [path for path in target.rglob('*') if path.is_file() and '__pycache__' not in path.parts]
            selected.update(path.relative_to(ROOT).as_posix() for path in contents)
            if not contents:
                directories.add(row.ref)
        else:
            raise TemplateError('缺少工程引用：' + row.ref)
    if any((ROOT / name).is_symlink() for name in selected):
        raise TemplateError('分发工程不允许符号链接')
    validate_library_imports(rows, ROOT)
    for manifest in (ROOT / 'CGYRO_TGLF_scan/OMFITsave.txt', ROOT / 'OMFITtemplates/OMFITsave.txt'):
        if manifest.is_file():
            validate_library_imports(parse_tree(manifest.read_bytes()), manifest.parent)
    metadata = json.loads((ROOT / 'PROJECT_CONTENTS.json').read_bytes())
    metadata['files'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(selected)}
    (ROOT / 'PROJECT_CONTENTS.json').write_bytes(json_bytes(metadata))
    selected.update({'README.md', 'PROJECT_CONTENTS.json'})
    with new_file(output) as temporary:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            # Native OMFIT chooses the project directory from namelist()[0].
            for name in ['OMFITsave.txt'] + sorted(selected - {'OMFITsave.txt'}):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, (ROOT / name).read_bytes())
            for name in sorted(directories):
                archive.writestr(name.rstrip('/') + '/', b'')
        with Project(temporary) as project:
            project.require_entry_first()
            owned = project.ownership(project.roots)
            data = [name for name, category in owned.items() if category == 'data']
            if data:
                raise TemplateError('发现计算数据文件：' + ', '.join(data[:5]))
            for row in project.rows:
                if project.selected(row, project.roots) and project.category(row) == 'data' and not (
                        row.kind == 'OMFITtree' and not row.ref and row.keys[:-1] in project.modules):
                    raise TemplateError('发现非空案例节点：' + row.fields[0])
            if project.z.testzip() is not None:
                raise TemplateError('ZIP CRC 校验失败')
    return {'output': str(output), 'files': len(selected), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'calculation_data_files': 0,
            'modules': project.roots}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    version = json.loads((ROOT / 'PROJECT_CONTENTS.json').read_bytes())['version']
    parser.add_argument('--output', default=str(ROOT / ('dist/CGYRO_TGLF_scan_code_only_' + version + '.zip')))
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
