"""Build a result-free, self-contained OMFIT project from reviewed tree references."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'OMFITtemplates/LIB'))
from OMFITlib_template_archive import Project, TemplateError, json_bytes, parse_tree, tree_bytes
from OMFITlib_template_service import new_file


def build(output):
    output = Path(output).expanduser().resolve()
    rows = parse_tree((ROOT / 'OMFITsave.txt').read_bytes())
    selected = {'OMFITsave.txt', 'MainSettingsNamelist.txt', 'VALIDATION.md'}
    directories = set()
    for row in rows:
        if not row.ref:
            continue
        target = (ROOT / row.ref).resolve()
        if ROOT.resolve() not in target.parents:
            raise TemplateError('工程引用跨出仓库：' + row.ref)
        if target.is_file():
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
    metadata = json.loads((ROOT / 'PROJECT_CONTENTS.json').read_bytes())
    metadata['files'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(selected)}
    (ROOT / 'PROJECT_CONTENTS.json').write_bytes(json_bytes(metadata))
    selected.update({'README.md', 'PROJECT_CONTENTS.json'})
    with new_file(output) as temporary:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(selected):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, (ROOT / name).read_bytes())
            for name in sorted(directories):
                archive.writestr(name.rstrip('/') + '/', b'')
        with Project(temporary) as project:
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
