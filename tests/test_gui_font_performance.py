"""Real Tk checks for inexpensive page refreshes and live font handling.

Run on a desktop/display with unittest discover. The family resolver is mocked
to a locally installed face so these tests never download a font pack.
"""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import font as tkfont, ttk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'CGYRO_TGLF_scan/LIB'))
import OMFITlib_gui_fonts as fonts
import OMFITlib_gui_layout as layout


class GuiFontPerformanceTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest('A Tk desktop/display is required: ' + str(error))
        self.root.withdraw()
        self.root._project_cjk_size = 11
        self.window = tk.Toplevel(self.root)
        self.window.geometry('640x360')
        self.family = patch.object(fonts, 'font_family', return_value='DejaVu Sans')
        self.family.start()
        self.errors = []
        self.root.report_callback_exception = lambda kind, error, trace: self.errors.append(error)

    def tearDown(self):
        if not hasattr(self, 'family'):
            return
        self.root.update()
        self.family.stop()
        self.root.destroy()
        self.assertEqual(self.errors, [])

    def test_registration_does_not_rescan_existing_pages(self):
        labels = [ttk.Label(self.window, text='Scan parameter ' + str(index)) for index in range(50)]
        for label in labels:
            label.pack()
        fonts.configure_window_fonts(self.window)
        self.root.update()
        with patch.object(fonts, 'style_widgets', wraps=fonts.style_widgets) as scan:
            for _ in range(10):
                fonts.configure_window_fonts(self.window)
            self.assertEqual(scan.call_count, 0)
        self.assertEqual(tkfont.Font(root=self.root, font=labels[0].cget('font')).actual('size'), 11)
        # New controls need no full-window pass, including a new hidden tab.
        book = ttk.Notebook(self.window)
        book.pack(before=labels[0])
        first, second = ttk.Frame(book), ttk.Frame(book)
        book.add(first, text='First')
        book.add(second, text='Second')
        added = ttk.Label(second, text='New tab')
        added.pack()
        added_button = ttk.Button(second, text='New command')
        added_button.pack()
        book.select(second)
        self.root.update()
        self.assertTrue(added.winfo_ismapped())
        self.assertTrue(str(added_button.cget('style')).startswith('ProjectCJK'))
        self.assertEqual(tkfont.Font(root=self.root, font=added.cget('font')).actual('size'), 11)
        self.assertEqual(tkfont.Font(root=self.root, font=added.cget('font')).actual('family'), 'DejaVu Sans')

    def test_refresh_updates_hidden_widgets_without_global_font_changes(self):
        original_global = tkfont.nametofont('TkDefaultFont', root=self.root).actual()
        book = ttk.Notebook(self.window)
        book.pack()
        first, second = ttk.Frame(book), ttk.Frame(book)
        book.add(first, text='First')
        book.add(second, text='Hidden')
        hidden = ttk.Entry(second)
        hidden.pack()
        clicks = []
        button = ttk.Button(first, text='Apply', command=lambda: clicks.append('apply'))
        button.pack()
        fonts.configure_window_fonts(self.window)
        command = button.cget('command')
        self.root.update()
        self.root._project_cjk_size = 15
        fonts.refresh_window_fonts(self.window)
        self.root.update()
        self.assertEqual(tkfont.Font(root=self.root, font=hidden.cget('font')).actual('size'), 15)
        self.assertEqual(button.cget('command'), command)
        button.invoke()
        self.assertEqual(clicks, ['apply'])
        self.assertEqual(tkfont.nametofont('TkDefaultFont', root=self.root).actual(), original_global)

    def test_theme_or_code_profile_change_rescans_mounted_widgets(self):
        field = ttk.Entry(self.window)
        field.pack()
        fonts.configure_window_fonts(self.window)
        self.root.update()
        self.window._project_cjk_binding_profile = 'previous code'
        self.window._project_cjk_appearance = ('previous code', 11, ttk.Style(self.window).theme_use())
        fonts.configure_window_fonts(self.window)
        binding = self.window.bind('<Map>')
        self.assertEqual(binding.count(self.window._project_cjk_map_binding), 1)
        self.assertEqual(self.window._project_cjk_binding_profile, fonts.FONT_PROFILE)
        style = ttk.Style(self.window)
        other = next(name for name in style.theme_names() if name != style.theme_use())
        style.theme_use(other)
        with patch.object(fonts, 'style_widgets', wraps=fonts.style_widgets) as scan:
            fonts.configure_window_fonts(self.window)
            self.assertGreater(scan.call_count, 0)
        self.root.update()
        self.assertEqual(self.window._project_cjk_appearance[-1], other)
        self.assertTrue(style.layout(field.cget('style')))

    def test_font_queries_observe_named_font_edits_without_temporary_clones(self):
        base = tkfont.Font(root=self.root, family='DejaVu Sans', size=20, weight='normal', slant='italic')
        normal = fonts.gui_font(self.window, base)
        with patch.object(fonts.tkfont, 'Font', wraps=tkfont.Font) as constructor:
            for _ in range(20):
                self.assertIs(fonts.gui_font(self.window, base), normal)
            self.assertEqual(constructor.call_count, 0)
        base.configure(weight='bold')
        bold = fonts.gui_font(self.window, base)
        self.assertEqual(bold.actual('weight'), 'bold')
        self.assertEqual(bold.actual('slant'), 'italic')
        self.assertEqual(bold.actual('size'), 11)
        self.assertEqual(base.actual('size'), 20)

    def test_native_layout_keeps_heading_and_scroll_geometry(self):
        canvas = tk.Canvas(self.window)
        canvas.pack(fill='both', expand=True)
        content = ttk.Frame(canvas)
        canvas.create_window(0, 0, window=content, anchor='nw')
        row = ttk.Frame(content)
        row.pack(fill='x')
        heading = ttk.Label(row, text='Scan configuration', font=('DejaVu Sans', 11, 'bold'), wraplength=0)
        heading.pack()
        field_row = ttk.Frame(content)
        field_row.pack(fill='x')
        field = ttk.Entry(field_row)
        field.pack(fill='x')
        layout.finish_gui_layout(heading, compact=False)
        self.root.update()
        self.assertEqual(tkfont.Font(root=self.root, font=heading.cget('font')).actual('weight'), 'bold')
        self.assertGreater(content.winfo_height(), 1)
        self.assertGreater(field.winfo_height(), 1)
        self.assertTrue(canvas.cget('scrollregion'))
        with patch.object(fonts, 'style_widgets', wraps=fonts.style_widgets) as scan:
            layout.finish_gui_layout(heading, compact=False)
            self.assertEqual(scan.call_count, 0)

    def test_console_scan_once_and_new_console_is_styled_when_mapped(self):
        class Console(tk.Text):
            pass
        existing = Console(self.window, height=3)
        existing.pack()
        with patch.object(tk, 'ConsoleTextGUI', Console, create=True):
            layout.fix_console_layout(self.window)
            self.root.update()
            self.assertIsNotNone(getattr(existing, '_cgyro_console_layout', None))
            # No traversal of unrelated OMFIT windows on each page finish.
            with patch.object(self.root, 'winfo_children', side_effect=AssertionError('Repeated global walk')):
                for _ in range(10):
                    layout.fix_console_layout(self.window)
            added = Console(self.window, height=3)
            added.pack()
            self.root.update()
            self.assertIsNotNone(getattr(added, '_cgyro_console_layout', None))
            self.assertEqual(tkfont.Font(root=self.root, font=added.cget('font')).actual('size'), 11)


if __name__ == '__main__':
    unittest.main()
