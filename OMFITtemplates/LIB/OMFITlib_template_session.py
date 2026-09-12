"""Small, main-thread-only adapter to OMFIT's public saveas/load methods."""
from builtins import any, bool, str
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
