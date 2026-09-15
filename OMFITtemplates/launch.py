"""Launch the UI or use the same template engine from a terminal (Python 3.9+)."""
import argparse
import json
import os
from pathlib import Path
import platform
import sys

if sys.version_info < (3, 9):
    raise SystemExit('OMFIT 模板管理器需要 Python 3.9 或更新版本。')

sys.path.insert(0, str(Path(__file__).resolve().parent / 'LIB'))
from OMFITlib_template_archive import TemplateError, json_bytes, parse_json
from OMFITlib_template_paths import default_library
from OMFITlib_template_service import apply_update, inspect_project, list_library, plan_update, publish
from OMFITlib_template_github import DEFAULT_REPOSITORY, GitHub
from OMFITlib_template_proxy import DEFAULT_PROXY_HOST, DEFAULT_PROXY_PORT, manual_proxy


def gui_environment(check_only=False, project='', library=None):
    try:
        import tkinter as tk
    except ImportError as exc:
        raise TemplateError('所选 Python 缺少 Tk：{}。请为该解释器安装 tkinter；Ubuntu/Debian 系统 Python 可安装 python3-tk。'.format(sys.executable)) from exc
    try:
        if check_only:
            window = tk.Tk(className='OMFITtemplates')
            window.withdraw()
            try:
                return {'platform': platform.system(), 'python': platform.python_version(), 'executable': sys.executable,
                        'tk': window.tk.call('package', 'require', 'Tk'), 'display': os.environ.get('DISPLAY', ''),
                        'wayland_display': os.environ.get('WAYLAND_DISPLAY', ''),
                        'screen': [window.winfo_screenwidth(), window.winfo_screenheight()]}
            finally:
                window.destroy()
        from OMFITlib_template_ui import open_manager
        open_manager(project, library)
    except tk.TclError as exc:
        raise TemplateError('无法打开 Tk 桌面窗口。请在 Linux 桌面会话中运行，并确认 X11 / XWayland 显示可用；'
                            '当前 DISPLAY={!r}。原始错误：{}'.format(os.environ.get('DISPLAY', ''), exc)) from exc


def main():
    parser = argparse.ArgumentParser(description='OMFIT 模板管理器：不提供子命令时打开图形界面。')
    parser.add_argument('--library', default=None, help='模板库目录；图形界面默认恢复上次目录')
    parser.add_argument('--project', default='')
    parser.add_argument('--check', action='store_true', help='检查当前 Python、Tk 和 Linux 显示环境后退出')
    commands = parser.add_subparsers(dest='command')
    inspect = commands.add_parser('inspect', help='读取工程模块与内容体积')
    inspect.add_argument('source')
    commands.add_parser('list', help='列出本地库版本')
    for name, description in [('github-probe', '测试 GitHub HTTPS 与所选代理（不读取 GitHub 凭据）'),
                              ('github-check', '检查 GitHub 仓库和登录状态（只读）'),
                              ('github-list', '列出 GitHub 模板版本（只读）')]:
        command = commands.add_parser(name, help=description)
        command.add_argument('--repository', default=DEFAULT_REPOSITORY)
        command.add_argument('--anonymous', action='store_true', help='公开仓库检查，不读取本地凭据')
        command.add_argument('--network', choices=['manual', 'system', 'direct'], default='manual',
                             help='默认使用公共 HTTP 代理 47.102.120.146:18889')
        command.add_argument('--proxy-host', default=DEFAULT_PROXY_HOST)
        command.add_argument('--proxy-port', default=DEFAULT_PROXY_PORT)
    release = commands.add_parser('publish', help='发布不可覆盖的新版本')
    release.add_argument('source')
    for key in ('id', 'name', 'author', 'version'):
        release.add_argument('--' + key, required=True)
    release.add_argument('--description', default='')
    release.add_argument('--roots', nargs='+', required=True)
    release.add_argument('--examples', action='store_true')
    preview = commands.add_parser('plan', help='预览并导出变更清单')
    preview.add_argument('current')
    preview.add_argument('template')
    preview.add_argument('report')
    preview.add_argument('--data', choices=['keep', 'examples'], default='keep')
    preview.add_argument('--settings', choices=['keep', 'template'], default='keep')
    apply = commands.add_parser('apply', help='根据预览清单另存新工程')
    apply.add_argument('report')
    apply.add_argument('output')
    args = parser.parse_args()
    try:
        if args.check:
            print(json.dumps(gui_environment(check_only=True), ensure_ascii=False, indent=2))
            return
        if args.command is None:
            gui_environment(project=args.project, library=args.library)
            return
        args.library = args.library or str(default_library())
        if args.command == 'inspect':
            result = inspect_project(args.source)
        elif args.command == 'list':
            releases, errors = list_library(args.library)
            result = {'releases': [{k: r[k] for k in ('id', 'name', 'author', 'version', 'examples', 'path')} for r in releases], 'errors': errors}
        elif args.command in ('github-probe', 'github-check', 'github-list'):
            proxy = None if args.network == 'system' else ''
            if args.network == 'manual':
                proxy = manual_proxy(args.proxy_host, args.proxy_port)
            client = GitHub(args.repository, token='' if args.anonymous or args.command == 'github-probe' else None, proxy=proxy)
            result = client.probe() if args.command == 'github-probe' else (
                client.connect() if args.command == 'github-check' else client.list_releases())
        elif args.command == 'publish':
            result = publish(args.source, args.library, {k: getattr(args, k) for k in ('id', 'name', 'author', 'version', 'description')},
                             sorted(set(args.roots)), args.examples)
        elif args.command == 'plan':
            result = plan_update(args.current, args.template, args.data, args.settings)
            with open(args.report, 'xb') as stream:
                stream.write(json_bytes(result))
        else:
            result = apply_update(parse_json(Path(args.report).read_bytes()), args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (TemplateError, OSError, ValueError, KeyError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
