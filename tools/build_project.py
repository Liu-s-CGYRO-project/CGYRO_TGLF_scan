"""Build a result-free, self-contained OMFIT project from reviewed tree references."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import zlib
from omfit_help import validate_module_help, validate_module_settings
from check_omfit_api import validate_project_api

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'OMFITtemplates/LIB'))
from OMFITlib_template_archive import Project, TemplateError, json_bytes, parse_tree, tree_bytes
from OMFITlib_template_service import new_file


def validate_gui_fonts():
    """Keep embedded/standalone typography identical; do not load native fonts."""
    first = ROOT / 'CGYRO_TGLF_scan'
    second = ROOT / 'OMFITtemplates'
    names = ['LIB/OMFITlib_gui_fonts.py', 'LIB/OMFITlib_gui_font_data.py', 'DOCS/FONT_LICENSE.txt']
    names.extend('LIB/OMFITlib_gui_font_part' + str(index) + '.py' for index in (1, 2, 3))
    for name in names:
        if (first / name).read_bytes() != (second / name).read_bytes():
            raise TemplateError('独立模块字体副本不一致：' + name)
    tree = ast.parse((first / 'LIB/OMFITlib_gui_font_data.py').read_text(encoding='utf-8'), feature_version=(3, 9))
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and node.targets[0].id != 'FONT_B85'}
    encoded = []
    for index in (1, 2, 3):
        source = first / ('LIB/OMFITlib_gui_font_part' + str(index) + '.py')
        if source.stat().st_size > 8 * 1024 ** 2:
            raise TemplateError('字体分片超过旧管理器的单文件限制')
        part_tree = ast.parse(source.read_text(encoding='utf-8'), feature_version=(3, 9))
        values = {node.targets[0].id: ast.literal_eval(node.value) for node in part_tree.body if isinstance(node, ast.Assign)}
        encoded.append(values['FONT_PART' + str(index)])
    assignment = next(node.value for node in tree.body if isinstance(node, ast.Assign) and node.targets[0].id == 'FONT_B85')
    expected = ast.parse('FONT_PART1 + FONT_PART2 + FONT_PART3', mode='eval').body
    if ast.dump(assignment) != ast.dump(expected):
        raise TemplateError('字体分片组合与已核对的顺序不一致')
    font = zlib.decompress(base64.b85decode(b''.join(encoded)))
    digest = hashlib.sha256(font).hexdigest()
    if digest != constants['FONT_SHA256'] or digest != '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b':
        raise TemplateError('字体资源与已核对的上游文件不一致')
    if hashlib.sha256((first / 'DOCS/FONT_LICENSE.txt').read_bytes()).hexdigest() != '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2':
        raise TemplateError('字体许可文件不一致')


def validate_plot_fonts():
    """Check pinned payloads and notices without importing or rendering fonts."""
    specification = json.loads((ROOT / 'tools/plot_fonts_sources.json').read_bytes())
    tree = ast.parse((ROOT / 'CGYRO_TGLF_scan/LIB/OMFITlib_plot_font_data.py').read_text(encoding='utf-8'), feature_version=(3, 9))
    constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)}
    assets = constants['FONT_ASSETS']
    if constants['DEFAULT_FONTS'] != specification['defaults'] or len(assets) != len(specification['faces']):
        raise TemplateError('绘图字体默认值或资源清单不一致')
    digests = []
    for asset, face in zip(assets, specification['faces']):
        if any(asset[key] != face[key] for key in ('filename', 'family', 'style', 'weight')):
            raise TemplateError('绘图字体资源与上游清单不一致')
        data = zlib.decompress(base64.b85decode(asset['payload']))
        digest = hashlib.sha256(data).hexdigest()
        if digest != asset['sha256'] or digest != specification['files'][asset['filename']]['sha256']:
            raise TemplateError('绘图字体字节与上游文件不一致：' + asset['filename'])
        digests.append(digest)
    if hashlib.sha256(''.join(digests).encode('ascii')).hexdigest() != constants['BUNDLE_ID']:
        raise TemplateError('绘图字体资源版本不一致')
    notice = (ROOT / 'CGYRO_TGLF_scan/DOCS/PLOT_FONTS_LICENSE.txt').read_bytes()
    for name in specification['licenses']:
        begin = ('=' * 72 + '\n' + name + '\n' + '=' * 72 + '\n').encode('utf-8')
        if begin not in notice:
            raise TemplateError('缺少绘图字体许可：' + name)
        # Compare original bytes, preserving upstream line endings and EOF.
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
    module_root = ROOT / 'CGYRO_TGLF_scan'
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
            'modules': project.roots, 'api_compatibility': api_review}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    version = json.loads((ROOT / 'PROJECT_CONTENTS.json').read_bytes())['version']
    parser.add_argument('--output', default=str(ROOT / ('dist/CGYRO_TGLF_scan_code_only_' + version + '.zip')))
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=False, indent=2))
