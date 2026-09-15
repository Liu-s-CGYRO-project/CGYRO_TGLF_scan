"""Small, main-thread-only adapter to OMFIT's public saveas/load methods."""
from builtins import any, bool, dict, str, type
import copy
from datetime import datetime
from pathlib import Path
import threading
import uuid

from OMFITlib_template_archive import Project, TemplateError


class OMFITSession:
    def __init__(self, omfit):
        self.omfit = omfit

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
