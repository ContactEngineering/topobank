Workflow engines
=================

topobank does not run workflows itself. It creates the record of a run - a
``WorkflowResult`` - applies its business rules (authorization,
de-duplication, permissions, ownership) and then hands the result to a
*workflow engine*. What happens next - queueing, dependency resolution,
fan-out, resource limits, which worker fleet runs the code - is the engine's
business. topobank neither knows nor cares whether an engine builds a DAG, when
it does so, or which engine executes it.

Descriptors and registries
--------------------------

Every workflow is tied to exactly one engine. A workflow engine therefore owns
a *registry* of the workflows it can run, and a workflow name resolves to an
engine and to that engine's *shim* for the workflow: a subclass of
:class:`~topobank.analysis.descriptor.WorkflowDescriptor` that tells topobank
what it needs to know without running anything - the name, the display name,
the accepted subject types, the pydantic ``Parameters`` model and the declared
``Outputs`` - and tells the engine whatever it needs to run the workflow. The
Celery engine's shim is
:class:`~topobank.analysis.celery.workflows.WorkflowImplementation`, which adds
the in-process implementation methods, their dependencies and a queue.

Plugins register a shim with the engine it targets::

    from topobank.analysis.celery.engine import registry

    @registry.register
    class MyWorkflow(WorkflowImplementation):
        class Meta:
            name = "myplugin.my_workflow"
            display_name = "My workflow"
            implementations = {Topography: "topography_implementation"}
        ...

``topobank.analysis.registry.register_implementation`` remains as an alias for
the Celery registry, so existing plugins keep working.

Resolution
----------

Engines are listed in settings, in priority order::

    TOPOBANK_WORKFLOW_ENGINES = [
        "sds_api.workflows.RayWorkflowEngine",
        "topobank.analysis.celery.engine.CeleryWorkflowEngine",
    ]

The Celery engine is always available and is appended if not listed.
:func:`topobank.analysis.engines.resolve_workflow` asks the engines in order
and the first one that knows a name wins. This is how a workflow moves between
engines without changing its name: register it with the new engine and list
that engine first. Results launched earlier keep working, because every
result records which engine launched it.

Enumeration for the frontend is unchanged:
``topobank.analysis.registry.get_workflow_names()`` is the union over all
engines, and ``get_implementation(name=...)`` returns the resolved shim. Which
engine runs a workflow is not exposed through the API.

Launch, poll, cancel
--------------------

An engine implements three methods (:class:`topobank.analysis.engines.WorkflowEngine`)::

    class MyWorkflowEngine:
        name = "mine"
        registry = WorkflowRegistry()

        def launch(self, result, *, force=False) -> LaunchHandle: ...
        def poll(self, result) -> RunInfo: ...
        def cancel(self, result) -> None: ...

``submit_workflow`` resolves the result's workflow name to its engine, calls
``launch`` and stores the returned :class:`~topobank.analysis.engines.LaunchHandle`
in ``WorkflowResult.execution_handle``. The handle names the engine and holds
whatever that engine needs to find the run again (a Celery task id, a Ray job
id). ``poll`` and ``cancel`` receive the result and read its handle. A result
without a handle predates engines and belongs to Celery.

Engines are singletons created once from the settings list; a Ray engine
would hold its cluster client there.

Status contract
---------------

Engines report how a run is going through the status contract in
:mod:`topobank.analysis.status`. A
:class:`~topobank.analysis.status.StatusReport` carries the task state and,
optionally:

``error`` and ``traceback``
    Shown to the user on failure. NUL bytes are stripped before storage.
``memory``
    Peak memory of the run in bytes (``task_memory``). Surfaced to the
    frontend and, for the Celery engine, learned from for admission control.
``timer``
    Per-stage timings as produced by ``muTimer.Timer.to_dict()``
    (``task_timer``). On failure, the partial timings up to the failure are
    worth reporting: they distinguish one stalled stage from many slow ones.
``dois``
    DOIs of the methods the run used.
``files``
    The files the run produced, as :class:`~topobank.analysis.status.FileEntry`
    items: the file name, its location in the configured Django storage (the
    ``name`` a ``FileField`` would hold, not a URL) and, optionally, size and
    content type. Applied on success only. topobank translates the list into
    ``Manifest`` rows through ``ManifestSet.register_files``; registering is
    idempotent. topobank never lists a storage prefix to discover output - the
    engine already knows what it wrote.
``start_time`` and ``end_time``
    Filled in by topobank when omitted. An engine that reports from a signal
    handler with its own clock (the Celery engine does) may pass them.

:func:`~topobank.analysis.status.apply_status_report` is the only place
lifecycle state is written to the database. Every field of the report that is
not ``None`` is applied; everything else is left alone, so a report can carry
as little as a state change. The Celery engine calls it in-process from its
worker; an engine running elsewhere hands its reports to whatever topobank code
observes it (a poll, a completion event) and that code calls the same function.

