Workflow managers
=================

topobank does not run workflows itself. It creates the record of a run - a
``WorkflowResult`` - applies its business rules (authorization,
de-duplication, permissions, ownership) and then hands the result to a
*workflow manager*. What happens next - queueing, dependency resolution,
fan-out, resource limits, which worker fleet runs the code - is the manager's
business. topobank neither knows nor cares whether a manager builds a DAG, when
it does so, or which engine executes it.

Descriptors and registries
--------------------------

Every workflow is tied to exactly one engine. A workflow manager therefore owns
a *registry* of the workflows it can run, and a workflow name resolves to a
manager and to that manager's *shim* for the workflow: a subclass of
:class:`~topobank.analysis.descriptor.WorkflowDescriptor` that tells topobank
what it needs to know without running anything - the name, the display name,
the accepted subject types, the pydantic ``Parameters`` model and the declared
``Outputs`` - and tells the manager whatever it needs to run the workflow. The
Celery manager's shim is
:class:`~topobank.analysis.celery.workflows.WorkflowImplementation`, which adds
the in-process implementation methods, their dependencies and a queue.

Plugins register a shim with the manager it targets::

    from topobank.analysis.celery.manager import registry

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

Managers are listed in settings, in priority order::

    TOPOBANK_WORKFLOW_MANAGERS = [
        "sds_api.workflows.RayWorkflowManager",
        "topobank.analysis.celery.manager.CeleryWorkflowManager",
    ]

The Celery manager is always available and is appended if not listed.
:func:`topobank.analysis.managers.resolve_workflow` asks the managers in order
and the first one that knows a name wins. This is how a workflow moves between
engines without changing its name: register it with the new manager and list
that manager first. Results launched earlier keep working, because every
result records which manager launched it.

Enumeration for the frontend is unchanged:
``topobank.analysis.registry.get_workflow_names()`` is the union over all
managers, and ``get_implementation(name=...)`` returns the resolved shim. Which
manager runs a workflow is not exposed through the API.

Launch, poll, cancel
--------------------

A manager implements three methods (:class:`topobank.analysis.managers.WorkflowManager`)::

    class MyWorkflowManager:
        name = "mine"
        registry = WorkflowRegistry()

        def launch(self, result, *, force=False) -> LaunchHandle: ...
        def poll(self, result) -> RunInfo: ...
        def cancel(self, result) -> None: ...

``submit_workflow`` resolves the result's workflow name to its manager, calls
``launch`` and stores the returned :class:`~topobank.analysis.managers.LaunchHandle`
in ``WorkflowResult.execution_handle``. The handle names the manager and holds
whatever that manager needs to find the run again (a Celery task id, a Ray job
id). ``poll`` and ``cancel`` receive the result and read its handle. A result
without a handle predates managers and belongs to Celery.

Managers are singletons created once from the settings list; a Ray manager
would hold its cluster client there.

Status
------

Managers report how a run is going through the status contract in
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
discover output; the manager already knows what it wrote.

The Celery manager
------------------

:class:`topobank.analysis.celery.manager.CeleryWorkflowManager` is the built-in
manager and topobank's original execution path. Its dependency resolution,
chord construction, memory admission control and lost-task reaper are its own
internals behind ``launch``. It keeps its bookkeeping on the result itself
(``task_id``, ``launcher_task_id``) and maps logical queue names onto broker
queues through ``CELERY_LOGICAL_QUEUE_MAP``.
