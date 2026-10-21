"""Declarative workbench extension points; stable keys are saved in OMFIT.

Add pages/modules here, then implement their view and explicit action adapters.
Changing captions is safe; changing keys needs a saved-settings migration.
Definitions contain data only, never live widgets or callbacks.
"""
from builtins import dict, getattr, str
from collections import OrderedDict

MODULES = {
    'transfer': ('Transfer_tool',), 'cgyro': ('CGYRO_scan',),
    'tglf': ('TGLF_scan', 'TGLF'), 'tgyro': ('TGLF_scan', 'TGYRO'),
    'profiles': ('TGLF_scan', 'TGYRO', 'PROFILES_GEN'),
}
LABELS = {'transfer': '输入转换', 'cgyro': 'CGYRO', 'tglf': 'TGLF',
          'tgyro': 'TGYRO', 'profiles': 'PROFILES_GEN'}
PAGES = OrderedDict([
    ('1 项目概览', 'overview'), ('2 环境配置与记录', 'run'),
    ('3 输入准备与转换', 'transfer'), ('4 CGYRO 扫描', 'cgyro'),
    ('5 TGLF 扫描', 'tglf'), ('6 绘图与对比', 'plots'), ('7 模板与 GitHub', 'templates'),
])
STATUS = {'prepared': '输入已准备', 'submitted': '已提交', 'submitting': '正在提交', 'loaded': '结果已读取',
          'uploading': '上传输入中',
          'submission_unconfirmed': '提交状态待确认',
          'submitted_or_finished': '已提交或执行返回',
          'published': '结果已归档', 'complete': '完成', 'running': '运行中',
          'failed': '失败', 'cancelled': '已中止', 'partial': '部分完成',
          'cancel_requested': '取消中，待 Slurm 确认',
          'ready': '输入就绪', 'prepare_failed': '输入生成失败', 'preparing': '输入生成中',
          'returned': '脚本已返回', 'inputs_copied': '输入已复制', 'archived': '已保留旧数据'}
STATUS.update(dict(awaiting_choice='等待用户选择', accepted='使用传入输入', kept_current='保留当前输入', superseded='已有新候选'))

SCAN_TABS = OrderedDict([('input', '输入准备'), ('settings', '扫描设置'), ('run', '运行')])

# Hidden multi page is also reached by old saved navigation callbacks.
PAGE_RENDERERS = {key: 'render_' + key for key in PAGES.values()}
PAGE_RENDERERS['multi'] = 'render_multi'


def render_page(view, key):
    """Dispatch a registered page on the current facade; never evaluate code."""
    if key not in PAGE_RENDERERS:
        raise ValueError('Unknown workbench page: ' + str(key))
    return getattr(view, PAGE_RENDERERS[key])()
