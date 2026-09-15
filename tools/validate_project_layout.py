"""Render workflow menu, common environment and localized Transfer with native Tk controls."""
import argparse
import ast
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

from validate_compare_layout import NativeWidgets, screenshot
from validate_native_execution import NativeHost, REPO
sys.path.insert(0, str(REPO / 'tests'))
from test_project import fixture


class ProjectWidgets(NativeWidgets):
    compound = False

    def TitleGUI(self, title):
        if not self.compound:
            super().TitleGUI(title)

    def CompoundGUI(self, task, title=''):
        # The actual Transfer source runs; only the native compound host is an adapter.
        assert self.page == 'transfer'
        parent, original_root = self.aux['parentGUI'], self.namespace['root']
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        self.aux['parentGUI'] = frame
        self.namespace['root'] = original_root['Transfer_tool']
        self.namespace['scratch'] = {}
        self.compound = True
        try:
            source = (REPO / 'CGYRO_TGLF_scan/Transfer_tool/GUIS/transfer.py').read_text(encoding='utf-8')
            exec(compile(source, '<Transfer GUI>', 'exec'), dict(root=self.namespace['root'], scratch=self.namespace['scratch'], OMFITx=self))
        finally:
            self.aux['parentGUI'], self.namespace['root'], self.compound = parent, original_root, False


def validate(source, output):
    output.mkdir(parents=True, exist_ok=True)
    host = NativeHost(source)
    checks = []
    for size in (11, 14):
        for page in ('overview', 'run', 'transfer'):
            window = tk.Tk()
            window.geometry('1100x850')
            try:
                root = fixture()
                root['LIB'] = host.modules[('CGYRO_TGLF_scan',)]['LIB']
                root['CGYRO_scan']['SETTINGS']['REMOTE_SETUP'].update(serverPicker='cluster', server='user@cluster',
                    workDir='/work/user/OMFITtmp/project/cgyro', cluster=dict(scheduler='slurm', queue='normal',
                    w='24:00:00', environment='source /shared/gacode/shared/bin/gacode_setup', executable='cgyro -e . -n 16'))
                ui = ProjectWidgets(source, root, window, size)
                ui.page = page
                ns = ui.namespace
                controller = SimpleNamespace(top=window, parentGUI=ui.body, notebooks={}, locked=[])
                ns['_GUIs'][str(window)] = controller
                native = Path(source) / 'omfit_classes/OMFITx.py'
                node = next(n for n in ast.parse(native.read_text(encoding='utf-8')).body if isinstance(n, ast.FunctionDef) and n.name == 'FilePicker')
                node.decorator_list = []
                exec(compile(ast.Module(body=[node], type_ignores=[]), str(native), 'exec'), ns)
                with patch.dict(sys.modules, {'utils_widgets': ui.helpers}):
                    host.execute('from OMFITlib_project import ProjectActions\nfrom OMFITlib_project_ui import ProjectUI\n'
                        'actions=ProjectActions(root)\nactions.settings["page"]=' + repr(page) + '\n'
                        'ProjectUI(actions,OMFITx,servers=["cluster"]).render()', root, OMFITx=ui)
                    ui.settle()
                    controls = ui.check_geometry(check_footer=False)
                    menu = next(result for tab, kind, args, result in ui.events if kind == 'ComboBox' and args[0].endswith("['page']"))
                    labels = list(menu.cget('values'))
                    assert [label.split()[0] for label in labels] == [str(i) for i in range(1, 10)], labels
                    if page == 'transfer':
                        buttons = []
                        def walk(widget):
                            for child in widget.winfo_children():
                                if child.winfo_class() == 'TButton':
                                    buttons.append(child.cget('text'))
                                walk(child)
                        walk(ui.body)
                        assert '数据树' in buttons and '文件' in buttons
                        assert 'Tree' not in buttons and 'File' not in buttons
                    if size == 14:
                        screenshot(window, output / (page + '-zh.png'))
                    checks.append(dict(page=page, font_size=size, controls=controls, menu_order=labels))
            finally:
                window.destroy()
    report = dict(viewports=checks, native_filepicker=True, no_control_overlap=True, full_server_session=False)
    (output / 'project-layout.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Project layout checks:', len(checks), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    validate(args.source, args.output)
