"""Open the template library using OMFIT's existing Tk session."""
from OMFITlib_template_ui import open_manager
from OMFITlib_template_session import OMFITSession

OMFITx.TitleGUI('OMFIT 模板管理')
OMFITx.Label('连接 GitHub，选择模板版本；更新时可保留当前案例与结果。', align='left')
OMFITx.Button('打开 GitHub 模板管理', lambda: open_manager(session=OMFITSession(OMFIT, gui_api=OMFITx)))
open_manager(session=OMFITSession(OMFIT, gui_api=OMFITx))
