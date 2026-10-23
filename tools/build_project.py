"""Build a result-free, self-contained OMFIT project from reviewed tree references."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile
from omfit_help import validate_module_help, validate_module_settings
from check_omfit_api import validate_project_api, validate_tk_variable_calls
from check_workbench import validate_workbench
from release_policy import MAX_PROJECT_PACKAGE_BYTES

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'OMFITtemplates/LIB'))
from OMFITlib_template_archive import Project, TemplateError, json_bytes, parse_tree, tree_bytes
from OMFITlib_template_service import new_file


def _refresh_manifest(destination, content):
    """Replace one manifest atomically; the validated ZIP is a separate commit."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.project-manifest-', dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _font_constants(path):
    tree = ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 9))
    return {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)}


def validate_font_imports(library, names):
    """Inspect the font dependency graph without importing any Tk/UI library."""
    graph = {}
    for name in names:
        path = library / (name + '.py')
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path), feature_version=(3, 9))
        graph[name] = set()
        for node in ast.walk(tree):
            imported = ([node.module] if isinstance(node, ast.ImportFrom) and node.module else
                        [item.name for item in node.names] if isinstance(node, ast.Import) else [])
            for dependency in imported:
                if not dependency.startswith('OMFITlib_'):
                    continue
                if node not in tree.body:
                    raise TemplateError('{}:{}：字体回调依赖必须在文件顶部导入 {}'.format(name, node.lineno, dependency))
                if dependency in names:
                    graph[name].add(dependency)
    visited = set()

    def visit(name, active):
        if name in active:
            raise TemplateError('字体库循环依赖：' + ' → '.join(active + [name]))
        if name not in visited:
            for dependency in sorted(graph[name]):
                visit(dependency, active + [name])
            visited.add(name)

    for name in names:
        visit(name, [])


def validate_gui_fonts():
    """Check cache-loader parity and pinned metadata without acquiring fonts."""
    first, second = ROOT / 'CGYRO_TGLF_scan', ROOT / 'OMFITtemplates'
    modules = ('OMFITlib_gui_fonts', 'OMFITlib_gui_font_data', 'OMFITlib_font_cache',
               'OMFITlib_font_download_ui', 'OMFITlib_font_ui', 'OMFITlib_font_manifest')
    names = ['LIB/' + name + '.py' for name in modules]
    names.append('DOCS/FONT_LICENSE.txt')
    for name in names:
        if (first / name).read_bytes() != (second / name).read_bytes():
            raise TemplateError('独立模块字体加载器不一致：' + name)
    validate_font_imports(first / 'LIB', modules + ('OMFITlib_plot_font_assets', 'OMFITlib_plot_font_data', 'OMFITlib_plot_fonts'))
    values = _font_constants(first / 'LIB/OMFITlib_font_manifest.py')
    identity = _font_constants(first / 'LIB/OMFITlib_gui_font_data.py')
    if identity['FONT_SHA256'] != '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b':
        raise TemplateError('GUI 字体上游标识改变')
    if values['FONT_FILES'][identity['FONT_FILENAME']]['sha256'] != identity['FONT_SHA256']:
        raise TemplateError('GUI 字体清单不一致')
    prefix = 'https://github.com/Liu-s-CGYRO-project/CGYRO_TGLF_scan/releases/download/omfit-fonts/v1/'
    for kind, pack in values['FONT_BUNDLES'].items():
        if pack['url'] != prefix + pack['filename'] or pack['bytes'] <= 0 or len(pack['sha256']) != 64:
            raise TemplateError('字体独立包标识无效：' + kind)
        for name in pack['fonts']:
            spec = values['FONT_FILES'][name]
            if spec['bundle'] != kind or any(pack['members'][name][key] != spec[key] for key in ('bytes', 'sha256')):
                raise TemplateError('字体独立包与文件标识不一致：' + name)
    if hashlib.sha256((first / 'DOCS/FONT_LICENSE.txt').read_bytes()).hexdigest() != '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2':
        raise TemplateError('字体许可文件不一致')


