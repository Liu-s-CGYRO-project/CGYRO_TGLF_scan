"""Build a selected tab in place without rerunning its owning OMFIT GUI."""
from builtins import dict, getattr, isinstance, list, str
import tkinter as tk
from tkinter import ttk
from OMFITlib_gui_context import alive, bind_actions, owner
from OMFITlib_gui_layout import finish_gui_subtree
from OMFITlib_gui_api import _DeferredGUIRefresh


def deferred_section(ui, render, local=False, container=False, action=False):
    """Capture native context; optionally own a body and its action boundary.

    local scopes field edits. With local=True, action also scopes buttons
    whose effects span child tabs; nested fields keep the nearer local scope.
    container keeps persistent headers outside the replaceable page body.
    """
    aux, registry = getattr(ui, '_aux', None), getattr(ui, '_GUIs', None)
    if not isinstance(aux, dict) or not isinstance(registry, dict):
        return None  # Non-Tk hosts render the selected page directly.
    parent = aux.get('parentGUI', None)
    gui = owner(parent, registry)
    if gui is None:
        return None
    if container:
        parent = ttk.Frame(parent)
        parent.pack(side=tk.TOP, fill=tk.X)
    return DeferredSection(ui, parent, gui, render, local, action)


class _Changed:
    """Native updateGUI hook for an edit that needs no immediate redraw."""
    def __init__(self, section):
        self.section = section

    def __bool__(self):
        self.section.invalidate()
        return False


class DeferredSection:
    """Build on first visit; edits refresh only the affected visible section.

    OMFIT's _aux and the owner's pythonFile are mutable construction globals.
    A later tab event can run after another module/CompoundGUI used them. Keep
    the original context so relative Entry locations and locks still belong
    to this project, and restore the other GUI even if rendering fails.
    """
    def __init__(self, ui, parent, gui, render, local=False, action=False):
        self.ui, self.parent, self.gui, self.render = ui, parent, gui, render
        self.context = dict(ui._aux)
        self.python_file = gui.pythonFile
        self.built = self.running = False
        self.rebuild_requested = False
        self.pending = None
        self.frame = None
        self.revision = getattr(gui, '_cgyro_view_revision', 0)
        if local:
            self.refresh = _DeferredGUIRefresh(ui, gui, ui._GUIs, parent, self.redraw)
            self.refresh.invalidate_only = _Changed(self)
            parent._cgyro_local_refresh = self.refresh
            if action:
                parent._cgyro_action_refresh = self.refresh
        parent._cgyro_section = self
        parent.bind('<Destroy>', self._closed, add='+')

    def invalidate(self):
        # Only view state is cached, never results or validation decisions.
        # Mark other sections stale; keep our mounted ancestors so editing a
        # nested scan option cannot destroy its Notebook or sibling controls.
        revision = getattr(self.gui, '_cgyro_view_revision', 0) + 1
        self.gui._cgyro_view_revision = revision
        parent = self.parent
        while isinstance(parent, tk.Misc):
            section = getattr(parent, '_cgyro_section', None)
            if section is not None:
                section.revision = revision
            parent = parent.master

    def redraw(self):
        self.invalidate()
        self.built = False
        if self.parent.winfo_ismapped():
            self.show()

    def rebuild(self):
        """Replace only this body, retaining requests made during construction."""
        self.built = False
        if self.running:
            self.rebuild_requested = True
        else:
            self.show()

    def show(self):
        revision = getattr(self.gui, '_cgyro_view_revision', 0)
        if ((self.built and self.revision == revision) or self.running or not alive(self.parent)
                or self.ui._GUIs.get(str(self.gui.top), None) is not self.gui):
            return
        session = getattr(self.ui, 'OMFITaux', {}).get('GUI', None)
        if getattr(session, 'lockSave', False):
            if self.pending is None:
                self.pending = self.parent.after(100, self._retry)
            return
        # Build offscreen, exposing only a complete panel. Failed construction
        # leaves no partial controls; selecting the tab again can retry.
        frame = ttk.Frame(self.parent)
        self.running, self.built = True, False
        aux = self.ui._aux
        previous, previous_file = dict(aux), self.gui.pythonFile
        try:
            aux.update(self.context)
            aux.update(dict(parentGUI=frame, same_row=None, packing=tk.TOP, configure_size=[],
                       tab_list=dict(self.context.get('tab_list', {})),
                       open_tabs=dict(self.context.get('open_tabs', {}))))
            self.gui.pythonFile = self.python_file
            self.render()
            for widget, action in aux['configure_size']:
                widget.bind('<Configure>', lambda event, action=action: action(), add='+')
            bind_actions(frame, self.ui)
            if self.frame is not None:
                self.frame.destroy()
            self.frame = frame
            finish_gui_subtree(frame)
            frame.pack(side=tk.TOP, fill=tk.X)
            self.built = True
            self.revision = revision
        finally:
            self.gui.pythonFile = previous_file
            aux.clear()
            aux.update(previous)
            self.running = False
            if not self.built:
                frame.destroy()
            if self.rebuild_requested:
                self.rebuild_requested = False
                self.built = False
                if self.pending is None and alive(self.parent):
                    self.pending = self.parent.after(0, self._retry)

    def _retry(self):
        self.pending = None
        # Saving may outlive the user's visit to this tab. Keep hidden tabs
        # lazy rather than completing an obsolete selection after saving.
        if alive(self.parent) and self.parent.winfo_ismapped():
            self.show()

    def _closed(self, event):
        if event.widget is self.parent:
            if self.pending is not None:
                self.parent.after_cancel(self.pending)
                self.pending = None
            # Native GUI.update enumerates this registry before destroying its
            # children. A locally replaced nested Notebook must not survive in
            # that registry as a dead Tcl path.
            for key, notebook in list(self.gui.notebooks.items()):
                if not alive(notebook):
                    del self.gui.notebooks[key]


class TabPages:
    """Shared native Notebook plumbing; only the selected renderer runs.

    Saved state stores tab keys, not Tk objects. Native CompoundGUI still owns
    nested Notebook contexts. Call select() for programmatic navigation.
    """
    def __init__(self, ui, captions, state, key, render, local=True, action=False):
        self.state, self.key, self.keys = state, key, list(captions)
        self.sections, self.notebook = {}, None
        selected = state.get(key, self.keys[0])
        if selected not in self.keys:
            selected = self.keys[0]
        state[key] = selected
        for page, caption in captions.items():
            ui.Tab(caption)
            section = deferred_section(ui, lambda page=page: render(page), local=local, action=action)
            self.sections[page] = section
            if section is None:
                # Non-Tk renderers (export/inspection) retain their native
                # all-tabs contract; no widget or geometry work happens there.
                render(page)
            elif self.notebook is None:
                self.notebook = section.parent.master
        if self.notebook is not None:
            self.notebook.bind('<<NotebookTabChanged>>', self.changed, add='+')
            self.select(selected)

    def select(self, page):
        self.state[self.key] = page
        if self.notebook is not None and alive(self.notebook):
            self.notebook.select(self.keys.index(page))
            self.sections[page].show()

    def changed(self, event):
        if event.widget is self.notebook:
            page = self.keys[self.notebook.index(self.notebook.select())]
            self.state[self.key] = page
            self.sections[page].show()
