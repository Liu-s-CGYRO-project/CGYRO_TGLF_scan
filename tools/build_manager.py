"""Build independent Linux and native OMFIT manager packages from registered files."""
import argparse
import hashlib
import gzip
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import zipfile
from omfit_help import validate_module_help, validate_module_settings

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'OMFITtemplates'
sys.path.insert(0, str(MODULE / 'LIB'))
from OMFITlib_template_archive import json_bytes, parse_json, parse_tree, tree_bytes
from OMFITlib_template_manager_update import package_names
from OMFITlib_template_service import new_file
from OMFITlib_template_versions import MANAGER_VERSION
from OMFITlib_template_incremental import FORMAT, _verify_tree, manifest_name, validate_manifest

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

## 下载进度

连接与校验阶段显示活动进度，下载阶段按实际字节显示百分比及已下载 / 总大小。
小模板也按网络块更新；完成后填满，取消或失败时停止动画。

## 模板更新

在 OMFIT 内打开：预览后点击“更新当前工程”，直接修改当前内存中的模块并刷新现有界面。
案例、结果和用户设置按所选策略保留，不需要保存中间 ZIP 或重新加载工程；照常保存即可。
支持“撤销本次更新”。外部独立管理器保持生成新工程 ZIP 的流程。

## 自动连接与更新检查

启动后自动连接上次 GitHub 仓库，并独立后台检查管理器更新。
当前版本及检查结果显示在标题下方；安装仍由用户选择。保留手动重试入口。
选择本地或共享模板库后记住选择，离线时仍可使用已下载的模板。

## 排序和独立更新

版本列表默认按实际发布时间从新到旧排列，搜索框右侧可切换版本号排序。
版本页可通过“作者”下拉框筛选，再组合关键词搜索与版本排序。
空列表提示分行显示，中文回退字体和说明行距适配 Linux 桌面。
数字版本按数值比较（1.10.0 在 1.9.0 前），旧日期版本保留在历史序列中。
右上角“检查管理器更新”显示当前和最新稳定版本，使用当前代理配置。
更新源固定为 Liu-s-CGYRO-project/CGYRO_TGLF_scan 的独立管理器 Release。
优先显示文件级增量更新：比较本地 SHA-256，只下载变更文件，在界面内安装并重新打开。
OMFIT 内只替换管理器模块；正常保存工程以保留更新。Linux 原启动入口会自动进入新版。
1.10.1 修复增量安装的版本不匹配提示，旧版可直接在界面内安装修复。
取消或校验失败保留当前版本；完整安装包下载继续作为兼容入口。
1.6.0 及更早版本需先完整安装一次 1.7.0，之后可使用增量流程。
原安装目录保留，运行 bash start_manager.sh --no-update-redirect 可返回原目录版本。
计算工程继续通过“更新 / 切换”页预览和生成新工程。

