"""Local font and geometry adjustments for this project's native OMFIT pages."""
from builtins import all, bytearray, bytes, dict, int, isinstance, len, list, max, min, range, str, sum, tuple
from contextlib import contextmanager
import hashlib
import threading
import tkinter as tk
from tkinter import ttk
from OMFITlib_gui_context import bind_actions
from OMFITlib_gui_fonts import FONT_PROFILE, configure_window_fonts, fit_field_height, font_size, gui_font


@contextmanager
def section_group(ui, title):
    """Enclose native controls without changing their bindings or tab context."""
    aux = getattr(ui, '_aux', None)
    parent = aux.get('parentGUI', None) if isinstance(aux, dict) else None
    if not isinstance(parent, tk.Misc):
        ui.Separator(title)
        yield
        return
    style_name = 'CGYROSection.TLabelframe'
    ttk.Style(parent).configure(style_name, relief='groove', borderwidth=2)
    group = ttk.LabelFrame(parent, style=style_name, padding=(10, 8))
    heading = ttk.Label(group, text=title)
    heading._cgyro_role = 'heading'
    group.configure(labelwidget=heading, labelanchor='nw')
    group.pack(side=tk.TOP, expand=False, fill=tk.X, padx=6, pady=(14, 10))
    # same_row restores this group after each row. Always restore its parent
    # before subsequent controls are placed, including when rendering fails.
    aux['parentGUI'] = group
    try:
        yield
    finally:
        aux['parentGUI'] = parent


def finish_gui_layout(label, ui=None, compact=True, fit_tabs=True):
    """Style the page containing an OMFITx.Label, retaining native bindings.

    OMFITx.Label returns a label in a row frame in the GUI's content frame.
    Style the content subtree and OMFIT consoles without changing global named
    fonts or the theme. Non-Tk hosts require no layout.
    """
    if not isinstance(label, tk.Misc):
        return
    fix_console_layout(label)
    content = label.master.master
    bind_actions(content, ui)
    previous = getattr(content, '_cgyro_gui_layout', None)
    if previous is not None and getattr(previous, 'anchor', None) is label:
        return
    aux = getattr(ui, '_aux', {})
    resize_window = not aux.get('is_compoundGUI', False)
    content._cgyro_gui_layout = NativeLayout(content, label, compact, resize_window, fit_tabs)


def finish_gui_subtree(content):
    """Style newly populated controls without rebinding the existing window."""
    parent = content.master
    while isinstance(parent, tk.Misc):
        layout = getattr(parent, '_cgyro_gui_layout', None)
        if layout is not None:
            # GUI.update retains the content frame, but destroys its children.
            # Until finish_gui_layout installs the replacement, that frame can
            # still carry a layout from the previous code version. Its dead
            # anchor means the whole page is being rebuilt, not extended.
            anchor = getattr(layout, 'anchor', None)
            if not isinstance(anchor, tk.Misc) or not anchor.winfo_exists():
                return
            _prune_layout(layout)
            layout._walk(content)
            layout.reflow()
            layout._queue_scroll()
            return
        parent = parent.master


def _prune_layout(layout):
    """Prune shared widget lists without requiring new methods on old objects.

    A mounted layout may survive a live code update. Keep this operation in
    the new module, rather than calling a method absent from that instance's
    original class. Layout constructors and callbacks stay version-consistent.
    """
    for key in ('labels', 'notebooks', 'panels', 'reset_help_buttons', 'reset_help_spacers'):
        setattr(layout, key, [widget for widget in getattr(layout, key) if widget.winfo_exists()])
    for key in ('rows', 'inline_rows', 'forms'):
        setattr(layout, key, [entry for entry in getattr(layout, key) if entry[0].winfo_exists()])


