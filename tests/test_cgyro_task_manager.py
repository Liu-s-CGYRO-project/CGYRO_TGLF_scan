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

    def test_filter_reuses_display_rows_and_never_reloads_task_catalog(self):
        table = self.window.table
        with patch.object(manager, 'task_catalog', side_effect=AssertionError('catalog reread')), patch.object(
                manager, 'task_case_caption', side_effect=AssertionError('caption rebuilt')), patch.object(
                table, 'insert', side_effect=AssertionError('row recreated')), patch.object(
                table, 'delete', side_effect=AssertionError('row deleted')):
            self.choose('first')
            self.window.query.set('login117')
            self.assertEqual(table.get_children(), ('other',))
            self.assertTrue(table.exists('first'))  # Detached, not recreated.
            self.assertEqual(self.window.selected_tokens(), [])
            self.window.query.set('tyadmin09')
            self.window.select_visible()
            self.assertEqual(self.window.selected_tokens(), ['draft', 'first'])
            self.window.query.set('')
            self.assertEqual(set(table.get_children()), {'draft', 'first', 'other'})
            self.assertEqual(self.window.selected_tokens(), [])
        # Explicit refresh must also remove hidden stale rows, not leave tokens
        # that collide when the same task is later inserted again.
        self.window.query.set('login117')
        self.window.refresh()
        self.window.query.set('')
        self.assertEqual(set(table.get_children()), {'draft', 'first', 'other'})

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

    def test_task_dialog_deletion_keeps_page_refresh_captured_at_button_creation(self):
        import OMFITlib_workbench_cgyro_ui as page
        buttons, changed = {}, Mock()
        view = page.CgyroPage()
        view.root, view.settings = {'CGYRO_scan': self.module}, {}
        view.ui = SimpleNamespace(_owner=self.owner, _aux={'parentGUI': self.owner},
            refresh_callback=Mock(return_value=changed), UpdateGUI=Mock(),
            Button=lambda title, command, **kw: buttons.setdefault(title, (command, kw)))
        view.actions = SimpleNamespace(remove_cgyro_tasks=self.delete, factory=dict)
        view.render_cgyro_cleanup(self.module)
        view.ui.refresh_callback.assert_called_once_with(scope='page')
        self.assertEqual(buttons['删除指定半径…'][1]['refresh_scope'], 'section')
        view.ui._aux['parentGUI'] = tk.Toplevel(self.root)
        with patch.object(page, 'TaskManager') as constructor:
            buttons['任务管理 / 删除任务…'][0]()
        self.assertIs(constructor.call_args.kwargs['on_changed'], changed)
        constructor.call_args.kwargs['on_changed']()
        changed.assert_called_once()
        replacement = Mock()
        view.open_cgyro_task_manager(replacement)
        self.assertIs(self.owner._cgyro_task_manager.on_changed, replacement)
        view.ui.UpdateGUI.assert_not_called()

    def test_runtime_apply_uses_captured_page_refresh_on_success_and_failure(self):
        from OMFITlib_workbench_runtime_ui import RuntimePage
        view, refreshed = RuntimePage(), Mock()
        label, button = ttk.Label(self.owner), ttk.Button(self.owner)
        view.ui = SimpleNamespace(UpdateGUI=Mock())
        view.actions = SimpleNamespace(apply_runtime=Mock(return_value='applied'), report_error=Mock())
        self.assertEqual(view.apply_runtime_button(label, button, refreshed), 'applied')
        refreshed.assert_called_once()
        refreshed.reset_mock()
        view.actions.apply_runtime.side_effect = ValueError('installation changed')
        with self.assertRaisesRegex(ValueError, 'installation changed'):
            view.apply_runtime_button(label, button, refreshed)
        refreshed.assert_called_once()
        view.actions.report_error.assert_called_once()
        view.ui.UpdateGUI.assert_not_called()

    def test_legend_save_refreshes_originating_comparison_section(self):
        import OMFITlib_compare_widgets as comparison
        buttons, refreshed = {}, Mock()
        ui = SimpleNamespace(refresh_callback=Mock(return_value=refreshed), UpdateGUI=Mock(),
            ComboBox=Mock(), Entry=Mock(), Label=Mock(),
            Button=lambda title, command, **kw: buttons.setdefault(title, command))
        view = comparison.ComparisonWidgets({}, ui)
        state = dict(legend_order_mode='Manual order', legend_order_text='T,D')
        view._render_legend_order_controls(lambda key: key, state)
        ui.refresh_callback.assert_called_once_with(scope='section')
        ui.refresh_callback.side_effect = AssertionError('Dialog must not discover a new scope')

        def save_dialog():
            dialog = next(w for w in self.root.winfo_children()
                          if isinstance(w, tk.Toplevel) and w.title() == '图例顺序')
            box = next(w for w in dialog.winfo_children() if isinstance(w, tk.Listbox))
            box.delete(0, tk.END)
            box.insert(tk.END, 'D', 'T')
            footer = dialog.winfo_children()[-1]
            next(w for w in footer.winfo_children() if w.cget('text') == '保存').invoke()

        self.root.after(30, save_dialog)
        with patch.object(comparison, 'configure_window_fonts'):
            buttons['编辑图例顺序…']()
        self.assertEqual(state['legend_order_text'], 'D,T')
        refreshed.assert_called_once()
        ui.UpdateGUI.assert_not_called()

    def test_transfer_to_scan_uses_page_navigation_instead_of_redrawing_transfer_tab(self):
        import OMFITlib_workbench_transfer_ui as transfer
        view = transfer.TransferPage()
        view.root, view.settings = {}, {'page': 'transfer'}
        view.compound, view.run_controls, view.nav = Mock(), Mock(), Mock()
        rows = [dict(mode='generated', paths={'cgyro': ('generated', 'input.cgyro')})]
        with patch.object(transfer, 'transfer_generated_rows', return_value=rows):
            view.transfer_run()
        view.nav.assert_called_once_with('设置 CGYRO 扫描', 'cgyro', cgyro_source_mode='generated')
        self.assertEqual(view.settings['page'], 'transfer')

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
