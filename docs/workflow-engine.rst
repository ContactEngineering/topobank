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
a *registry* of the workflows it can run, and a workflow name resolves to a
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

Status
------

Engines report how a run is going through the status contract in
:mod:`topobank.analysis.status`. A
:class:`~topobank.analysis.status.StatusReport` carries the task state and,
optionally, error and traceback, peak memory, per-stage timings, DOIs and the
list of files the run produced. :func:`~topobank.analysis.status.apply_status_report`
is the only place lifecycle state is written to the database, and it fires the
hooks configured in ``TOPOBANK_TASK_LIFECYCLE_HOOKS`` with ``(instance, report)``
so notification channels attach there rather than to any particular engine.

A ``STARTED`` report may be made as a *claim*: a conditional update that
exactly one worker wins. A worker that loses the claim must not run the work.
This closes the window in which two workers pick up the same result.

A completion report may carry a file manifest: a list of
:class:`~topobank.analysis.status.FileEntry` items naming each file the run
produced and its location in the configured Django storage, with optional size
and content type. topobank translates the list into ``Manifest`` rows through
``ManifestSet.register_files``. topobank never lists a storage prefix to
discover output; the engine already knows what it wrote.

The Celery engine
------------------

:class:`topobank.analysis.celery.engine.CeleryWorkflowEngine` is the built-in
engine and topobank's original execution path. Its dependency resolution,
chord construction, memory admission control and lost-task reaper are its own
internals behind ``launch``. It keeps its bookkeeping on the result itself
(``task_id``, ``launcher_task_id``) and maps logical queue names onto broker
queues through ``CELERY_LOGICAL_QUEUE_MAP``.
