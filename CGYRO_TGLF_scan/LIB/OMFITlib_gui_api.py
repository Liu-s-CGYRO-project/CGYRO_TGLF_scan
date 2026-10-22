"""Project-local controls, help and deferred refresh; no global OMFIT patches."""
from OMFITlib_gui_fonts import configure_window_fonts, gui_font, style_checkbox, style_widget
from builtins import callable, dict, enumerate, getattr, isinstance, list, max, min, repr, set, str, tuple
import inspect
from functools import update_wrapper
from types import FunctionType
import tkinter as tk
from tkinter import ttk


class _DeferredGUIRefresh:
    """Refresh one native GUI after its control callback has returned.

    Native controls test updateGUI after committing their value/action.
    That destroys/recreates controls inside their own selection callback and
    also rebuilds unrelated windows. A normal timer, unlike after_idle, cannot
    run inside OMFIT's update_idletasks while that callback is still active.
    """
    def __init__(self, api, gui, registry):
        self.api, self.gui, self.registry = api, gui, registry
        self.top = gui.top
        self.pending = None
        self.running = self.dirty = self.closed = False
        self.top.bind('<Destroy>', self._closed, add='+')

    def __bool__(self):
        """Replace the native redraw branch, not its value/validation callback.

        OMFIT passes updateGUI through helpers, then evaluates it at the end of
        a successful edit (or Button's finally). Request the owner and decline
        the global event. This also preserves norm, delete_if_default and reset
        semantics that would be lost by wrapping/replacing postcommand.
        """
        self.request()
        return False

    def request(self):
        if self.closed or self.registry.get(str(self.top), None) is not self.gui:
            return
        self.dirty = True
        if self.pending is None and not self.running:
            self.pending = self.top.after(1, self.flush)

    def flush(self):
        self.pending = None
        if self.closed or self.registry.get(str(self.top), None) is not self.gui:
            return
        # Saving owns the session tree. Keep processing Tk events while it
        # finishes instead of nesting another module redraw in its wait loop.
        session = getattr(self.api, 'OMFITaux', {}).get('GUI', None)
        if getattr(session, 'lockSave', False):
            self.pending = self.top.after(100, self.flush)
            return
        self.dirty, self.running = False, True
        try:
            self.gui.update()
        finally:
            self.running = False
            if self.dirty:
                self.request()

    def _closed(self, event):
        if event.widget is self.top:
            self.closed = True
            if self.pending is not None:
                self.top.after_cancel(self.pending)
                self.pending = None


def _deferred_gui_refresh(api, parent):
    """Locate the GUI by ancestry, never by OMFIT's last-rendered GUI global."""
    registry = getattr(api, '_GUIs', None)
    if not isinstance(registry, dict):
        return None
    while isinstance(parent, tk.Misc):
        gui = registry.get(str(parent), None)
        if gui is not None:
            refresh = getattr(gui, '_cgyro_deferred_refresh', None)
            if refresh is None:
                refresh = gui._cgyro_deferred_refresh = _DeferredGUIRefresh(api, gui, registry)
            return refresh
        parent = parent.master
    return None


def _constructor_copy(function, helpers):
    """Substitute private helper calls for one render, leaving OMFIT untouched."""
    namespace = dict(function.__globals__)
    namespace.update(helpers)
    constructor = FunctionType(function.__code__, namespace, function.__name__,
                               function.__defaults__, function.__closure__)
    constructor.__kwdefaults__ = function.__kwdefaults__
    return update_wrapper(constructor, function)


def _local_entry(function, text_function, refresh):
    """Keep the native Entry body, localizing its hardcoded multiline refresh.

    Entry's showText closure passes True to _Text even when updateGUI is False.
    A render-local constructor copy substitutes only that helper. The original
    functions/globals are untouched; native resolved locations, normalization,
    locks, editor contents and postcommand closures are passed through intact.
    Do not cache this globals snapshot across GUI renders or code upgrades.
    """
    def local_text(*args, **kwargs):
        bound = inspect.signature(text_function).bind_partial(*args, **kwargs)
        if bound.arguments.get('updateGUI', False) is not False:
            bound.arguments['updateGUI'] = refresh
        return text_function(*bound.args, **bound.kwargs)

    return _constructor_copy(function, {'_Text': local_text})