def validate_plot_fonts():
    """Check original face hashes and complete notices without font loading."""
    specification = json.loads((ROOT / 'tools/plot_fonts_sources.json').read_bytes())
    constants = _font_constants(ROOT / 'CGYRO_TGLF_scan/LIB/OMFITlib_plot_font_data.py')
    resources = _font_constants(ROOT / 'CGYRO_TGLF_scan/LIB/OMFITlib_font_manifest.py')['FONT_FILES']
    assets = constants['FONT_ASSETS']
    if constants['DEFAULT_FONTS'] != specification['defaults'] or len(assets) != len(specification['faces']):
        raise TemplateError('绘图字体默认值或资源清单不一致')
    digests = []
    for asset, face in zip(assets, specification['faces']):
        if any(asset[key] != face[key] for key in ('filename', 'family', 'style', 'weight')):
            raise TemplateError('绘图字体资源与上游清单不一致')
        expected = specification['files'][asset['filename']]
        if any(asset[key] != expected[key] or resources[asset['filename']][key] != expected[key] for key in ('bytes', 'sha256')):
            raise TemplateError('绘图字体字节标识与上游文件不一致：' + asset['filename'])
        if 'payload' in asset:
            raise TemplateError('主程序不得重新嵌入字体文件')
        digests.append(asset['sha256'])
    if hashlib.sha256(''.join(digests).encode('ascii')).hexdigest() != constants['BUNDLE_ID']:
        raise TemplateError('绘图字体资源版本不一致')
    notice = (ROOT / 'CGYRO_TGLF_scan/DOCS/PLOT_FONTS_LICENSE.txt').read_bytes()
    for name in specification['licenses']:
        begin = ('=' * 72 + '\n' + name + '\n' + '=' * 72 + '\n').encode('utf-8')
        if begin not in notice:
            raise TemplateError('缺少绘图字体许可：' + name)
        data = notice.split(begin, 1)[1][:specification['files'][name]['bytes']]
        if hashlib.sha256(data).hexdigest() != specification['files'][name]['sha256']:
            raise TemplateError('绘图字体许可不一致：' + name)


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
            try:
                validate_tk_variable_calls(tree, row.ref)
            except ValueError as exc:
                raise TemplateError(str(exc)) from exc
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
    validate_gui_fonts()
    validate_plot_fonts()
    rows = parse_tree((ROOT / 'OMFITsave.txt').read_bytes())
    # Historical validation records stay in the repository, outside installers.
    selected = {'OMFITsave.txt', 'MainSettingsNamelist.txt', 'OMFIT_COMPATIBILITY.md'}
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
            # Development suites stay in Git. They are not runtime resources;
            # direct tree references must be removed too (checked below).
            contents = [path for path in target.rglob('*') if path.is_file() and '__pycache__' not in path.parts
                        and not path.relative_to(ROOT).as_posix().startswith('OMFITtemplates/tests/')]
            selected.update(path.relative_to(ROOT).as_posix() for path in contents)
            if not contents:
                directories.add(row.ref)
        else:
            raise TemplateError('缺少工程引用：' + row.ref)
    if any(name.startswith('OMFITtemplates/tests/') for name in selected):
        raise TemplateError('运行包仍有测试文件引用，请从保存树移到仓库开发入口')
    if any((ROOT / name).is_symlink() for name in selected):
        raise TemplateError('分发工程不允许符号链接')
    validate_library_imports(rows, ROOT)
    module_root = ROOT / 'CGYRO_TGLF_scan'
    workbench_review = validate_workbench(module_root)
    python_refs = {(ROOT / row.ref).resolve() for row in rows
                   if row.ref and row.kind.startswith('OMFITpython')
                   and module_root in (ROOT / row.ref).resolve().parents}
    try:
        api_review = validate_project_api(module_root, python_refs)
    except ValueError as exc:
        raise TemplateError(str(exc)) from exc
    for manifest in (ROOT / 'CGYRO_TGLF_scan/OMFITsave.txt', ROOT / 'OMFITtemplates/OMFITsave.txt'):
        if manifest.is_file():
            validate_library_imports(parse_tree(manifest.read_bytes()), manifest.parent)
    metadata = json.loads((ROOT / 'PROJECT_CONTENTS.json').read_bytes())
    # Hash and write the same snapshot. A concurrent source edit must not make
    # the published manifest disagree with the bytes inside its own package.
    source_bytes = {name: (ROOT / name).read_bytes() for name in sorted(selected)}
    metadata['files'] = {name: hashlib.sha256(content).hexdigest() for name, content in source_bytes.items()}
    manifest_bytes = json_bytes(metadata)
    # The repository walkthrough is not a native runtime reference. Keep it on
    # GitHub; module help and deployment instructions remain in this archive.
    selected.add('PROJECT_CONTENTS.json')
    with new_file(output) as temporary:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            # Native OMFIT chooses the project directory from namelist()[0].
            for name in ['OMFITsave.txt'] + sorted(selected - {'OMFITsave.txt'}):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                content = manifest_bytes if name == 'PROJECT_CONTENTS.json' else source_bytes[name]
                archive.writestr(info, content, compresslevel=9)
            for name in sorted(directories):
                archive.writestr(name.rstrip('/') + '/', b'')
        # Keep a bounded code-only installer without stripping maintenance
        # comments or integrity checks merely to meet the old 1 MB threshold.
        if temporary.stat().st_size >= MAX_PROJECT_PACKAGE_BYTES:
            raise TemplateError('代码安装包超过 2 MiB，请将大型资源移到独立资源包')
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
    # Output publication and source metadata are separate commits. A rejected
    # build must never leave a new source manifest behind. If this final refresh
    # fails, report that the already validated package still exists for recovery.
    try:
        _refresh_manifest(ROOT / 'PROJECT_CONTENTS.json', manifest_bytes)
    except OSError as exc:
        raise TemplateError('安装包已生成，但源清单刷新失败：' + str(output)) from exc
    return {'output': str(output), 'files': len(selected), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'calculation_data_files': 0,
            'modules': project.roots, 'api_compatibility': api_review, 'workbench_contracts': workbench_review}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    version = json.loads((ROOT / 'PROJECT_CONTENTS.json').read_bytes())['version']
    parser.add_argument('--output', default=str(ROOT / ('dist/CGYRO_TGLF_scan_code_only_' + version + '.zip')))
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
