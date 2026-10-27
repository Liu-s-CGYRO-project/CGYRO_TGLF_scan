"""Native Tk editing, invalidation and lifetime contracts for lazy tab pages."""
from collections import Counter
import gc
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import weakref

import test_gui_refresh_native as native
from OMFITlib_gui_deferred import TabPages
from OMFITlib_gui_layout import finish_gui_layout
import OMFITlib_gui_layout as layout_module
import OMFITlib_gui_fonts as fonts
import OMFITlib_gui_api as widgets

SOURCE = native.SOURCE


class NativeTabsTests(unittest.TestCase):
    def setUp(self):
        source = patch.object(native, 'SOURCE', SOURCE)
        source.start()
        self.addCleanup(source.stop)
        self.host = native.NativeTkRefreshTests()
        self.addCleanup(self.host.doCleanups)
        font = patch.object(fonts, 'font_family', lambda *args, **kwargs: 'DejaVu Sans')
        font.start()
        self.addCleanup(font.stop)
        self.host.setUp()
        # A recording Mock retains destroyed widgets in its call history.
        # This lifetime test needs a non-recording font adapter.
        style = patch.object(widgets, 'style_widget', lambda *args, **kwargs: None)
        style.start()
        self.addCleanup(style.stop)
        self.addCleanup(self.host.tearDown)
        self.addCleanup(self.host.drain)
        native.native_definitions(SOURCE / 'omfit_classes/OMFITx.py',
            {'Tab', 'Label', '_Label', 'same_row', 'CompoundGUI'}, self.host.api.__dict__)
        self.counts = Counter()
        self.state = dict(page='edit')
        self.values = []
        self.render_fails = False

    def build(self):
        def page(key):
            self.counts[key] += 1
            if key == 'edit':
                self.combo = self.ui.ComboBox("root['mode']", ['spectra', 'ballooning'], updateGUI=True)
                self.entry = self.ui.Entry("root['number']", updateGUI=False)
            else:
                self.values.append(self.host.tree['number'])
                self.ui.Label(str(self.host.tree['number']))
            if self.render_fails:
                raise ValueError('synthetic render failure')
        def render(ui):
            self.ui = ui
            self.header = ui.Label('Header')
            self.pages = TabPages(ui, dict(edit='Edit', run='Run'), self.state, 'page', page)
            ui.Tab('')
            self.footer = ui.Button('Action', lambda: None, updateGUI=True)
            finish_gui_layout(self.header, ui)
        self.host.render(render)

    def select(self, page):
        self.pages.select(page)
        self.host.root.update()
        self.host.drain()

    def commit(self, text):
        self.entry.delete(0, 'end')
        self.entry.insert(0, text)
        self.entry.bind('<<TestCommit>>', self.entry.bind('<Return>'))
        self.entry.event_generate('<<TestCommit>>')
        self.host.drain()

    def test_hidden_tabs_are_lazy_and_switch_preserves_uncommitted_text(self):
        self.build()
        self.assertEqual(self.counts, dict(edit=1))
        entry = self.entry
        entry.delete(0, 'end')
        entry.insert(0, '123')
        for page in ('run', 'edit', 'run', 'edit'):
            self.select(page)
        self.assertEqual(self.counts, dict(edit=1, run=1))
        self.assertIs(self.entry, entry)
        self.assertEqual(entry.get(), '123')
        self.assertEqual(self.host.updates, [])

    def test_committed_no_redraw_entry_invalidates_previous_run_preview(self):
        self.build()
        self.select('run')
        self.select('edit')
        entry, header = self.entry, self.header
        self.commit('39')
        self.assertEqual(self.host.tree['number'], 39)
        self.assertIs(self.entry, entry)
        self.assertEqual(self.counts, dict(edit=1, run=1))
        self.select('run')
        self.assertEqual(self.values, [12.0, 39])
        self.assertEqual(self.counts, dict(edit=1, run=2))
        self.assertIs(self.header, header)
        self.assertEqual(self.host.updates, [])

    def test_combo_only_rebuilds_edit_section_and_layout_does_not_accumulate(self):
        self.build()
        header, footer, notebook = self.header, self.footer, self.pages.notebook
        layout = header.master.master._cgyro_gui_layout
        old_entry = weakref.ref(self.entry)
        for index in range(12):
            self.combo.set('ballooning' if index % 2 == 0 else 'spectra')
            self.combo.event_generate('<<ComboboxSelected>>')
            self.host.drain(3)
        self.assertEqual(self.counts, dict(edit=13))
        self.assertIs(self.header, header)
        self.assertIs(self.footer, footer)
        self.assertIs(self.pages.notebook, notebook)
        self.assertEqual(self.host.updates, [])
        self.assertTrue(all(w.winfo_exists() for w in layout.labels + layout.panels + layout.notebooks))
        gc.collect()
        self.assertIsNone(old_entry())
        self.assertLess(len(layout.panels), 15)
        self.assertLess(len(self.host.root.tk.call('after', 'info')), 6)

    def test_action_still_rebuilds_owner_header_and_remembers_selected_tab(self):
        self.build()
        self.select('run')
        old = self.header
        self.host.invoke(self.footer.invoke)
        self.host.drain()
        self.assertEqual(self.host.updates, [('owner', False)])
        self.assertFalse(old.winfo_exists())
        self.assertEqual(self.state['page'], 'run')
        self.assertEqual(self.pages.notebook.index('current'), 1)

    def test_full_redraw_does_not_use_layout_left_on_persistent_content(self):
        self.build()
        content, anchor = self.header.master.master, self.header
        # Native GUI.update destroys the children but keeps this frame
        # and its Python attributes, including an older layout object.
        # Do not supply prune: pre-1.24.23 objects have no such method.
        legacy = SimpleNamespace(anchor=anchor, _cancel_scroll=lambda: None)
        content._cgyro_gui_layout = legacy
        self.host.owner.update()
        self.host.root.update()
        self.assertFalse(anchor.winfo_exists())
        self.assertIs(self.header.master.master, content)
        self.assertIsNot(content._cgyro_gui_layout, legacy)
        self.assertIs(content._cgyro_gui_layout.anchor, self.header)
        self.assertTrue(self.entry.winfo_exists())

    def test_mounted_legacy_layout_accepts_subtree_without_new_instance_methods(self):
        self.build()
        content, anchor = self.header.master.master, self.header
        child = native.ttk.Frame(content)
        child.pack()
        dead = native.ttk.Label(child, text='retired')
        dead.destroy()
        calls = []
        legacy = SimpleNamespace(anchor=anchor,
            _walk=lambda frame: calls.append(('walk', frame)),
            reflow=lambda: calls.append(('reflow',)),
            _queue_scroll=lambda: calls.append(('queue',)))
        for key in ('labels', 'notebooks', 'panels', 'reset_help_buttons', 'reset_help_spacers'):
            setattr(legacy, key, [dead, anchor])
        for key in ('rows', 'inline_rows', 'forms'):
            setattr(legacy, key, [(dead, []), (anchor, [])])
        current = content._cgyro_gui_layout
        content._cgyro_gui_layout = legacy
        try:
            layout_module.finish_gui_subtree(child)
            self.assertEqual(calls, [('walk', child), ('reflow',), ('queue',)])
            self.assertEqual(legacy.labels, [anchor])
            self.assertEqual(legacy.rows, [(anchor, [])])
        finally:
            content._cgyro_gui_layout = current
            child.destroy()

    def test_failed_replacement_retains_prior_panel_and_retry_has_no_duplicates(self):
        self.build()
        self.select('run')
        section = self.pages.sections['run']
        old_frame = section.frame
        section.invalidate()
        section.built = False
        self.render_fails = True
        with self.assertRaisesRegex(ValueError, 'synthetic'):
            section.show()
        self.assertTrue(old_frame.winfo_exists())
        self.assertEqual(len(section.parent.winfo_children()), 1)
        self.render_fails = False
        section.show()
        self.assertFalse(old_frame.winfo_exists())
        self.assertEqual(len(section.parent.winfo_children()), 1)

    def test_scope_refresh_waits_for_save_and_closing_cancels_timer(self):
        self.build()
        section = self.pages.sections['edit']
        self.host.api.OMFITaux['GUI'].lockSave = True
        self.combo.set('ballooning')
        self.combo.event_generate('<<ComboboxSelected>>')
        self.host.drain()
        self.assertEqual(self.counts, dict(edit=1))
        self.assertIsNotNone(section.refresh.pending)
        self.host.owner.top.destroy()
        self.assertIsNone(section.refresh.pending)
        self.host.drain(130)

    def test_nested_compound_edit_retains_outer_tabs_and_full_refresh_has_no_dead_books(self):
        class Script:
            def __run__(script, **kwargs):
                self.nested = TabPages(self.ui, dict(edit='Edit', run='Run'),
                    self.state, 'nested', child)
        module = ModuleType('omfit_classes.omfit_python')
        module.OMFITpythonGUI = Script
        patcher = patch.dict(sys.modules, {'omfit_classes.omfit_python': module})
        patcher.start()
        self.addCleanup(patcher.stop)
        def child(key):
            self.counts[key] += 1
            self.combo = self.ui.ComboBox("root['mode']", ['spectra', 'ballooning'], updateGUI=True)
        def outer(key):
            if key == 'edit':
                self.ui.CompoundGUI(Script(), title='')
            else:
                self.ui.Label('Other')
        def render(ui):
            self.ui = ui
            self.header = ui.Label('Header')
            self.pages = TabPages(ui, dict(edit='Scan', other='Other'), self.state, 'page', outer)
            ui.Tab('')
            self.footer = ui.Button('Action', lambda: None, updateGUI=True)
            finish_gui_layout(self.header, ui)
        self.host.render(render)
        original = self.pages.notebook
        self.combo.set('ballooning')
        self.combo.event_generate('<<ComboboxSelected>>')
        self.host.drain()
        self.assertIs(self.pages.notebook, original)
        self.assertEqual(self.counts, dict(edit=2))
        self.pages.select('other')
        self.pages.sections['other'].invalidate()
        self.pages.select('edit')
        self.host.root.update()
        self.assertTrue(all(w.winfo_exists() for w in self.host.owner.notebooks.values()))
        self.host.invoke(self.footer.invoke)
        self.host.drain()
        self.assertEqual(self.host.updates, [('owner', False)])


if __name__ == '__main__':
    unittest.main()