After every applied report, the hooks configured in
``TOPOBANK_TASK_LIFECYCLE_HOOKS`` (import paths) are called with
``(instance, report)``. Notification channels - server-sent events, audit
logs - attach here rather than to any particular engine. A failing hook is
logged and never blocks the report: status must reach the database even if a
notification channel is down.

Lifecycle of a result
---------------------

A ``WorkflowResult`` moves through the states of ``TaskStateModel``:

``NOTRUN`` → ``PENDING`` → (``PENDING_DEPENDENCIES``) → ``STARTED`` → ``SUCCESS`` | ``FAILURE``

Who writes what, and when:

1. **Creation and submission (topobank, API process).** ``Workflow.submit``
   and ``submit_for_surfaces`` apply the business rules - authorization,
   de-duplication under an advisory lock, permissions, ownership - and create
   or reuse the result. ``set_pending_state`` puts it in ``PENDING``, stamps
   ``task_submission_time``, clears error, traceback, timestamps and the
   ``execution_handle``. The engine is only involved from a
   ``transaction.on_commit`` hook, so the row is visible to whatever worker the
   engine starts before that worker looks for it.

2. **Launch (topobank → engine).** ``submit_workflow`` resolves the workflow
   name to its engine and calls ``launch``; the returned handle is stored in
   ``execution_handle``. If no engine knows the workflow, the result is set to
   ``FAILURE`` with a message - an exception here would vanish in the
   ``on_commit`` hook and leave the result pending forever. ``PENDING`` is
   therefore the only state in which a result has no handle, apart from results
   that predate engines.

3. **Start (engine).** The engine reports ``STARTED``, which sets
   ``task_start_time`` if not set. It should do so as a *claim*
   (``apply_status_report(..., claim=True)``): a conditional update that only
   succeeds while the result is waiting. A worker that loses the claim - because
   another worker already runs or finished the result - must not run the work.
   This closes the window in which two workers pick up the same result.
   ``PENDING_DEPENDENCIES`` is an intermediate state an engine may report while
   it waits for dependencies it resolves itself; topobank treats it as pending.

4. **Progress (engine, optional).** Progress is not part of the status
   contract; it is transient and is answered by ``poll``. Engines that track
   progress return it in :class:`~topobank.analysis.engines.RunInfo`
   (``progress`` as a percentage, ``messages``).

5. **Completion (engine).** A ``SUCCESS`` or ``FAILURE`` report sets
   ``task_end_time`` and, on success, registers the reported files. These two
   states are *terminal*: once a result carries one, topobank trusts the row
   and never asks the engine again.

6. **Reconciliation (topobank, on read).** While a result is not terminal,
   ``get_task_state`` compares the self-reported state with what ``poll``
   returns. The engine wins when it reports a failure the run could not report
   itself (a killed worker, a revoked task). ``PENDING`` with nothing known to
   the engine is the launch gap: it is reported as pending for
   ``COMMIT_EXPIRATION`` (30 s) after ``task_submission_time`` and as a failure
   afterwards, on the assumption that the ``on_commit`` hook never ran.
   ``get_task_error`` likewise adopts an error the engine holds and records the
   failure. Reads never contact the engine for a terminal result.

7. **Re-submission.** ``submit_again`` goes through ``set_pending_state`` and
   a fresh ``launch``: a new handle, possibly on a different engine if the
   workflow moved in the meantime. Results that already reached ``SUCCESS`` or
   ``FAILURE`` are only re-run when forced.

8. **Cancellation.** ``cancel_task`` asks the engine named in the handle to
   stop the run. The engine reports the resulting ``FAILURE`` like any other
   (the Celery engine does so from its ``task_revoked`` signal handler).
   Deleting a result cancels its run first.

What the engine must guarantee is small: report ``STARTED`` (as a claim)
before doing work, report exactly one terminal state, and report failures it
learns about out of band - a worker that died, a job the cluster killed - so
that the reconciliation in step 6 has something to see.

The Celery engine
------------------

:class:`topobank.analysis.celery.engine.CeleryWorkflowEngine` is the built-in
engine and topobank's original execution path. Its dependency resolution,
chord construction, memory admission control and lost-task reaper are its own
internals behind ``launch``. It keeps its bookkeeping on the result itself
(``task_id``, ``launcher_task_id``) and maps logical queue names onto broker
queues through ``CELERY_LOGICAL_QUEUE_MAP``.

Its tasks live in :mod:`topobank.analysis.celery.tasks`: ``schedule_workflow``
resolves a result's declared dependencies and, when some still have to run,
builds a chord whose callback is ``execute_workflow``, which claims the result,
runs the shim's implementation in-process and reports the outcome through the
status contract. The tasks keep their historical ``topobank.analysis.tasks.*``
names, and :mod:`topobank.analysis.tasks` re-exports them, so queued messages,
per-task Celery settings and downstream code matching on task names are
unaffected by the move.
