"""Main-thread OMFIT operations, including updates to the existing module tree."""
from builtins import any, bool, dict, id, list, set, str, type
import copy
from datetime import datetime
from pathlib import Path
import threading
import uuid

from OMFITlib_template_archive import Project, TemplateError
from OMFITlib_template_live import LivePlan, MISSING, lookup


class OMFITSession:
    def __init__(self, omfit, tree_factory=None, gui_api=None):
        self.omfit = omfit
        self.tree_factory = tree_factory
        self.gui_api = gui_api

    def _live_state(self):
        state = getattr(self.omfit, '_template_live_state', None)
        if state is None:
            state = {'undo': None, 'history': [], 'storage': []}
            self.omfit._template_live_state = state
        return state

    def preview_live(self, prepared):
        self._main_thread()
        factory = self.tree_factory
        if factory is None:
            from omfit_classes.omfit_base import OMFITtree
            factory = OMFITtree
        plan = LivePlan(self.omfit, prepared, factory)
        plan.windows = []
        plan.closed_windows = set()
        return plan

    def _capture_live_windows(self, plan, undo=False):
        paths = plan.current_gui_paths()
        plan.windows = [item for item in plan.windows if undo and id(item[0]) in plan.closed_windows]
        for gui in list(getattr(self.gui_api, '_GUIs', {}).values()):
            path = paths.get(id(gui.pythonFile))
            if path:
                plan.windows.append((gui, path, gui.pythonFile))

    def _refresh_live(self, plan, restoring):
        # Rebind native GUI controllers to their replacement script nodes, then
        # redraw their existing TopLevels. The project and its module roots stay.
        for gui, path, previous in plan.windows:
            node = lookup(self.omfit, path)
            if not gui.top.winfo_exists():
                if restoring and id(gui) in plan.closed_windows and node is not MISSING:
                    node.run()
                continue
            if node is MISSING:
                self.gui_api._clearClosedGUI(gui.top)
                plan.closed_windows.add(id(gui))
                continue
            gui.pythonFile = node
            try:
                gui.update()
            except Exception:
                if not gui.top.winfo_exists():
                    plan.closed_windows.add(id(gui))
                raise
        parent = getattr(self.gui_api, 'OMFITaux', {}).get('rootGUI', None)
        if parent is not None:
            parent.event_generate('<<update_treeGUI>>')

    def apply_live(self, plan):
        self._main_thread()
        if plan.omfit is not self.omfit:
            raise TemplateError('当前 OMFIT 工程已改变，请重新预览')
        state = self._live_state()
        self._capture_live_windows(plan)
        plan.apply(self._refresh_live)
        state['storage'].append(plan.prepared)  # Keep backing files alive through save/undo.
        state['undo'] = plan
        record = dict(plan.report(), completed_at=datetime.now().isoformat(timespec='seconds'))
        state['history'].append(record)
        return record

    def can_undo_live(self):
        return bool(getattr(self.omfit, '_template_live_state', {}).get('undo', None))

    def undo_live(self):
        self._main_thread()
        state = self._live_state()
        plan = state['undo']
        if plan is None:
            raise TemplateError('没有可撤销的更新')
        self._capture_live_windows(plan, undo=True)
        plan.undo(self._refresh_live)
        state['undo'] = None
        state['history'].append(dict(action='undo', release=plan.prepared.release,
                                    completed_at=datetime.now().isoformat(timespec='seconds')))

    def live_history(self):
        self._main_thread()
        return list(self._live_state()['history'])

    def _main_thread(self):
        if threading.current_thread() is not threading.main_thread():
            raise TemplateError('OMFIT 工程操作必须在界面主线程执行')

    def project_path(self):
        path = str(getattr(self.omfit, 'filename', '') or '')
        return path if path.lower().endswith('.zip') else ''

    def manager_sources(self):
        """Locate only manager objects, even when OMFIT relocated their files."""
        self._main_thread()
        module = self.omfit['OMFITtemplates']
        sources = {}
        for branch, folder in (('LIB', 'LIB'), ('GUIS', 'GUIS'), ('TESTS', 'tests'), ('SOURCE', '')):
            for key, node in module.get(branch, {}).items():
                filename = str(getattr(node, 'filename', '') or '')
                if filename:
                    name = key if '.' in key else key + '.py'
                    relative = 'OMFITtemplates/' + (folder + '/' if folder else '') + name
                    sources[relative] = filename
        for key, name in (('SETTINGS', 'SettingsNamelist.txt'), ('help', 'help.rst')):
            node = module.get(key, None)
            filename = str(getattr(node, 'filename', '') or '')
            if filename:
                sources['OMFITtemplates/' + name] = filename
                if key == 'SETTINGS':
                    sources['OMFITtemplates/SettingsOMFIT.txt'] = filename
        return sources

    def replace_manager(self, module_dir):
        """Load only the manager; retain the old object until reopening succeeds."""
        self._main_thread()
        current = self.omfit['OMFITtemplates']
        new = type(current)(str(Path(module_dir) / 'OMFITsave.txt'), quiet=True, developerMode=False)
        if new['SETTINGS']['MODULE'].get('ID', '') != 'OMFITtemplates' or 'main' not in new.get('GUIS', {}):
            raise TemplateError('下载内容不是可运行的 OMFITtemplates 模块')
        def preserve(default, value):
            if hasattr(default, 'items') and hasattr(value, 'items'):
                result = copy.deepcopy(default)
                for key, item in value.items():
                    result[key] = preserve(result[key], item) if key in result else copy.deepcopy(item)
                return result
            return copy.deepcopy(value)
        for key, value in current.get('SETTINGS', {}).items():
            if key != 'MODULE':
                new['SETTINGS'][key] = preserve(new['SETTINGS'].get(key, {}), value)
        new.filename = ''
        self.omfit['OMFITtemplates'] = new
        return current

    def restore_manager(self, previous):
        self._main_thread()
        self.omfit['OMFITtemplates'] = previous

    def reopen_manager(self):
        self._main_thread()
        self.omfit['OMFITtemplates']['GUIS']['main'].run()

    def save_as(self, path):
        self._main_thread()
        destination = Path(path).expanduser().resolve()
        if destination.suffix.lower() != '.zip':
            raise TemplateError('OMFIT 工程快照需要使用 .zip 文件名')
        if destination.exists():
            raise TemplateError('快照目标已存在，请选择新文件名')
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.omfit.saveas(str(destination), zip=True, quiet=False, skip_save_errors=False)
        if not destination.is_file():
            raise TemplateError('OMFIT 未生成指定的工程 ZIP，请检查 OMFIT 保存日志')
        with Project(destination):
            pass
        return str(destination)

    def backup_and_open(self, path):
        self._main_thread()
        target = Path(path).expanduser().resolve()
        with Project(target) as project:
            if not any(row.keys == ('MainSettings',) for row in project.rows):
                raise TemplateError('打开需要完整 OMFIT 工程（包含 MainSettings），不能直接打开模板包')
        backup = target.with_name(target.stem + '__before_open_' + datetime.now().strftime('%Y%m%d_%H%M%S')
                                  + '_' + uuid.uuid4().hex[:8] + '.zip')
        self.save_as(backup)
        try:
            self.omfit.load(str(target))
        except Exception as exc:
            try:
                self.omfit.load(str(backup))
            except Exception:
                raise TemplateError('打开失败，自动恢复也未成功。请在 OMFIT 重新打开会话备份：' + str(backup)) from exc
            raise TemplateError('打开失败，已从会话备份恢复：' + str(backup)) from exc
        return str(backup)
