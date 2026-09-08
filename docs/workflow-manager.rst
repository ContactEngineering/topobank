Workflow managers
=================

topobank does not run analyses itself. It creates the record of a run - a
``WorkflowResult`` for a workflow, or another task-state row such as a
``Topography`` whose derived files need refreshing - applies its business
rules (authorization, de-duplication, permissions, ownership) and then hands
the work to a *workflow manager*. What happens next - queueing, dependency
resolution, fan-out, resource limits, which worker fleet runs the code - is the
manager's business. topobank neither knows nor cares whether a manager builds
a DAG, when it does so, or which engine executes it.

The launch API
--------------

The contract lives in :mod:`topobank.taskapp.launch` and has three parts.

**launch.** topobank builds a :class:`~topobank.taskapp.launch.LaunchRequest`,
a self-contained job envelope: which row, whether it is a workflow or a plain
task, the workflow name and its parameters, the subject hash, the owning
organization and requesting user, the parent when the run is a dependency, a
logical queue hint and the storage prefix output should go to. The manager
returns a :class:`~topobank.taskapp.launch.LaunchHandle`, an opaque JSON
document naming the manager and carrying whatever the manager needs to find
the run again. topobank stores the handle on the row in ``execution_handle``.

**poll / cancel.** topobank asks the manager named in the handle what it knows
about the run (a :class:`~topobank.taskapp.launch.RunInfo` with state,
progress and messages) or asks it to stop the run. Because the handle names its
manager, rows launched under one manager stay pollable after the default
changes, so two managers can run side by side during a migration.

**report.** The manager reports how a run is going through the status contract
in :mod:`topobank.taskapp.status`. A
:class:`~topobank.taskapp.status.StatusReport` carries the task state and,
optionally, error and traceback, peak memory, per-stage timings, DOIs and the
list of files the run produced. :func:`~topobank.taskapp.status.apply_status_report`
is the only place lifecycle state is written to the database, and it fires the
hooks configured in ``TOPOBANK_TASK_LIFECYCLE_HOOKS`` with ``(instance, report)``
so notification channels attach there rather than to any particular engine.

A ``STARTED`` report may be made as a *claim*: a conditional update that
exactly one worker wins. A worker that loses the claim must not run the work.
This closes the window in which two workers pick up the same row.

Files
-----

A completion report may carry a file manifest: a list of
:class:`~topobank.taskapp.status.FileEntry` items naming each file the run
produced and its location in the configured Django storage, with optional size
and content type. topobank translates the list into ``Manifest`` rows through
``ManifestSet.register_files``. topobank never lists a storage prefix to
discover output; the manager already knows what it wrote.

The Celery manager
------------------

:class:`topobank.taskapp.celery_manager.CeleryWorkflowManager` is the built-in
manager and topobank's original execution path. Its dependency resolution,
chord construction, memory admission control and lost-task reaper are its own
internals behind ``launch``. It keeps its bookkeeping on the row itself
(``task_id``, ``launcher_task_id``) and maps logical queue names onto broker
queues through ``CELERY_LOGICAL_QUEUE_MAP``.

Configuration
-------------

.. code:: python

    # Name of the manager new work is launched on
    TOPOBANK_WORKFLOW_MANAGER = "celery"

    # Additional managers, by name. Merged over the built-in Celery entry.
    TOPOBANK_WORKFLOW_MANAGERS = {
        "ray": "myproject.workflows.RayWorkflowManager",
    }

    # Import paths called with (instance, report) on every status report
    TOPOBANK_TASK_LIFECYCLE_HOOKS = [
        "myproject.events.publish_task_status",
    ]

Writing a manager
-----------------

A manager is a class with a ``name`` and three methods::

    class MyWorkflowManager:
        name = "mine"

        def launch(self, request, instance=None) -> LaunchHandle: ...
        def poll(self, handle, instance=None) -> RunInfo: ...
        def cancel(self, handle, instance=None) -> None: ...

``instance`` is the already-loaded row when the caller has it; managers that
keep their state elsewhere may ignore it. On completion the manager - or the
topobank code that observes its completion - calls
:func:`~topobank.taskapp.status.apply_status_report` with the outcome and the
files produced.