默认公共 GitHub 代理使用“手动 HTTP 代理”，主机 47.102.120.146，端口 18889，用户名和密码留空。
已移除 SSH 隧道与脚本入口，旧 SSH 配置自动迁移到公共代理。
点击“登录 GitHub”时自动检测 gh，缺少时下载官方 Linux 包，校验后安装到用户目录并打开登录。
无需 sudo 或配置 PATH，进度在窗口底部显示，可取消。
路径标签、下拉框、按钮与表格按字体尺寸布局，较窄窗口自动换行。
窗口标题为 OMFIT Template Manager，版本及检查结果显示在标题下方。
未登录时整个发布页置灰；授权完成后自动读取 GitHub 登录名，作者 ID 只读。
账号切换或登录失效后清除旧发布准备信息。
公开版本检查与下载不需要 GitHub 登录；私有仓库和发布仍使用各自的 GitHub 账号。
'''


def build(directory):
    directory = Path(directory).expanduser().resolve()
    validate_module_help((MODULE / 'help.rst').read_bytes(), 'OMFITtemplates/help.rst')
    validate_module_settings((MODULE / 'SettingsNamelist.txt').read_bytes(), 'OMFITtemplates/SettingsNamelist.txt')
    selected = {'OMFITsave.txt', 'SettingsNamelist.txt', 'help.rst'}
    for row in parse_tree((MODULE / 'OMFITsave.txt').read_bytes()):
        if row.ref:
            path = (MODULE / row.ref).resolve()
            if MODULE.resolve() not in path.parents or not path.is_file() or path.is_symlink():
                raise ValueError('Invalid manager reference: ' + row.ref)
            selected.add(path.relative_to(MODULE).as_posix())
    payload = {'OMFITtemplates/' + name: (MODULE / name).read_bytes().replace(b'\r\n', b'\n')
               for name in sorted(selected)}
    # Existing v1 installers require MODULE.version at this exact path. Keep
    # their descriptor, but point native OMFIT at clean settings so it never
    # sees the legacy version field and never rewrites help.rst.
    native_settings = 'OMFITtemplates/SettingsOMFIT.txt'
    legacy_settings = 'OMFITtemplates/SettingsNamelist.txt'
    payload[native_settings] = payload[legacy_settings]
    descriptor = parse_json(payload[legacy_settings])
    descriptor['MODULE']['version'] = MANAGER_VERSION
    payload[legacy_settings] = json_bytes(descriptor)
    rows = parse_tree(payload['OMFITtemplates/OMFITsave.txt'])
    settings_rows = [row for row in rows if row.keys == ('SETTINGS',) and row.kind == 'OMFITsettings']
    if len(settings_rows) != 1 or settings_rows[0].ref != 'SettingsNamelist.txt':
        raise ValueError('Manager settings registration changed; review updater compatibility')
    settings_rows[0].fields[2] = './SettingsOMFIT.txt'
    payload['OMFITtemplates/OMFITsave.txt'] = tree_bytes(rows)
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
    incremental = directory / 'incremental'
    incremental.mkdir(parents=True, exist_ok=True)
    manifest = dict(format=FORMAT, version=MANAGER_VERSION, files={})
    for name, data in sorted(payload.items()):
        digest = hashlib.sha256(data).hexdigest()
        asset = 'omfit-file-' + digest + '.gz'
        manifest['files'][name] = dict(size=len(data), sha256=digest, asset=asset,
                                      mode=0o755 if name.endswith('.sh') else 0o644)
        destination = incremental / asset
        if not destination.exists():
            with new_file(destination) as temporary:
                temporary.write_bytes(gzip.compress(data, mtime=0))
    validate_manifest(manifest, MANAGER_VERSION)
    # Validate the actual artifact metadata/registered tree, not just the
    # manifest syntax. These are static file checks; no GUI or code execution.
    with tempfile.TemporaryDirectory(prefix='.verify-manager-', dir=directory) as temporary:
        stage = Path(temporary)
        for name, data in payload.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        _verify_tree(stage, manifest)
    legacy_identity = parse_json(payload[legacy_settings])['MODULE']
    if legacy_identity.get('ID') != 'OMFITtemplates' or legacy_identity.get('version') != MANAGER_VERSION:
        raise ValueError('Old manager installers would reject the package descriptor')
    validate_module_settings(payload[native_settings], native_settings)
    registered = parse_tree(payload['OMFITtemplates/OMFITsave.txt'])
    if any(row.ref == 'SettingsNamelist.txt' for row in registered):
        raise ValueError('Legacy update descriptor must not be loaded by OMFIT')
    with new_file(incremental / manifest_name(MANAGER_VERSION)) as temporary:
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return dict(version=MANAGER_VERSION, files=sum(name.startswith('OMFITtemplates/') for name in payload),
        incremental=str(incremental), legacy_installer_descriptor_checked=True, native_settings_checked=True, packages=[
        dict(path=str(path), bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        for path in (linux, module)])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    print(json.dumps(build(args.output_dir), ensure_ascii=False, indent=2))