def _style_console(console):
    """Use a real CJK font so Tk measures the glyphs that it actually draws."""
    try:
        previous = getattr(console, '_cgyro_console_layout', None)
        current = str(console.cget('font'))
        if previous is not None and current == str(previous['font']):
            return
        font = gui_font(console, current or 'TkFixedFont')
        gap = max(3, font.metrics('linespace') // 5)
        console.configure(font=font, spacing1=gap, spacing2=gap, spacing3=gap)
        # Keep the named font alive; changing fonts does not edit log contents.
        console._cgyro_console_layout = {'font': font}
    except tk.TclError:
        # A window can disappear during a project GUI refresh.
        return


def fix_console_layout(anchor=None):
    """Adjust OMFIT consoles only, including newly opened output windows."""
    if threading.current_thread() is not threading.main_thread():
        return
    root = anchor._root() if isinstance(anchor, tk.Misc) else getattr(tk, '_default_root', None)
    console_type = getattr(tk, 'ConsoleTextGUI', None)
    if root is None or console_type is None:
        return
    try:
        # A single Map hook per Tk interpreter; reloads replace only our handler.
        root._cgyro_style_console = _style_console
        if not getattr(root, '_cgyro_console_map_binding', None):
            def mapped(event):
                if isinstance(event.widget, console_type):
                    root._cgyro_style_console(event.widget)
            root._cgyro_console_map_binding = root.bind_class('Text', '<Map>', mapped, add='+')
        # Existing consoles need a scan on first use/live upgrade only. Later
        # output windows pass through the Map hook; a page refresh must not walk
        # every widget in every open OMFIT window just to find those consoles.
        if getattr(root, '_cgyro_console_scan_profile', None) == FONT_PROFILE:
            return
        pending = [root]
        while pending:
            widget = pending.pop()
            if isinstance(widget, console_type):
                _style_console(widget)
            pending.extend(widget.winfo_children())
        root._cgyro_console_scan_profile = FONT_PROFILE
    except tk.TclError:
        return


class NativeLayout:
    def __init__(self, content, label, compact=False, resize_window=True, fit_tabs=False):
        self.content = content
        self.anchor = label
        self.compact = compact
        self.fit_tabs = fit_tabs
        configure_window_fonts(content.winfo_toplevel())
        self.style = ttk.Style(content)
        base = label.cget('font') or self.style.lookup(label.cget('style') or 'TLabel', 'font') or 'TkDefaultFont'
        self.normal = gui_font(content, base, weight='normal')
        self.bold = gui_font(content, base, weight='bold')
        self.heading = gui_font(content, base, size=font_size(content) + 1, weight='bold')
        self.gap = max(4, self.normal.metrics('linespace') // 5)
        self.width = min(760, max(640, self.normal.measure('0') * 72), content.winfo_screenwidth() - 64)
        self.tag = hashlib.sha256(repr(self.normal.actual()).encode('utf-8')).hexdigest()[:12]
        background = self.style.lookup('TFrame', 'background') or '#d9d9d9'
        self.background = background
        red, green, blue = content.winfo_rgb(background)
        light = (red + green + blue) > 3 * 32768
        self.light_background = light
        self.heading_color = '#363636' if light else '#eeeeee'
        self.muted_color = '#5b5b5b' if light else '#cccccc'
        self.rows = []
        self.inline_rows = []
        self.labels = []
        self.notebooks = []
        self.panels = []
        self.reset_help_buttons = []
        self.reset_help_spacers = []
        self.forms = []
        self.configured_styles = {}
        self.scroll_pending = None
        self._walk(content)
        # Match the real help buttons after their font and padding are styled.
        # Empty help slots keep resets aligned on rows without a question mark.
        help_width = max((button.winfo_reqwidth() for button in self.reset_help_buttons),
                         default=self.normal.measure('?') + 16)
        for spacer in self.reset_help_spacers:
            spacer.configure(width=help_width)
        self.reflow()
        if compact and resize_window:
            self._portrait_window()
        self._watch_viewport()
        self._queue_scroll()

    def _portrait_window(self):
        """Set an initial narrow, tall viewport; let OMFIT scroll the content.

        Apply once per owning window, including an already-open wide Project
        window. Subsequent field updates retain the user's manual window size.
        Compound pages must not resize another module's owning window.
        """
        top = self.content.winfo_toplevel()
        if getattr(top, '_cgyro_portrait_layout', False):
            return
        height = min(900, top.winfo_screenheight() - 100)
        top.geometry('{}x{}'.format(self.width, height))
        top._cgyro_portrait_layout = True

    def _style_name(self, widget, font, **options):
        old = str(widget.cget('style')) or widget.winfo_class()
        if old == getattr(widget, '_project_cjk_applied_style', None):
            old = widget._project_cjk_base_style
        if old == getattr(widget, '_cgyro_layout_style', None):
            old = widget._cgyro_layout_base_style
        density = 'Scan.' if getattr(widget, '_cgyro_field_columns', None) is not None else ''
        name = 'CGYRO.' + self.tag + '.' + density + old
        # Retain the named font so a later font download or size change reaches
        # styles already used by mounted and hidden tabs.
        signature = (str(font), options)
        if self.configured_styles.get(name, None) != signature:
            self.style.configure(name, font=font, **options)
            self.configured_styles[name] = signature
        widget.configure(style=name)
        widget._cgyro_layout_base_style = old
        widget._cgyro_layout_style = name
        if widget.winfo_class() in ('TEntry', 'TCombobox'):
            fit_field_height(widget, name, font)

    def _walk(self, parent):
        children = parent.winfo_children()
        # Native same_row holds one frame per OMFIT control. Reflow those
        # frames, not the label/entry/default/help widgets within each control.
        row = len(children) > 1 and all(child.winfo_class() == 'TFrame' and
            child.winfo_manager() == 'pack' and str(child.pack_info().get('side', '')) == 'left' for child in children)
        for child in children:
            kind = child.winfo_class()
            if kind == 'Toplevel':
                continue
            if kind in ('TFrame', 'TLabelframe'):
                self.panels.append(child)
            if kind == 'TLabel':
                self.labels.append(child)
                role = getattr(child, '_cgyro_role', '')
                current = child.cget('font') or self.style.lookup(child.cget('style') or 'TLabel', 'font') or 'TkDefaultFont'
                bold = role in ('heading', 'pending') or str(child.tk.call(
                    'font', 'actual', current, '-displayof', str(child), '-weight')) == 'bold'
                child.configure(font=self.bold if bold else self.normal, width=0,
                                padding=(0, self.gap if bold else self.gap // 2))
                if role == 'heading':
                    child.configure(font=self.heading, foreground=self.heading_color,
                                    padding=(0, self.gap * 2, 0, self.gap))
                elif role in ('muted', 'note'):
                    child.configure(foreground=self.muted_color)
                    if role == 'note':
                        child.configure(padding=(0, self.gap, 0, self.gap * 2))
                elif role == 'pending':
                    child.configure(foreground='#3f3f3f' if self.light_background else '#eeeeee')
                if self.compact:
                    child.configure(wraplength=self.width - 80)
            elif kind in ('TEntry', 'TCombobox'):
                child.configure(font=self.normal)
                columns = getattr(child, '_cgyro_field_columns', None)
                if self.compact:
                    # Long file paths and lists scroll inside the native field.
                    # Their text must not become the window's requested width.
                    child.configure(width=columns if columns is not None else min(28, max(1, int(child.cget('width')))))
                if columns is not None and child.winfo_manager() == 'pack':
                    child.pack_configure(expand=False, fill=tk.NONE)
                self._style_name(child, self.normal, padding=(4, 2 if columns is not None else self.gap))
                if kind == 'TCombobox':
                    child.option_add('*' + str(child).lstrip('.') + '*Listbox.font', self.normal)
            elif kind in ('TButton', 'TCheckbutton', 'TRadiobutton'):
                pending = getattr(child, '_cgyro_role', '') == 'pending'
                primary = pending or getattr(child, '_cgyro_role', '') == 'primary'
                if primary:
                    child.configure(style='ProjectPending.TButton' if pending else 'ProjectPrimary.TButton')
                self._style_name(child, self.bold if primary else self.normal, padding=(6, self.gap))
                if pending:
                    name = str(child.cget('style'))
                    self.style.configure(name, background='#515151', foreground='#ffffff')
                    self.style.map(name,
                        background=[('disabled', self.background), ('pressed', '#333333'), ('active', '#666666')],
                        foreground=[('disabled', self.muted_color), ('!disabled', '#ffffff')])
                child.configure(width=0)
            elif kind == 'TNotebook':
                old = str(child.cget('style')) or 'TNotebook'
                name = 'CGYRO.' + self.tag + '.' + old
                self.style.configure(name + '.Tab', font=self.normal,
                                     padding=(10, self.gap + 2))
                child.configure(style=name)
                if self.fit_tabs and child.winfo_manager() == 'pack':
                    # OMFIT packs notebooks with expand=YES but fill=X. Tk
                    # centers that widget in its enlarged vertical parcel,
                    # leaving a gap above short tabs in a taller canvas frame.
                    child.pack_configure(expand=False, anchor='n')
            elif kind == 'Text':
                child.configure(font=self.normal, spacing1=self.gap, spacing2=self.gap, spacing3=self.gap)
            self._walk(child)
            if kind == 'TNotebook' and self.fit_tabs:
                # Nested books precede their parents when heights settle.
                self.notebooks.append(child)
                # Selection precedes deferred geometry propagation through
                # nested panes. Measure after that event, not inside it.
                child.bind('<<NotebookTabChanged>>', lambda event: self._queue_scroll(), add='+')
                child.bind('<Configure>', lambda event: self._queue_scroll(), add='+')
        children = self._reserve_reset_help(parent, children)
        form = getattr(parent, '_cgyro_form', None)
        if form is not None:
            self._form(parent, children, *form)
            self.forms.append((parent, form))
        if row:
            for child in children:
                child.pack_forget()
            if getattr(parent, '_cgyro_inline', False):
                # Long parameter names must not squeeze out value/reset/help.
                # Reflow the native row frames, keeping their callbacks intact.
                self.inline_rows.append((parent, children))
                parent.bind('<Configure>', lambda event, frame=parent, items=children:
                            self._inline_row(frame, items), add='+')
            else:
                self.rows.append((parent, children))
                parent.bind('<Configure>', lambda event, frame=parent, items=children: self._row(frame, items), add='+')

    def _reserve_reset_help(self, frame, children):
        """Keep a help slot after native resets, including within same_row."""
        resets = [child for child in children if getattr(child, '_project_reset_origin', '') in ('D', 'd')]
        if len(resets) != 1:
            return children
        reset = resets[0]
        if reset.winfo_manager() != 'pack' and getattr(frame, '_cgyro_form', None) is None:
            return children
        spacer = getattr(frame, '_cgyro_reset_help_spacer', None)
        ordered = [child for child in children if child is not spacer]
        index = ordered.index(reset) + 1
        tail = ordered[index:]
        if tail and tail[0].winfo_class() == 'TButton' and str(tail[0].cget('text')) == '?':
            self.reset_help_buttons.append(tail[0])
            return children
        # Native optional web links follow help; retain their position and command.
        if not all(child.winfo_class() == 'TButton' and str(child.cget('text')) == 'w' for child in tail):
            return children
        if spacer is None:
            spacer = ttk.Frame(frame, width=self.normal.measure('?') + 16)
            frame._cgyro_reset_help_spacer = spacer
        if getattr(frame, '_cgyro_form', None) is None:
            options = {'side': tk.LEFT, 'expand': False, 'fill': tk.NONE, 'padx': 0, 'pady': 0}
            if tail:
                options['before'] = tail[0]
            spacer.pack(**options)
        self.reset_help_spacers.append(spacer)
        ordered.insert(index, spacer)
        return ordered

    def _form(self, frame, children, field, caption, wide, short):
        """Align native field labels; paths and scripts get a full-width row."""
        if not children or field not in children:
            return
        label = children[0]
        label.configure(text=caption, anchor='w', wraplength=0)
        for child in children:
            child.pack_forget()
        if wide:
            frame.columnconfigure(0, weight=1)
            label.grid(row=0, column=0, columnspan=len(children) - 1, sticky='w', pady=(self.gap, 0))
            for index, child in enumerate(children[1:]):
                child.grid(row=1, column=index, sticky='ew' if child is field else 'w',
                           padx=(0, 4), pady=(0, self.gap // 2))
        else:
            frame.columnconfigure(0, minsize=max(self.normal.measure(caption),
                                               self.normal.measure('每进程线程数'),
                                               self.normal.measure('profiles_gen')) + 18)
            frame.columnconfigure(1, weight=1)
            for index, child in enumerate(children):
                child.grid(row=0, column=index, sticky='ew' if child is field and not short else 'w',
                           padx=(0, 4), pady=self.gap // 2)
        if short:
            field.configure(width=12)

    def _fit_tab(self, notebook):
        """Hidden history pages must not determine the active form's height."""
        try:
            selected = notebook.select()
            if selected:
                height = max(1, notebook.nametowidget(selected).winfo_reqheight())
                if notebook.winfo_pixels(notebook.cget('height')) != height:
                    notebook.configure(height=height)
                    return True
        except tk.TclError:
            return False
        return False

    def _settle_tabs(self):
        """Let changed child sizes propagate before sizing their root Canvas."""
        for notebook in self.notebooks:
            if self._fit_tab(notebook):
                self._queue_scroll()
                return False
        return True

    def _watch_viewport(self):
        content = self.content
        if not getattr(content, '_cgyro_layout_cleanup', None):
            def closed(event):
                current = getattr(content, '_cgyro_gui_layout', None)
                if event.widget is content and current is not None:
                    current._cancel_scroll()
            content._cgyro_layout_cleanup = content.bind('<Destroy>', closed, add='+')
        canvas = self.content.master
        if not isinstance(canvas, tk.Canvas):
            return
        tag = getattr(canvas, '_cgyro_viewport_tag', None)
        if tag is None:
            tag = 'CGYROViewport' + str(canvas)
            canvas._cgyro_viewport_tag = tag
        def changed(event):
            current = getattr(content, '_cgyro_gui_layout', None)
            try:
                if current is not None and content.winfo_exists() and current.anchor.winfo_exists():
                    current._queue_scroll()
            except tk.TclError:
                pass
        # OMFIT replaces widget Configure bindings after every redraw. The
        # local tag retains native handlers, including after a live upgrade
        # from a version whose existing tag did not yet observe Map events.
        for sequence in ('<Configure>', '<Map>', '<Destroy>'):
            if not canvas.bind_class(tag, sequence):
                canvas.bind_class(tag, sequence, changed)
        if not getattr(canvas, '_cgyro_viewport_cleanup', None):
            def cleanup(event):
                if event.widget is canvas:
                    current = getattr(content, '_cgyro_gui_layout', None)
                    try:
                        canvas.unbind_class(tag, '<Configure>')
                        canvas.unbind_class(tag, '<Map>')
                        canvas.unbind_class(tag, '<Destroy>')
                    except tk.TclError:
                        pass
                    if current is not None:
                        current._cancel_scroll()
            canvas._cgyro_viewport_cleanup = canvas.bind('<Destroy>', cleanup, add='+')
        # Observe intermediate pane/compound frames too. Their requested size
        # can settle after an inner tab changes while its parent stays clipped.
        # Map events also reach newly selected panes with unchanged allocation.
        for widget in (canvas, self.content, *self.content.winfo_children(), *self.notebooks, *self.panels):
            tags = list(widget.bindtags())
            if tag not in tags:
                tags.insert(1, tag)
                widget.bindtags(tuple(tags))

    def _queue_scroll(self):
        if self.scroll_pending is None:
            self.scroll_pending = self.content.after_idle(self._sync_scroll)

    def _cancel_scroll(self):
        if self.scroll_pending is not None:
            try:
                self.content.after_cancel(self.scroll_pending)
            except tk.TclError:
                pass
            self.scroll_pending = None

    def _content_height(self):
        height = 0
        for child in self.content.pack_slaves():
            info = child.pack_info()
            padding = info.get('pady', 0)
            if isinstance(padding, (tuple, list)):
                values = padding
            else:
                # pack_info can return an int or a Tcl distance/list object.
                # splitlist accepts text, not an arbitrary Python scalar.
                text = padding if isinstance(padding, (str, bytes, bytearray)) else str(padding)
                values = self.content.tk.splitlist(text)
            pads = [self.content.winfo_pixels(value) for value in values]
            outside = 2 * pads[0] if len(pads) == 1 else sum(pads)
            height += child.winfo_reqheight() + outside + 2 * self.content.winfo_pixels(info.get('ipady', 0))
        return max(1, height)

    def _sync_scroll(self):
        """Fit our root content to the viewport, retaining vertical scrolling."""
        self.scroll_pending = None
        if getattr(self.content, '_cgyro_gui_layout', None) is not self or not self.anchor.winfo_exists():
            return
        canvas = self.content.master
        if not isinstance(canvas, tk.Canvas):
            self._settle_tabs()
            return
        try:
            for item in canvas.find_all():
                if canvas.type(item) != 'window' or canvas.itemcget(item, 'window') != str(self.content):
                    continue
                inset = 2 * (canvas.winfo_pixels(canvas.cget('borderwidth')) +
                             canvas.winfo_pixels(canvas.cget('highlightthickness')))
                width = canvas.winfo_width() - inset
                if width <= 1:
                    width = max(1, self.width - 32)
                for label in self.labels:
                    if not label.winfo_exists() or label.winfo_pixels(label.cget('wraplength')) <= 0:
                        continue
                    parent_width = label.master.winfo_width()
                    # Native Label's row binding uses this same width. Keep
                    # both handlers in agreement so wrapping cannot oscillate.
                    limit = max(1, min(width, parent_width if parent_width > 1 else width))
                    if label.winfo_pixels(label.cget('wraplength')) != limit:
                        label.configure(wraplength=limit)
                        self._queue_scroll()
                if not self._settle_tabs():
                    return
                height = self._content_height()
                # Complete measurement and set a valid size before freezing
                # propagation. A measurement error must not freeze a zero-size
                # frame and unmap the rest of the page.
                if self.content.winfo_pixels(self.content.cget('width')) != width or self.content.winfo_pixels(self.content.cget('height')) != height:
                    self.content.configure(width=width, height=height)
                # Native configure_size takes max(requested, visible width).
                # Stop hidden panes or newly added rows inflating that request.
                self.content.pack_propagate(False)
                if canvas.winfo_pixels(canvas.itemcget(item, 'width')) != width or canvas.winfo_pixels(canvas.itemcget(item, 'height')) != height:
                    canvas.itemconfigure(item, width=width, height=height)
                canvas.configure(scrollregion=(0, 0, width, height))
                break
        except tk.TclError:
            return

    def _row(self, frame, items):
        if not frame.winfo_exists():
            return
        width = frame.winfo_width()
        if width <= 1:
            width = self.width - 40 if self.compact else max(1, self.content.winfo_toplevel().winfo_width() - 40)
        required = max(item.winfo_reqwidth() + 10 for item in items)
        columns = max(1, min(len(items), width // max(1, required)))
        if self.compact:
            columns = min(getattr(frame, '_cgyro_max_columns', 2), columns)
        if getattr(frame, '_cgyro_columns', None) == columns:
            return
        frame._cgyro_columns = columns
        for index in range(len(items)):
            frame.columnconfigure(index, weight=1 if index < columns else 0, uniform='cgyro' if index < columns else '')
        for index, item in enumerate(items):
            item.grid(row=index // columns, column=index % columns, sticky='ew', padx=5, pady=self.gap // 2)
        self._queue_scroll()

    def prune(self):
        # Existing 1.24.23 tab callbacks can outlive a live code update.
        _prune_layout(self)

    def reflow(self):
        for frame, items in self.rows:
            self._row(frame, items)
        for frame, items in self.inline_rows:
            self._inline_row(frame, items)

    def _inline_row(self, frame, items):
        """Stack the caption above its controls when a parameter row is narrow.

        Measure the unwrapped caption, so wrapping cannot alternate between
        layouts. Controls keep native bindings and their original order.
        """
        if not frame.winfo_exists() or not items:
            return
        width = frame.winfo_width()
        if width <= 1:
            width = self.width - 40
        captions = [child for child in items[0].winfo_children() if child.winfo_class() == 'TLabel']
        caption_width = max((self.normal.measure(str(child.cget('text'))) for child in captions), default=0)
        controls_width = sum(child.winfo_reqwidth() + 10 for child in items[1:])
        stacked = caption_width + controls_width + 20 > width
        if getattr(frame, '_cgyro_inline_stacked', None) == stacked:
            return
        frame._cgyro_inline_stacked = stacked
        for index in range(len(items)):
            frame.columnconfigure(index, weight=1 if index == 0 else 0, uniform='')
        for index, child in enumerate(items):
            child.grid_forget()
            row, column = (0, 0) if index == 0 else ((1, index - 1) if stacked else (0, index))
            child.grid(row=row, column=column, columnspan=max(1, len(items) - 1) if stacked and index == 0 else 1,
                       sticky='ew', padx=5, pady=self.gap // 2)
        self._queue_scroll()

    def refresh_font_metrics(self):
        """Re-measure after a GUI font/size change without rebuilding callbacks."""
        self.gap = max(4, self.normal.metrics('linespace') // 5)
        self.width = min(760, max(640, self.normal.measure('0') * 72), self.content.winfo_screenwidth() - 64)
        for frame, form in self.forms:
            if frame.winfo_exists() and not form[2]:
                frame.columnconfigure(0, minsize=max(self.normal.measure(form[1]),
                                                   self.normal.measure('每进程线程数'),
                                                   self.normal.measure('profiles_gen')) + 18)
        for frame, items in self.rows:
            frame._cgyro_columns = None
        for frame, items in self.inline_rows:
            frame._cgyro_inline_stacked = None
        self.reflow()
        self._queue_scroll()
