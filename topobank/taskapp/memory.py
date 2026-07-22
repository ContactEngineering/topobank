"""Peak-memory tracking for task execution.

Every workflow / task-model run records its peak memory into ``task_memory``,
which is used to right-size workers. Two facts drive the design:

1. ``tracemalloc`` is the wrong tool for sizing. It traces *Python-allocator*
   bytes only — it misses native allocations (SDSAlgorithms/Eigen C++, NetCDF
   buffers), allocator fragmentation and the interpreter/Django baseline, all
   of which the OOM killer and container limits very much count. And numpy
   reports every array-data allocation to it: measured overhead on an
   allocation-heavy 20-Mpx feature computation is ~35x wall clock
   (28 s → 16 min). It stays available, opt-in, for *leak hunting and
   allocation attribution* via ``settings.TOPOBANK_TRACK_MEMORY_USAGE = True``
   — a different question from sizing.

2. The kernel already keeps the number sizing needs. ``VmHWM`` in
   ``/proc/self/status`` is the process's peak RSS, and writing ``"5"`` to
   ``/proc/self/clear_refs`` resets it to the *current* RSS. Reset on task
   start, read on task end → true per-task peak RSS at the cost of two /proc
   accesses. Celery's prefork children execute one task at a time, so
   per-process is per-task. (With a threaded/gevent pool concurrent tasks
   would share the counter — the value then over-approximates, which for
   sizing is the safe direction.)

Fallback ladder when ``clear_refs`` is unavailable (non-Linux dev machines,
hardened containers): a background thread samples ``/proc/self/statm`` every
100 ms for the task's duration (misses only sub-100-ms spikes); if /proc is
unavailable entirely, ``getrusage(ru_maxrss)`` — a process-lifetime
high-water mark, i.e. an upper bound in reused workers.

For capacity planning: a worker needs roughly
``parent + concurrency x max(task_memory)`` — task peaks here already
include the per-child interpreter/Django baseline.
"""

import resource
import sys
import threading
import tracemalloc
from contextlib import contextmanager

from django.conf import settings

_PAGE_SIZE = resource.getpagesize()

#: Sampling interval of the fallback RSS sampler thread.
_SAMPLE_INTERVAL = 0.1  # seconds


def _read_vm_hwm():
    """Peak RSS (``VmHWM``) of this process in bytes, or ``None``."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) * 1024  # kB → bytes
    except (OSError, ValueError, IndexError):
        pass
    return None


def _reset_vm_hwm():
    """Reset this process's peak-RSS counter to its current RSS.

    Returns True on success. Writing "5" to ``/proc/self/clear_refs`` is the
    documented kernel interface for resetting ``VmHWM`` (see proc(5)).
    """
    try:
        with open("/proc/self/clear_refs", "w") as f:
            f.write("5")
        return True
    except OSError:
        return False


def _read_rss():
    """Current RSS in bytes via ``/proc/self/statm``, or ``None``."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * _PAGE_SIZE
    except (OSError, ValueError, IndexError):
        return None


class _RssSampler:
    """Background thread recording the max RSS observed during a block."""

    def __init__(self):
        self.peak = _read_rss() or 0
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="rss-sampler", daemon=True
        )

    def _run(self):
        while not self._stop.wait(_SAMPLE_INTERVAL):
            rss = _read_rss()
            if rss is not None and rss > self.peak:
                self.peak = rss

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=1.0)
        rss = _read_rss()
        if rss is not None and rss > self.peak:
            self.peak = rss


class MemoryUsage:
    """Result object filled in when the ``track_memory_usage`` block exits."""

    #: Peak memory in bytes. Default modes report peak RSS (what the OOM
    #: killer / container limits act on); the opt-in tracemalloc mode reports
    #: peak Python-allocator usage instead. ``None`` until the block exits.
    peak = None


@contextmanager
def track_memory_usage():
    """Context manager yielding a :class:`MemoryUsage` whose ``peak`` is set
    on exit (including the exception path — the previous inline tracemalloc
    calls skipped ``stop()`` on failure, leaving tracing enabled for every
    subsequent task in the worker process)."""
    usage = MemoryUsage()

    if getattr(settings, "TOPOBANK_TRACK_MEMORY_USAGE", False):
        # Opt-in allocation profiling (leak hunting) — NOT for sizing; ~35x
        # slower on numeric workloads and blind to native allocations.
        tracemalloc.start()
        tracemalloc.reset_peak()
        try:
            yield usage
        finally:
            _, usage.peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        return

    if _reset_vm_hwm():
        # Preferred: kernel-maintained per-task peak RSS, ~zero overhead.
        try:
            yield usage
        finally:
            usage.peak = _read_vm_hwm()
        return

    if _read_rss() is not None:
        # /proc exists but the peak counter can't be reset: sample RSS.
        with _RssSampler() as sampler:
            try:
                yield usage
            finally:
                usage.peak = sampler.peak
        return

    # Last resort (no /proc, i.e. macOS dev machines): process-lifetime
    # high-water mark — an upper bound for the current task in reused
    # workers. ru_maxrss is KiB on Linux, bytes on macOS.
    scale = 1 if sys.platform == "darwin" else 1024
    try:
        yield usage
    finally:
        usage.peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale
