"""Open the template library using OMFIT's existing Tk session."""
from OMFITlib_tk_callbacks import begin_view_open, native_version_notice
native_open = begin_view_open(OMFITx)
from OMFITlib_template_ui import open_manager
from OMFITlib_template_session import OMFITSession

manager = open_manager(session=OMFITSession(OMFIT, gui_api=OMFITx))
manager.native_version = str(OMFITx.__dict__.get('repo_str', '') or '未提供版本标识')
manager.show_startup_notice(native_version_notice(OMFITx))
if native_open is not None:
    manager.native_open_events = native_open

# Native OMFIT closes a newly created GUI when it has no controls. A legacy
# entry already on screen needs the same cleanup after its redraw completes.
entry_gui = OMFITx._GUIs.get(str(OMFITx._aux.get('topGUI', '')))
if entry_gui is not None:
    def close_empty_entry(gui=entry_gui, gui_api=OMFITx):
        if gui.top.winfo_exists() and not gui.parentGUI.winfo_children():
            gui_api._clearClosedGUI(gui.top)
    manager.window._root().after(0, close_empty_entry)
