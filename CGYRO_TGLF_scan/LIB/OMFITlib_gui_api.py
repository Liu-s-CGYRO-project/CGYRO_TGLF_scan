"""Local OMFIT widget adapter: full help text without global tooltip patches."""
from OMFITlib_gui_fonts import configure_window_fonts, gui_font, style_widget
from builtins import abs, callable, dict, enumerate, getattr, int, isinstance, list, max, min, range, repr, set, str, tuple, zip
import inspect
import tkinter as tk
from tkinter import ttk


def set_checkbox_value(control, value):
    """Give each native checkbox its own live variable; None means invalid."""
    variable = getattr(control, '_omfit_boolean', None)
    if variable is None:
        variable = tk.BooleanVar(master=control, value=False)
        control._omfit_boolean = variable
    control.configure(variable=variable, onvalue=1, offvalue=0)
    variable.set(value is True)
    control.state(['!alternate', 'selected' if value is True else '!selected'])
    if value is None:
        control.state(['alternate'])


def _checkbox_images(master, size, disabled=False):
    """Draw neutral indicators without a platform theme or a font glyph."""
    edge, fill, ink = ('#a2a2a2', '#eeeeee', '#888888') if disabled else ('#707070', '#ffffff', '#202020')
    images = []
    for mark in ('off', 'on', 'mixed'):
        image = tk.PhotoImage(master=master, width=size + 6, height=size)
        image.put(edge, to=(0, 0, size, size))
        image.put(fill, to=(1, 1, size - 1, size - 1))
        thickness = max(2, size // 9)
        if mark == 'mixed':
            image.put(ink, to=(size // 4, size // 2, size * 3 // 4, size // 2 + thickness))
        elif mark == 'on':
            points = [(size // 5, size // 2), (size * 2 // 5, size * 3 // 4), (size * 4 // 5, size // 4)]
            for (x0, y0), (x1, y1) in zip(points, points[1:]):
                steps = max(abs(x1 - x0), abs(y1 - y0))
                for step in range(steps + 1):
                    x = x0 + (x1 - x0) * step // steps
                    y = y0 + (y1 - y0) * step // steps
                    image.put(ink, to=(x, y, x + thickness, y + thickness))
        images.append(image)
    return images


def style_checkbox(control):
    """Replace only this project's indicator; retain label/font/focus layout."""
    style = ttk.Style(control)
    original = str(control.cget('style')) or 'TCheckbutton'
    if original == getattr(control, '_project_checkbox_style', None):
        original = control._project_checkbox_base_style
    font = gui_font(control, style.lookup(original, 'font') or 'TkDefaultFont')
    size = max(14, min(26, int(font.metrics('linespace') * 0.7)))
    key = (style.theme_use(), size)
    name = 'ProjectChecksV1{}.'.format(size) + original
    if (str(control.cget('style')) == name and
            getattr(control, '_project_checkbox_appearance', None) == key):
        return
    root = control._root()
    cache = getattr(root, '_project_checkbox_images', None)
    if cache is None:
        cache = root._project_checkbox_images = {}
    element = 'ProjectChecksV1{}.indicator'.format(size)
    if key not in cache:
        off, on, mixed = _checkbox_images(root, size)
        disabled_off, disabled_on, disabled_mixed = _checkbox_images(root, size, disabled=True)
        style.element_create(element, 'image', off,
            ('disabled', 'alternate', disabled_mixed), ('disabled', 'selected', disabled_on),
            ('disabled', disabled_off), ('alternate', mixed), ('selected', on),
            width=size + 6, sticky='w')
        # Tk does not retain Python image objects. Keep them for the interpreter,
        # including after a hidden tab or its original checkbox is destroyed.
        cache[key] = (off, on, mixed, disabled_off, disabled_on, disabled_mixed)

    def replace_indicator(layout):
        result = []
        for name, options in layout:
            options = dict(options)
            if 'children' in options:
                options['children'] = replace_indicator(options['children'])
            result.append((element if name.endswith('.indicator') else name, options))
        return result

    style.layout(name, replace_indicator(style.layout(original)))
    control.configure(style=name)
    control._project_checkbox_base_style = original
    control._project_checkbox_style = name
    control._project_checkbox_appearance = key
    if not getattr(control, '_project_checkbox_theme_binding', None):
        control._project_checkbox_theme_binding = control.bind(
            '<<ThemeChanged>>', lambda event: style_checkbox(control), add='+')


def _bind_native_checkboxes(api, arguments, controls):
    """Read the native tree after defaults, including already-alternate boxes."""
    resolve = getattr(api, '_absLocation', None)
    evaluate = getattr(api, '_eval', None)
    representation = getattr(api, 'repr', repr)
    locations = resolve(arguments['location']) if callable(resolve) and callable(evaluate) else None
    if isinstance(locations, str):
        locations = [locations]
    mapping = arguments.get('mapFalseTrue', None) or ([0, 1] if arguments.get('useInt', False) else [False, True])

    def synchronize():
        for index, control in enumerate(controls):
            if not isinstance(control, tk.Misc) or not control.winfo_exists():
                continue
            if locations is None:
                value = None if control.instate(['alternate']) else control.instate(['selected'])
            else:
                actual = representation(evaluate(locations[index]))
                value = False if actual == representation(mapping[0]) else True if actual == representation(mapping[1]) else None
            set_checkbox_value(control, value)

    synchronize()
    for control in controls:
        if isinstance(control, tk.Misc):
            style_checkbox(control)
    return synchronize


def compact_reset(widget, caption=''):
    """Short reset caption and a local tooltip; keep the native command intact."""
    if caption in ('D', 'd'):
        widget._project_reset_origin = caption
    origin = getattr(widget, '_project_reset_origin', '')
    text = {'D': '重置为模块默认值', 'd': '重置为模块载入时的值'}.get(origin, '重置为默认值')
    widget.configure(text='重置')
    previous = getattr(widget, '_project_reset_tip', None)
    if previous is not None:
        previous['text'] = text
        return
    state = {'window': None, 'timer': None, 'text': text}
    widget._project_reset_tip = state

    def hide(event=None):
        timer, window = state['timer'], state['window']
        state['timer'], state['window'] = None, None
        try:
            if timer is not None:
                widget.after_cancel(timer)
            if window is not None:
                window.destroy()
        except tk.TclError:
            pass

    def show():
        state['timer'] = None
        try:
            if not widget.winfo_exists():
                return
            tip = tk.Toplevel(widget)
            configure_window_fonts(tip)
            state['window'] = tip
            tip.withdraw()
            tip.overrideredirect(True)
            ttk.Label(tip, text=state['text'], padding=(8, 5), wraplength=320).pack()
            tip.update_idletasks()
            width, height = tip.winfo_reqwidth(), tip.winfo_reqheight()
            x = max(0, min(widget.winfo_rootx(), widget.winfo_screenwidth() - width))
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            if y + height > widget.winfo_screenheight():
                y = max(0, widget.winfo_rooty() - height - 4)
            tip.geometry('+{}+{}'.format(x, y))
            tip.deiconify()
        except tk.TclError:
            hide()

    def enter(event):
        hide()
        state['timer'] = widget.after(350, show)

    widget.bind('<Enter>', enter, add='+')
    for event in ('<Leave>', '<ButtonPress-1>', '<Destroy>'):
        widget.bind(event, hide, add='+')


def show_help(parent, text):
    if isinstance(text, (list, tuple)):
        text = '\n'.join(str(value) for value in text)
    top = tk.Toplevel(parent.winfo_toplevel())
    configure_window_fonts(top)
    top.title('说明')
    top.transient(parent.winfo_toplevel())
    sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
    width, height = min(720, sw - 80), min(460, sh - 100)
    x = max(0, min(parent.winfo_rootx(), sw - width - 20))
    y = max(0, min(parent.winfo_rooty(), sh - height - 50))
    top.geometry('{}x{}+{}+{}'.format(width, height, x, y))
    frame = ttk.Frame(top, padding=12)
    frame.pack(fill='both', expand=True)
    body = tk.Text(frame, wrap='word', width=1, height=1, padx=10, pady=8,
                   font=gui_font(top), borderwidth=0)
    scroll = ttk.Scrollbar(frame, command=body.yview)
    body.configure(yscrollcommand=scroll.set)
    body.grid(row=0, column=0, sticky='nsew')
    scroll.grid(row=0, column=1, sticky='ns')
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)
    body.insert('1.0', str(text))
    body.configure(state='disabled')
    ttk.Button(frame, text='关闭', command=top.destroy).grid(row=1, column=0, columnspan=2, pady=(10, 0))
    top.bind('<Escape>', lambda event: top.destroy())
    body.focus_set()
    return top


def children(parent):
    result = []
    if isinstance(parent, tk.Misc):
        for child in parent.winfo_children():
            result.append(child)
            result.extend(children(child))
    return result


class ProjectWidgets:
    def __init__(self, api):
        self._api = api
        self._project_widget_adapter = True

    def __getattr__(self, name):
        function = getattr(self._api, name)
        if name not in ('Entry', 'ComboBox', 'Button', 'CheckBox', 'FilePicker', 'RadioButtons') or not callable(function):
            return function

        def create(*args, **kwargs):
            parent = getattr(self._api, '_aux', {}).get('parentGUI', None)
            arguments = dict(kwargs)
            if args:
                arguments.setdefault('location', args[0])
            # Respect native positional signatures; never rewrite entry values.
            try:
                arguments.update(inspect.signature(function).bind_partial(*args, **kwargs).arguments)
            except (TypeError, ValueError):
                pass
            help_text = arguments.get('help', '')
            before = set(parent.winfo_children()) if isinstance(parent, tk.Misc) else set()
            result = function(*args, **kwargs)
            added = []
            if isinstance(parent, tk.Misc):
                for frame in parent.winfo_children():
                    if frame not in before:
                        added.extend([frame] + children(frame))
            defaults = []
            for widget in added:
                # Native OMFIT assigns its own font while creating fields.
                # Override it after creation, including before a hidden tab maps.
                style_widget(widget)
                if widget.winfo_class() != 'TButton':
                    continue
                caption = str(widget.cget('text'))
                if caption in ('D', 'd'):
                    compact_reset(widget, caption)
                    defaults.append(widget)
                elif caption == '?' and help_text:
                    widget.configure(command=lambda w=widget, text=help_text: show_help(w, text))
            if name == 'CheckBox' and result:
                synchronize = _bind_native_checkboxes(self._api, arguments, result)
                # Native reset changes the tree and state directly. Read its
                # actual mapped value instead of retaining an obsolete variable.
                for button in defaults:
                    command = tuple(button.tk.splitlist(str(button.cget('command'))))
                    def reset(command=command, button=button, synchronize=synchronize):
                        value = button.tk.call(*command)
                        synchronize()
                        return value
                    button.configure(command=reset)
            return result
        return create


def adapt(api):
    return api if getattr(api, '_project_widget_adapter', False) else ProjectWidgets(api)
