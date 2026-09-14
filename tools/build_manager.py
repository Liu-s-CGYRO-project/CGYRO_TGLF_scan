"""Build independent Linux and native OMFIT manager packages from registered files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'OMFITtemplates'
sys.path.insert(0, str(MODULE / 'LIB'))
from OMFITlib_template_archive import parse_tree
from OMFITlib_template_manager_update import package_names
from OMFITlib_template_service import new_file
from OMFITlib_template_versions import MANAGER_VERSION

README = '''# OMFIT 模板管理器 {version}

这是独立的管理器发行包，不附带计算工程、案例或结果。已有模板库和代理偏好沿用用户配置目录。

## Linux 桌面

解压到一个新目录，进入目录后运行 `bash start_manager.sh`。
需要 Python 3.9+ 和 Tk；指定解释器时使用：

```bash
OMFIT_TEMPLATE_PYTHON=/path/to/python bash start_manager.sh
```

需要安装应用菜单入口时，运行 `bash install_desktop.sh`；无需 sudo。

## OMFIT 内使用

选择 OMFIT 的 `Import module...`，导入同版本的 `.omfit.zip`，模块位置选择 `OMFITtemplates`。
已有同名模块时确认替换管理模块，保存工程，关闭旧管理器窗口并重新打开。
也可从解压目录加载 `OMFITtemplates/OMFITsave.txt`。这个模块包只包含管理器。

## 排序和独立更新

版本列表默认按实际发布时间从新到旧排列，搜索框右侧可切换版本号排序。
数字版本按数值比较（1.10.0 在 1.9.0 前），旧日期版本保留在历史序列中。
右上角“检查管理器更新”显示当前和最新稳定版本，使用当前代理配置。
更新源固定为 Liu-s-CGYRO-project/CGYRO_TGLF_scan 的独立管理器 Release。
下载 Linux 或 OMFIT 安装包后会校验大小和 SHA-256，用户再安装并重新打开窗口。
计算工程继续通过“更新 / 切换”页预览和生成新工程。

公共 GitHub 代理可选“手动 HTTP 代理”，主机 47.102.120.146，端口 18889，用户名和密码留空。
公开版本检查与下载不需要 GitHub 登录；私有仓库和发布仍使用各自的 GitHub 账号。
'''


def build(directory):
    directory = Path(directory).expanduser().resolve()
    selected = {'OMFITsave.txt', 'SettingsNamelist.txt', 'help.rst'}
    for row in parse_tree((MODULE / 'OMFITsave.txt').read_bytes()):
        if row.ref:
            path = (MODULE / row.ref).resolve()
            if MODULE.resolve() not in path.parents or not path.is_file() or path.is_symlink():
                raise ValueError('Invalid manager reference: ' + row.ref)
            selected.add(path.relative_to(MODULE).as_posix())
    payload = {'OMFITtemplates/' + name: (MODULE / name).read_bytes().replace(b'\r\n', b'\n')
               for name in sorted(selected)}
    payload['README.md'] = README.format(version=MANAGER_VERSION).encode('utf-8')
    payload['start_manager.sh'] = (b'#!/bin/sh\nset -eu\n'
        b'task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        b'exec sh "$task_dir/OMFITtemplates/start_manager.sh" "$@"\n')
    payload['install_desktop.sh'] = (b'#!/bin/sh\nset -eu\n'
        b'task_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        b'exec "${OMFIT_TEMPLATE_PYTHON:-python3}" "$task_dir/OMFITtemplates/install_desktop.py" "$@"\n')
    checksums = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
    payload['SHA256SUMS.json'] = (json.dumps(checksums, indent=2) + '\n').encode()
    names = package_names(MANAGER_VERSION)
    linux = directory / names['linux']
    prefix = linux.name[:-7]
    with new_file(linux) as temporary:
        with tarfile.open(temporary, 'w:gz') as archive:
            for name, data in sorted(payload.items()):
                info = tarfile.TarInfo(prefix + '/' + name)
                info.size = len(data)
                info.mode = 0o755 if name.endswith('.sh') else 0o644
                archive.addfile(info, io.BytesIO(data))
    module = directory / names['omfit']
    first = 'OMFITtemplates/OMFITsave.txt'
    with new_file(module) as temporary:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in [first] + sorted(name for name in payload if name.startswith('OMFITtemplates/') and name != first):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, payload[name])
        with zipfile.ZipFile(temporary) as archive:
            assert archive.namelist()[0] == first
            assert archive.testzip() is None
            for name in archive.namelist():
                assert archive.read(name) == payload[name]
    return dict(version=MANAGER_VERSION, files=len(selected), packages=[
        dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        for path in (linux, module)])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir), ensure_ascii=False, indent=2))
