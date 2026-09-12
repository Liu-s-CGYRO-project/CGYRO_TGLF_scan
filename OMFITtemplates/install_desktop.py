#!/usr/bin/env python3
"""Register this directory in the Linux application menu without system writes.

Exec argument escaping follows the freedesktop Desktop Entry specification.
The chosen interpreter is recorded so launching does not depend on .bashrc.
"""
import argparse
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / 'LIB'))
from OMFITlib_template_paths import APP_ID, applications_directory

MARKER = 'X-OMFIT-Template-Manager=true'


def desktop_string(value):
    value = str(value)
    if any(ord(character) < 32 for character in value):
        raise ValueError('桌面入口路径不能含换行或控制字符')
    return value.replace('\\', '\\\\').replace(' ', '\\s')


def exec_argument(value):
    value = str(value)
    if any(ord(character) < 32 for character in value):
        raise ValueError('启动参数不能含换行或控制字符')
    # First quote an Exec argument, then escape backslashes for desktop strings.
    quoted = ''.join('\\' + c if c in '\\"`$' else c for c in value)
    return '"' + quoted.replace('\\', '\\\\').replace('%', '%%') + '"'


def desktop_contents(module, interpreter, library=None):
    module = Path(module).resolve()
    interpreter = Path(interpreter).resolve()
    if '=' in str(interpreter):
        raise ValueError('桌面入口的 Python 可执行文件路径不能包含等号')
    if not (module / 'launch.py').is_file() or not (module / 'omfit-templates.svg').is_file():
        raise ValueError('安装目录缺少 launch.py 或图标文件')
    command = [str(interpreter), str(module / 'launch.py')]
    if library is not None:
        command.extend(['--library', str(Path(library).expanduser().resolve())])
    return '\n'.join([
        '[Desktop Entry]', 'Version=1.0', 'Type=Application', 'Name=OMFIT Template Manager',
        'Name[zh_CN]=OMFIT 模板管理器', 'Comment=Manage OMFIT project templates and versions',
        'Comment[zh_CN]=分发代码与设置，保留当前结果或切换示例',
        'Exec=' + ' '.join(exec_argument(arg) for arg in command),
        'Icon=' + desktop_string(module / 'omfit-templates.svg'),
        'Terminal=false', 'Categories=Science;', 'Keywords=OMFIT;CGYRO;TGLF;templates;',
        'StartupNotify=false', 'StartupWMClass=OMFITtemplates', MARKER, '',
    ])


def install(module, interpreter, destination_dir=None, library=None, uninstall=False):
    directory = Path(destination_dir).expanduser().resolve() if destination_dir is not None else applications_directory()
    destination = directory / (APP_ID + '.desktop')
    if destination.is_symlink():
        raise ValueError('桌面入口路径是符号链接，未修改：' + str(destination))
    if destination.exists() and MARKER not in destination.read_text(encoding='utf-8').splitlines():
        raise ValueError('已有同名入口不属于本工具，未修改：' + str(destination))
    if uninstall:
        if destination.exists():
            destination.unlink()
        return destination
    contents = desktop_contents(module, interpreter, library)
    directory.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', dir=directory,
                                         prefix='.omfit-desktop-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return destination


def main():
    parser = argparse.ArgumentParser(description='安装／移除当前用户的 OMFIT 模板管理器菜单入口，无需 sudo。')
    parser.add_argument('--applications-dir', help='覆盖应用菜单目录，默认遵循 XDG_DATA_HOME')
    parser.add_argument('--library', help='可选：桌面启动时固定使用的模板库路径')
    parser.add_argument('--uninstall', action='store_true', help='只移除菜单入口，不删除软件或模板库')
    args = parser.parse_args()
    if not sys.platform.startswith('linux'):
        parser.exit(1, '此安装器用于 Linux 桌面。\n')
    try:
        result = install(Path(__file__).resolve().parent, sys.executable, args.applications_dir, args.library, args.uninstall)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')
    print(('已移除菜单入口：' if args.uninstall else '已安装菜单入口：') + str(result))
    if not args.uninstall:
        print('应用菜单名称：OMFIT 模板管理器。请保留当前软件目录的位置；移动后重新运行安装器。')


if __name__ == '__main__':
    main()
