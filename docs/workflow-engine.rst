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

On the topobank side, a workflow is referred to by name through the
:class:`~topobank.analysis.models.Workflow` value object. It is not a model -
there is no table of workflows - and it holds no knowledge of its own: it
resolves its name to the registered descriptor (``descriptor``, or
``implementation`` for a lookup that yields ``None`` instead of raising) and
delegates every question the API asks - ``display_name``,
``get_kwargs_schema``, ``get_default_kwargs``, ``get_outputs_schema``,
``clean_kwargs``, ``has_implementation`` - to it. Asking about a workflow no
engine knows raises ``WorkflowNotRegisteredException``; only ``display_name``
falls back to the name, because results outlive the workflows that produced
them and still need a label. Running a workflow is not on this class at all.

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

Result requests and reuse
-------------------------

A result comes into being in one of two ways: a user submits a workflow, or a
workflow declares that it needs another workflow's result first. Both are the
same request - *this workflow, on this subject, with these parameters* - and
both are spelled as a :class:`~topobank.analysis.workflows.ResultRequest`::

    ResultRequest(workflow_name="myplugin.my_workflow", subject=topography, kwargs={"n": 8})
    ResultRequest(workflow_name="myplugin.my_workflow", surfaces=[s1, s2])

A request names either a single ``subject`` (a topography, surface or tag,
stored on the result's foreign keys) or a set of ``surfaces`` (stored on the
result's ``surfaces`` relation and addressed by ``subject_hash``). Building a
request touches neither the registry nor the database; parameters are
validated and completed against the workflow's ``Parameters`` model when the
request is resolved. The Celery shim's dependency methods return a dictionary
of requests; ``WorkflowDefinition(subject=, function=Workflow(...), kwargs=)``
is the deprecated spelling of the same thing and still works.

:func:`topobank.analysis.store.find_or_create` turns a request into a
``WorkflowResult`` row. It is the one place results are created, and it
serializes the check-then-create for one (workflow, subject, parameters)
triple under an advisory lock so that concurrent identical requests yield one
row. What differs between callers is only *when an existing row may stand in
for a new one*, which they say with a ``Reuse`` policy:

``Reuse.VIABLE``
    Reuse a result that is pending, running or finished successfully; when
    none exists, delete the failed, unnamed leftovers for the triple and
    create a fresh row. This is what ``Workflow.submit`` and
    ``submit_for_surfaces`` want: the newest viable answer, computed once.
    ``submit`` additionally restricts candidates to results the user may see
    (``for_user``), and tag results to the user's own.
``Reuse.FINISHED``
    Reuse whatever exists, finished or not, and report whether it still has
    to run. A dependency that failed once is reused, not retried behind the
    parent's back. This is what the Celery engine's dependency resolution
    wants; new dependency rows share the parent's permissions and owner and
    record the parent in their metadata.
``Reuse.NEVER``
    Always create, leaving existing rows alone (``ignore_existing``).

``force`` overrides either judgement: under ``VIABLE`` it creates anew, under
``FINISHED`` it marks a reused row as needing a run. The function returns a
``Found`` triple - the row, whether it was created, and whether it
``needs_run`` - and dispatches nothing. The caller decides: ``Workflow.submit``
registers ``submit_workflow`` in an ``on_commit`` hook exactly when
``needs_run`` is set; dependency resolution puts the row in the set the engine
schedules.

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
    The files the run produced, as :class:`~topobank.analysis.status.ManifestEntry`
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

File registration
-----------------

A result's output is a set of files in a folder - a ``ManifestSet`` - and
topobank knows a file only through its ``Manifest`` row: the file name, where
the file lives in the configured Django storage, its kind, size and content
type, and ``confirmed_at``, the moment topobank learned that the file is
really there. ``get_valid_files`` returns confirmed manifests only; an
unconfirmed manifest is a reservation, not a file. topobank never lists a
storage prefix to find out what a folder contains - listing object storage is
slow and brittle - so a file that has no manifest does not exist as far as
topobank is concerned, whatever is in the bucket.

Manifests come into being in two ways, and an engine uses whichever fits
where its workers run:

**In-process writes.** A workflow running inside a Django process - every
workflow on the Celery engine - writes through the folder itself:
``ManifestSet.save_file``, ``save_json``, ``save_xarray``. Each call stores
the bytes and, in the same step, creates or replaces the ``Manifest`` row and
stamps ``confirmed_at``. The row exists the moment the file does. The Celery
engine's success report therefore carries no ``files``; there is nothing left
to register when it arrives.

**The engine's file manifest.** An engine whose workers do not touch Django
writes to storage on its own and, with its ``SUCCESS`` report, hands topobank
the list of what it wrote as
:class:`~topobank.analysis.status.ManifestEntry` items. Each entry names the
file and its storage location (the ``name`` a ``FileField`` would hold, not a
URL) and, optionally, kind, size and content type.
:func:`~topobank.analysis.status.apply_status_report` passes the list to
``ManifestSet.register_files``, which, for each entry, finds the manifest with
that file name or creates one, points it at the reported location, copies the
attributes it was given and stamps ``confirmed_at``. Registering is
idempotent: reporting the same file twice updates the row in place, and a
file that was also written in-process under the same name is updated, not
duplicated.

What registration does *not* do defines its limits:

- It happens on ``SUCCESS`` only. A ``FAILURE`` report may carry ``files``
  but they are ignored; nothing is recorded for a run that did not finish.
- It never removes a manifest. A file recorded by an earlier run that the new
  run did not report stays in the folder. The folder is the union of
  everything ever registered, until ``remove_files`` clears it.
- It does not check storage. A reported location that does not exist yields
  a confirmed manifest whose file cannot be opened. The engine's list is
  taken as the truth about what was written, because the engine is the only
  party that knows.

Together with the lifecycle rule that a terminal state is written exactly
once, this means the files of a result are settled at the same moment as its
state: whoever sees ``SUCCESS`` sees the complete set of manifests the run
reported. What happens to files written by a run that never reaches
``SUCCESS`` is a question for the engine - see the discussion of partial
output under `Lifecycle of a result`_, step 5.

Lifecycle of a result
---------------------

A ``WorkflowResult`` moves through the states of ``TaskStateModel``:

``NOTRUN`` → ``PENDING`` → (``PENDING_DEPENDENCIES``) → ``STARTED`` → ``SUCCESS`` | ``FAILURE``

Who writes what, and when:

1. **Creation and submission (topobank, API process).** ``Workflow.submit``
   and ``submit_for_surfaces`` check authorization and build a
   ``ResultRequest``; ``find_or_create`` applies the reuse policy under an
   advisory lock and creates or reuses the result, with permissions and
   ownership. A new row goes through ``set_pending_state``, which puts it in
   ``PENDING``, stamps ``task_submission_time`` and clears error, traceback,
   timestamps and the ``execution_handle``. The engine is only involved from
   a ``transaction.on_commit`` hook, so the row is visible to whatever worker
   the engine starts before that worker looks for it.

2. **Launch (topobank → engine).** ``submit_workflow`` resolves the workflow
   name to its engine and calls ``launch``; the returned handle is stored in
   ``execution_handle``. If no engine knows the workflow, the result is set to
   ``FAILURE`` with a message - an exception here would vanish in the
   ``on_commit`` hook and leave the result pending forever. ``PENDING`` is
   therefore the only state in which a result has no handle, apart from results
   that predate engines.

3. **Start (engine).** The engine reports ``STARTED``, which sets
   ``task_start_time`` if not set. It should do so as a *claim* - see
   `The STARTED claim`_ below: the transition is made only if the result is
   still waiting, and a worker for which it is not made must not run the
   work. ``PENDING_DEPENDENCIES`` is an intermediate state an engine may
   report while it waits for dependencies it resolves itself; topobank treats
   it as pending.

4. **Progress (engine, optional).** Progress is not part of the status
   contract; it is transient and is answered by ``poll``. Engines that track
   progress return it in :class:`~topobank.analysis.engines.RunInfo`
   (``progress`` as a percentage, ``messages``).

5. **Completion (engine).** A ``SUCCESS`` or ``FAILURE`` report sets
   ``task_end_time`` and, on success, registers the reported files (see
   `File registration`_). These two states are *terminal*: once a result
   carries one, topobank trusts the row and never asks the engine again. A
   run that dies after writing some of its files leaves partial output
   behind: recorded and confirmed if the files were written in-process,
   unrecorded in storage if a remote engine had not yet reported them. No
   report ever removes files, so the folder of a failed result is whatever
   the run managed to write before it failed.

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

What the engine must guarantee is small: claim the result (report
``STARTED`` with ``claim=True``) before doing work and stop if the claim is
lost, report exactly one terminal state, and report failures it learns about
out of band - a worker that died, a job the cluster killed - so that the
reconciliation in step 6 has something to see.

The STARTED claim
~~~~~~~~~~~~~~~~~

The same result can reach two workers. A dependency shared by two parents is
scheduled by both; a forced re-submission is dispatched while the previous
run is still going; a broker redelivers a message it believes lost. Without
a rule, both workers run the same workflow on the same row and the second one
overwrites whatever the first wrote.

The rule is that ``STARTED`` is not a notification but a *claim* on the
result, and exactly one worker wins it. A claim is made with
``apply_status_report(result, StatusReport(state=STARTED), claim=True)``,
which does not save the row but issues a single conditional update::

    UPDATE analysis_workflowresult
       SET task_state = 'STARTED', task_start_time = now(), ...
     WHERE id = <result>
       AND task_state NOT IN ('STARTED', 'SUCCESS', 'FAILURE')

The condition is what makes it a claim: the transition only happens while the
result is still waiting (``PENDING``, ``PENDING_DEPENDENCIES`` or ``RETRY``).
The database serializes concurrent updates to a row, so of two workers issuing
this statement, one changes the row and the other finds that nothing matched.
``apply_status_report`` returns ``True`` to the winner and ``False`` to the
loser, after refreshing the loser's instance so it sees the true state.

A worker that loses the claim must not run the workflow. It has learned that
another worker is already running the result (``STARTED``) or that the result
has been completed in the meantime (``SUCCESS`` or ``FAILURE``); in both cases
the right thing is to do nothing and report nothing, because any terminal
report it made would be about a run that never happened. The Celery engine's
``execute_workflow`` returns at this point.

Two consequences follow. A result that is already ``STARTED`` is never
claimed again, so a stuck run blocks re-runs until something reports its
failure - which is why an engine must report failures it learns about out
of band (a dead worker, a revoked task; the Celery engine does this from its
``task_revoked`` and ``task_failure`` signal handlers and its lost-task
reaper). And a forced re-run goes through ``set_pending_state`` first, which
puts the row back to ``PENDING`` and thereby makes it claimable again; the
previous run, if still alive, then loses nothing but reports into a row that
was re-pended, which is the existing (and accepted) behaviour of a forced
re-submission.

The Celery engine
------------------

:class:`topobank.analysis.celery.engine.CeleryWorkflowEngine` is the built-in
engine and topobank's original execution path. Its dependency resolution,
chord construction, memory admission control and lost-task reaper are its own
internals behind ``launch``. It keeps its bookkeeping on the result itself
(``task_id``, ``launcher_task_id``) and maps logical queue names onto broker
queues through ``CELERY_LOGICAL_QUEUE_MAP``.

Its tasks live in :mod:`topobank.analysis.celery.tasks`: ``schedule_workflow``
resolves a result's declared dependencies (``get_dependencies`` on the shim,
``find_or_create`` with ``Reuse.FINISHED`` for each) and, when some still have
to run, builds a chord whose callback is ``execute_workflow``, which claims the
result, runs the workflow in-process and reports the outcome through the
status contract. The tasks keep their historical ``topobank.analysis.tasks.*``
names, and :mod:`topobank.analysis.tasks` re-exports them, so queued messages,
per-task Celery settings and downstream code matching on task names are
unaffected by the move.

Running a workflow in-process is
:func:`topobank.analysis.celery.workflows.run_workflow`: given a result, it
looks the shim up in the Celery registry, binds it to the result's parameters
and routes to the implementation method for the result's subject - by surface
count for a surface set, by subject model otherwise. This routing is the
Celery shim's way of running and belongs to this engine; ``WorkflowResult``
and ``Workflow`` know nothing of it. Another engine would ship the result's
identity to its own workers and run whatever its shim describes.
