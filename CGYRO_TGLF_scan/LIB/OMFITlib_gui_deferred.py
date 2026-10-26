"""Build a selected tab in place without rerunning its owning OMFIT GUI."""
from builtins import dict, getattr, isinstance, str
import tkinter as tk
from tkinter import ttk
from OMFITlib_gui_context import alive, bind_actions, owner
from OMFITlib_gui_layout import finish_gui_subtree


def deferred_section(ui, render):
    """Capture native construction context while the GUI script is running."""
    aux, registry = getattr(ui, '_aux', None), getattr(ui, '_GUIs', None)
    if not isinstance(aux, dict) or not isinstance(registry, dict):
        return None  # Non-Tk hosts render the selected page directly.
    parent = aux.get('parentGUI', None)
    gui = owner(parent, registry)
    if gui is None:
        return None
    return DeferredSection(ui, parent, gui, render)


class DeferredSection:
    """One render per widget lifetime; ordinary data edits rebuild the owner.

    OMFIT's _aux and the owner's pythonFile are mutable construction globals.
    A later tab event can run after another module/CompoundGUI used them. Keep
    the original context so relative Entry locations and locks still belong
    to this project, and restore the other GUI even if rendering fails.
    """
    def __init__(self, ui, parent, gui, render):
        self.ui, self.parent, self.gui, self.render = ui, parent, gui, render
        self.context = dict(ui._aux)
        self.python_file = gui.pythonFile
        self.built = self.running = False
        self.pending = None
        parent.bind('<Destroy>', self._closed, add='+')

    def show(self):
        if (self.built or self.running or not alive(self.parent)
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
        self.running = True
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
            finish_gui_subtree(frame)
            frame.pack(side=tk.TOP, fill=tk.X)
            self.built = True
        finally:
            self.gui.pythonFile = previous_file
            aux.clear()
            aux.update(previous)
            self.running = False
            if not self.built:
                frame.destroy()

    def _retry(self):
        self.pending = None
        # Saving may outlive the user's visit to this tab. Keep hidden tabs
        # lazy rather than completing an obsolete selection after saving.
        notebook = self.parent.master
        if alive(self.parent) and notebook.select() == str(self.parent):
            self.show()

    def _closed(self, event):
        if event.widget is self.parent and self.pending is not None:
            self.parent.after_cancel(self.pending)
            self.pending = None
