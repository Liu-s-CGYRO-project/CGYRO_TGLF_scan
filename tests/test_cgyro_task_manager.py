"""Real Tk selection/filtering plus both independent confirmation boundaries."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'CGYRO_TGLF_scan/LIB'))
import test_cgyro_storage as fixture
import OMFITlib_cgyro_task_manager as manager
from OMFITlib_cgyro_task_cleanup import remove_tasks


def module_fixture():
    def record(token, job, server, state='failed'):
        return dict(manifest=dict(run_token=token, runid='Jet', case_id='nr=1__rho=0.33__ion=T',
                                  server=server, job_id=job, status=state))
    return dict(RUN_DB={}, RUN_HISTORY={'first': record('first', '123', 'tyadmin09'),
                                      'other': record('other', '123', 'login117'),
                                      'draft': record('draft', '', 'tyadmin09')})


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.owner = tk.Toplevel(self.root)
        self.owner.geometry('500x350+0+0')
        self.module = module_fixture()
        self.errors = []
        self.root.report_callback_exception = lambda kind, value, trace: self.errors.append(value)
        self.changed = Mock()
        def execute(tokens, expected, confirmation):
            return remove_tasks(self.module, tokens, expected, confirmation)
        self.delete = Mock(side_effect=execute)
        self.window = manager.TaskManager(self.owner, self.module, self.delete, on_changed=self.changed)
        self.root.update()
        self.info = patch.object(manager.messagebox, 'showinfo').start()
        self.error = patch.object(manager.messagebox, 'showerror').start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.assertEqual(self.errors, [])

    def choose(self, *tokens):
        self.window.table.selection_set(tokens)
        self.window.selection_changed()

    def test_empty_selection_never_opens_a_confirmation_and_filter_clears_hidden_selection(self):
        self.assertEqual(self.window.selected_tokens(), [])
        self.assertEqual(str(self.window.delete_button.cget('state')), 'disabled')
        with patch.object(manager, 'confirm_deletion') as confirmation:
            self.window.remove_selected()
        confirmation.assert_not_called()
        self.choose('first')
        self.window.query.set('login117')
        self.assertEqual(self.window.table.get_children(), ('other',))
        self.assertEqual(self.window.selected_tokens(), [])
        self.delete.assert_not_called()

    def test_sort_and_same_job_number_keep_full_task_identity(self):
        self.choose('first')
        self.window.sort_rows('server')
        self.window.sort_rows('server')
        self.assertEqual(self.window.selected_tokens(), ['first'])
        with patch.object(manager, 'review_scope', return_value=True), patch.object(
                manager.messagebox, 'askokcancel', return_value=True) as second:
            self.window.remove_selected()
        self.assertEqual(second.call_count, 1)
        self.assertEqual(second.call_args.kwargs['default'], 'cancel')
        self.assertNotIn('DELETE', second.call_args.args[1])
        self.assertNotIn('输入', second.call_args.args[1])
        self.assertEqual(self.delete.call_args.args, (['first'],))
        self.assertIn('other', self.module['RUN_HISTORY'])
        self.assertNotIn('first', self.module['RUN_HISTORY'])
        self.changed.assert_called_once()
        self.assertEqual(self.window.selected_tokens(), [])

    def test_first_cancel_and_second_cancel_or_close_do_not_delete(self):
        self.choose('draft')
        with patch.object(manager, 'review_scope', return_value=False), patch.object(
                manager.messagebox, 'askokcancel') as second:
            self.window.remove_selected()
            second.assert_not_called()
        for answer in (None, False):
            with self.subTest(answer=answer), patch.object(manager, 'review_scope', return_value=True), patch.object(
                    manager.messagebox, 'askokcancel', return_value=answer):
                self.window.remove_selected()
        self.delete.assert_not_called()
        self.assertIn('draft', self.module['RUN_HISTORY'])

    def test_modal_metadata_change_is_rejected_at_native_commit(self):
        self.choose('first')
        def change(*args, **kwargs):
            self.module['RUN_HISTORY']['first']['manifest']['job_id'] = '124'
            return True
        with patch.object(manager, 'review_scope', return_value=True), patch.object(
                manager.messagebox, 'askokcancel', side_effect=change):
            self.window.remove_selected()
        self.assertIn('first', self.module['RUN_HISTORY'])
        self.assertIn('已变化', self.error.call_args.args[1])
        self.changed.assert_not_called()

    def test_modal_selection_change_and_reentrant_click_cannot_widen_deletion(self):
        self.choose('first')
        def change(*args, **kwargs):
            self.window.remove_selected()  # Reentrant callbacks cannot enter another dialog.
            self.choose('other')
            return True
        with patch.object(manager, 'review_scope', side_effect=change), patch.object(
                manager.messagebox, 'askokcancel', return_value=True):
            self.window.remove_selected()
        self.delete.assert_not_called()
        self.assertIn('选择已变化', self.error.call_args.args[1])

    def test_select_visible_means_only_filtered_rows_and_refresh_clears_selection(self):
        self.window.query.set('tyadmin09')
        self.window.select_visible()
        self.assertEqual(self.window.selected_tokens(), ['draft', 'first'])
        self.window.refresh()
        self.assertEqual(self.window.selected_tokens(), [])

    def test_index_and_radius_are_visible_in_rows_and_full_preview(self):
        self.window.query.set('nr=1')
        self.assertEqual(len(self.window.table.get_children()), 3)
        row = self.window.rows['first']
        description = manager.task_description(row)
        self.assertIn('nr=1', description)
        self.assertIn('ρ=0.33', description)

    def test_workbench_uses_captured_owner_after_another_gui_changes_global_aux(self):
        import OMFITlib_workbench_cgyro_ui as page
        other = tk.Toplevel(self.root)
        view = page.CgyroPage()
        view.root = {'CGYRO_scan': self.module}
        view.ui = SimpleNamespace(_owner=self.owner, _aux={'parentGUI': other}, UpdateGUI=Mock())
        view.actions = SimpleNamespace(remove_cgyro_tasks=self.delete, factory=dict)
        with patch.object(page, 'TaskManager') as constructor:
            view.open_cgyro_task_manager()
        self.assertIs(constructor.call_args.args[0], self.owner)
        self.assertFalse(hasattr(other, '_cgyro_task_manager'))

    def test_task_window_survives_owner_child_refresh_and_closes_with_its_owner(self):
        ttk.Label(self.owner, text='old control').pack()
        for child in self.owner.winfo_children():
            child.destroy()  # Native GUI._clearKids uses this same ownership boundary.
        self.assertTrue(self.window.alive())
        self.owner.destroy()
        self.assertFalse(self.window.alive())

    def test_first_confirmation_has_scrollbar_and_pinned_buttons(self):
        def press_cancel():
            dialogs = [w for w in self.window.window.winfo_children() if isinstance(w, tk.Toplevel)]
            self.assertEqual(len(dialogs), 1)
            dialog = dialogs[0]
            text = next(w for w in dialog.winfo_children() if isinstance(w, tk.Text))
            self.assertIn('large task', text.get('1.0', 'end'))
            self.assertEqual(str(text.cget('state')), 'disabled')
            frame = next(w for w in dialog.winfo_children() if isinstance(w, ttk.Frame))
            button = next(w for w in frame.winfo_children() if str(w.cget('text')) == '取消')
            self.assertTrue(button.winfo_manager())
            button.invoke()
        self.root.after(30, press_cancel)
        self.assertFalse(manager.review_scope('Review', '\n'.join('large task ' + str(i) for i in range(1000)),
                                             parent=self.window.window))


if __name__ == '__main__':
    unittest.main()
