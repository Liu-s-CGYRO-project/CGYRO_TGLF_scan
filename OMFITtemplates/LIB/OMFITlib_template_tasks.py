"""Background task ownership; workers never call Tk or a live OMFIT object.

Each channel has its own generation and cancellation event. Late messages from
an invalidated task cannot affect its replacement. Progress is coalesced so a
large transfer cannot fill the UI queue faster than Tk can drain it.
"""
from builtins import BaseException, RuntimeError, getattr, len, range, str, tuple, type
from collections import deque, namedtuple
import queue
import threading


TaskEvent = namedtuple('TaskEvent', 'kind channel generation result error callback label done total receipt dispose')
Task = namedtuple('Task', 'generation cancel success failure')


class BackgroundTasks:
    """Thread-safe transport with explicit main-thread acceptance of outcomes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._context = threading.local()
        self._active = {}
        self._completed = deque()
        self._progress = {}
        self._disposal_errors = deque()
        self._generation = 0
        self._closed = False

    def start(self, channel, work, success=None, failure=None, cancel=None, receipt='', dispose=None):
        """Run work; receipt marks a durable commit, dispose owns unclaimed data.

        A successful durable operation must still be reported if cancellation
        races its completion. Its UI callback must not chain new work when the
        cancellation event is set. Disposal is opt-in and idempotent, only for
        results that have never been delivered to the success callback.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError('Background task controller is closed')
            previous = self._active.get(channel)
            if previous is not None:
                previous.cancel.set()
            self._generation += 1
            task = Task(self._generation, cancel if cancel is not None else threading.Event(), success, failure)
            self._active[channel] = task
            self._progress.pop(channel, None)

        def run():
            self._context.identity = (channel, task.generation)
            try:
                result = work()
                event = TaskEvent('success', channel, task.generation, result, None, success, '', 0, 0, receipt, dispose)
            except BaseException as exc:
                # A worker Abort must still release the UI's busy/close state.
                # The original exception is transported, not silently discarded.
                event = TaskEvent('error', channel, task.generation, None, exc, failure, '', 0, 0, '', None)
            finally:
                self._context.identity = None
            with self._lock:
                owned = not self._closed and self._active.get(channel) is task
                if owned:
                    self._completed.append(event)
            if not owned:
                self.discard(event)

        try:
            threading.Thread(target=run, name='omfit-template-' + channel, daemon=True).start()
        except BaseException:
            self.invalidate(channel)
            raise
        return task.cancel

    def progress(self, label, done, total):
        identity = getattr(self._context, 'identity', None)
        if identity is None:
            return
        channel, generation = identity
        with self._lock:
            task = self._active.get(channel)
            if not self._closed and task is not None and task.generation == generation:
                self._progress[channel] = TaskEvent('progress', channel, generation, None, None, None, label, done, total, '', None)

    def next_event(self, blocked=()):
        """Return one event without allowing a deferred channel to block others."""
        with self._lock:
            for unused in range(len(self._completed)):
                event = self._completed.popleft()
                if event.channel in blocked:
                    self._completed.append(event)
                else:
                    return event
            for channel in tuple(self._progress):
                if channel not in blocked:
                    return self._progress.pop(channel)
        raise queue.Empty

    def accept(self, event):
        """Consume only the currently owned generation and report cancellation."""
        with self._lock:
            task = self._active.get(event.channel)
            accepted = not self._closed and task is not None and task.generation == event.generation
            cancelled = task.cancel.is_set() if accepted else False
            if accepted and event.kind != 'progress':
                self._active.pop(event.channel)
                self._progress.pop(event.channel, None)
        if not accepted:
            self.discard(event)
        return accepted, cancelled

    def discard(self, event):
        """Release only explicitly owned staging data, never arbitrary results."""
        if event.kind == 'success' and event.dispose is not None:
            try:
                event.dispose(event.result)
            except BaseException as exc:
                # Ownership was already released. A faulty cleanup must neither
                # strand later files nor reactivate a cancelled task. Keep only
                # text, not a traceback that retains the abandoned result.
                with self._lock:
                    self._disposal_errors.append(type(exc).__name__ + ': ' + str(exc))

    def take_disposal_errors(self):
        """Drain cleanup diagnostics on the UI thread without owning results."""
        with self._lock:
            messages = tuple(self._disposal_errors)
            self._disposal_errors.clear()
        return messages

    def invalidate(self, channel):
        with self._lock:
            task = self._active.pop(channel, None)
            if task is not None:
                task.cancel.set()
            self._progress.pop(channel, None)

    def close(self):
        with self._lock:
            self._closed = True
            for task in self._active.values():
                task.cancel.set()
            self._active.clear()
            abandoned = tuple(self._completed)
            self._completed.clear()
            self._progress.clear()
        for event in abandoned:
            self.discard(event)