def _own_button_timers(button):
    """Cancel only this button's callbacks when a local redraw destroys it.

    The native non-global branch schedules re-enable at 250 ms. Its Tcl
    command would otherwise disappear during our earlier redraw, leaving a
    dangling timer and a Tk background error. Preserve native Button behavior.
    """
    if getattr(button, '_cgyro_owned_timers', None) is not None:
        return
    pending = button._cgyro_owned_timers = set()
    destroyed = [False]
    original_after, original_cancel = button.after, button.after_cancel

    def after(ms, func=None, *args):
        if func is None:
            return original_after(ms)
        # A task may have already redrawn the GUI inside the native command,
        # before Button's finally attempts its re-enable timer.
        if destroyed[0]:
            return None
        timer = [None]
        def call():
            pending.discard(timer[0])
            return func(*args)
        timer[0] = original_after(ms, call)
        pending.add(timer[0])
        return timer[0]

    def closed(event):
        if event.widget is button:
            destroyed[0] = True
            for timer in list(pending):
                original_cancel(timer)
            pending.clear()

    button.after = after
    button.bind('<Destroy>', closed, add='+')


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
        self._owner = getattr(api, '_aux', {}).get('parentGUI', None)
        self._entry_functions = {}
        self._helper_functions = {}

    def UpdateGUI(self, top=None, all_windows=False):
        """Refresh the captured owner, or an explicit target, after callbacks.

        all_windows is an explicit escape hatch for callers that truly change
        every GUI. Native template apply/undo uses its own synchronous updates.
        """
        if all_windows:
            return self._api.UpdateGUI(top=top)
        refresh = _deferred_gui_refresh(self._api, top if top is not None else self._owner)
        if refresh is not None:
            refresh.request()
        elif top is not None:
            return self._api.UpdateGUI(top=top)

    updateGUI = UpdateGUI

    def __getattr__(self, name):
        function = getattr(self._api, name)
        # These native selectors construct controls internally, bypassing the
        # public adapter (ObjectPicker even hardcodes updateGUI=True).
        # ShotTimeDevice is intentionally excluded: edits propagate to shared
        # MainSettings and must update modules inheriting those values.
        helpers = {'ObjectPicker': ('Button', 'FilePicker'), 'ModulePicker': ('ComboBox',)}
        if name in helpers and isinstance(function, FunctionType):
            if function not in self._helper_functions:
                self._helper_functions[function] = _constructor_copy(
                    function, {key: getattr(self, key) for key in helpers[name]})
            return self._helper_functions[function]
        if name not in ('Entry', 'ComboBox', 'Button', 'CheckBox', 'FilePicker',
                        'EditASCIIobject', 'ListEditor', 'TreeLocationPicker', 'Slider', 'RadioButtons') or not callable(function):
            return function

        def create(*args, **kwargs):
            parent = getattr(self._api, '_aux', {}).get('parentGUI', None)
            arguments = dict(kwargs)
            bound = None
            if args:
                arguments.setdefault('location', args[0])
            # Respect native positional signatures; never rewrite entry values.
            try:
                bound = inspect.signature(function).bind_partial(*args, **kwargs)
                arguments.update(bound.arguments)
            except (TypeError, ValueError):
                pass
            constructor = function
            refresh = _deferred_gui_refresh(self._api, parent)
            if refresh is not None:
                if arguments.get('updateGUI', False) and bound is not None:
                    bound.arguments['updateGUI'] = refresh
                    args, kwargs = bound.args, bound.kwargs
                text_function = getattr(self._api, '_Text', None)
                if name == 'Entry' and isinstance(function, FunctionType) and callable(text_function):
                    key = (function, refresh)
                    if key not in self._entry_functions:
                        self._entry_functions[key] = _local_entry(function, text_function, refresh)
                    constructor = self._entry_functions[key]
            help_text = arguments.get('help', '')
            before = set(parent.winfo_children()) if isinstance(parent, tk.Misc) else set()
            result = constructor(*args, **kwargs)
            if name == 'Button' and refresh is not None and isinstance(result, tk.Misc):
                _own_button_timers(result)
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
