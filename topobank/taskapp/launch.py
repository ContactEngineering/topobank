"""
The launch API: how topobank hands work to a workflow management system.

topobank owns the *what*: a row of a :class:`~topobank.taskapp.models.TaskStateModel`
subclass (a `WorkflowResult`, a `Topography` whose cache needs refreshing, a ZIP
container to build) together with the business rules that created it -
authorization, de-duplication, permissions, ownership. Everything after that
point is the *how*, and the how belongs to a workflow manager: queueing,
dependency resolution, fan-out, retries, resource limits, worker fleets. topobank
does not care whether a manager builds a DAG, when it does so, or whether it
uses Celery, Ray, Step Functions or a thread pool.

The contract between the two sides is deliberately small:

``launch``
    topobank builds a :class:`LaunchRequest` - a self-contained job envelope
    carrying everything a manager may need without a database lookup: which row,
    which workflow, its parameters, who owns it, where output goes - and hands it
    to :meth:`WorkflowManager.launch`. The manager returns a
    :class:`LaunchHandle`, an opaque, JSON-serialisable reference to the run that
    topobank stores on the row.

``poll`` / ``cancel``
    topobank asks a manager about a run, or asks it to stop one, using the stored
    handle. A handle names the manager that produced it, so rows launched under
    one manager stay pollable after the default manager changes. This is what
    lets two managers run side by side during a migration.

``report``
    The manager tells topobank how a run is going through the status contract in
    :mod:`topobank.taskapp.status`. That is the *only* way lifecycle state
    reaches the database. A completion report may carry a file manifest - a
    plain list of the files the run produced - which topobank translates into
    `Manifest` rows. topobank never lists a storage prefix to discover output.

The Celery manager (:mod:`topobank.taskapp.celery_manager`) implements the
contract over the tasks that have always driven topobank. Its dependency
resolution, chord construction and memory admission are its own business and
live behind ``launch``.

Managers are configured in settings::

    TOPOBANK_WORKFLOW_MANAGER = "celery"          # name of the default manager
    TOPOBANK_WORKFLOW_MANAGERS = {                # name -> import path
        "celery": "topobank.taskapp.celery_manager.CeleryWorkflowManager",
    }

Entries given in ``TOPOBANK_WORKFLOW_MANAGERS`` are merged over the built-in
defaults, so a deployment can add a manager without repeating the Celery entry.
"""

import logging
from typing import Any, Dict, List, Literal, Optional, Protocol, runtime_checkable

import pydantic
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

_log = logging.getLogger(__name__)

#: Managers known without any configuration. ``TOPOBANK_WORKFLOW_MANAGERS`` is
#: merged over this mapping.
DEFAULT_WORKFLOW_MANAGERS = {
    "celery": "topobank.taskapp.celery_manager.CeleryWorkflowManager",
}

#: Name of the manager used when ``TOPOBANK_WORKFLOW_MANAGER`` is not set.
DEFAULT_WORKFLOW_MANAGER = "celery"


class LaunchRequest(pydantic.BaseModel):
    """
    The job envelope: everything a manager may need to run one row of work.

    The envelope is built by topobank from the row and is self-contained on
    purpose. A manager that runs inside the Django process (Celery) is free to
    ignore most of it and load the row; a manager that runs elsewhere gets the
    routing context - owner, user, parent - without a database connection.

    Two kinds of work exist. A ``workflow`` is a `WorkflowResult`: it names a
    registered workflow and its parameters, and the manager is expected to run
    that workflow, including whatever dependency resolution the workflow
    declares. A ``task`` is any other :class:`~topobank.taskapp.models.TaskStateModel`
    (a measurement cache refresh, a ZIP export): the manager is expected to call
    the row's ``task_worker`` with ``args`` and ``task_kwargs``.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    kind: Literal["workflow", "task"]

    #: The row this request is about, as ``"<app_label>.<model_name>"`` and pk.
    model: str
    pk: int

    #: Re-run even if the row already holds a result.
    force: bool = False

    #: Logical resource hint (e.g. ``"analysis"``, ``"manager"``). Managers may
    #: map it onto a queue, a node pool or nothing at all.
    queue: Optional[str] = None

    #: Storage prefix the run should write its output under. Informational for
    #: managers that write through the Django storage layer.
    storage_prefix: Optional[str] = None

    # --- routing context -------------------------------------------------
    organization_id: Optional[int] = None
    user_id: Optional[int] = None
    #: Set when this run was requested as a dependency of another row.
    parent_id: Optional[int] = None

    # --- workflow envelope (kind == "workflow") ------------------------------
    workflow_name: Optional[str] = None
    kwargs: Dict[str, Any] = pydantic.Field(default_factory=dict)
    subject_hash: Optional[str] = None

    # --- task envelope (kind == "task") --------------------------------------
    args: List[Any] = pydantic.Field(default_factory=list)
    task_kwargs: Dict[str, Any] = pydantic.Field(default_factory=dict)

    @property
    def app_label(self) -> str:
        return self.model.split(".", 1)[0]

    @property
    def model_name(self) -> str:
        return self.model.split(".", 1)[1]


class LaunchHandle(pydantic.BaseModel):
    """
    Opaque, serialisable reference to a launched run.

    ``manager`` names the :class:`WorkflowManager` that produced the handle and
    is the only field topobank interprets: it selects the manager that
    :func:`poll` and :func:`cancel` are routed to. ``data`` is the manager's
    own, e.g. a Celery task id, a Step Functions execution ARN, a Ray job id.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    manager: str
    data: Dict[str, Any] = pydantic.Field(default_factory=dict)


class RunInfo(pydantic.BaseModel):
    """
    What a manager knows about a run when polled.

    ``state`` uses the two-letter codes of
    :class:`~topobank.taskapp.models.TaskStateModel` (``"pe"``, ``"st"``,
    ``"su"``, ``"fa"``, ...). ``progress`` is a percentage or ``None`` when the
    manager cannot tell. ``messages`` are the progress messages of the run and
    its children, if the manager tracks them. ``error`` is set when the manager
    holds an error the run did not report itself, e.g. because its process died.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    state: str
    progress: Optional[float] = None
    messages: Optional[List[str]] = None
    error: Optional[str] = None


@runtime_checkable
class WorkflowManager(Protocol):
    """
    The launch contract a workflow management system implements.

    All three methods accept the already-loaded row as ``instance`` when the
    caller has it. Managers that keep bookkeeping on the row itself (the Celery
    manager does) may use it and skip a query; managers that do not may ignore
    it.
    """

    #: Short, stable name recorded in every handle this manager produces.
    name: str

    def launch(self, request: LaunchRequest, instance=None) -> LaunchHandle:
        """Start the work described by ``request`` and return a handle to it."""
        ...

    def poll(self, handle: LaunchHandle, instance=None) -> RunInfo:
        """Return what the manager knows about the run behind ``handle``."""
        ...

    def cancel(self, handle: LaunchHandle, instance=None) -> None:
        """Stop the run behind ``handle`` if it is still running."""
        ...


def _manager_registry() -> Dict[str, str]:
    registry = dict(DEFAULT_WORKFLOW_MANAGERS)
    registry.update(getattr(settings, "TOPOBANK_WORKFLOW_MANAGERS", {}) or {})
    return registry


def get_default_manager_name() -> str:
    return getattr(settings, "TOPOBANK_WORKFLOW_MANAGER", DEFAULT_WORKFLOW_MANAGER)


def get_workflow_manager(name: Optional[str] = None) -> WorkflowManager:
    """
    Return the workflow manager called ``name``, or the default manager.

    Managers are instantiated on every call; they are expected to be cheap,
    stateless objects. Configuration lives in Django settings, so tests can
    swap managers with ``override_settings``.
    """
    if name is None:
        name = get_default_manager_name()
    registry = _manager_registry()
    try:
        path = registry[name]
    except KeyError:
        raise ImproperlyConfigured(
            f"No workflow manager named {name!r}. Known managers: "
            f"{sorted(registry)}. Add it to TOPOBANK_WORKFLOW_MANAGERS."
        )
    manager = import_string(path)() if isinstance(path, str) else path()
    if getattr(manager, "name", None) != name:
        raise ImproperlyConfigured(
            f"Workflow manager {path!r} reports name {getattr(manager, 'name', None)!r} "
            f"but is registered as {name!r}."
        )
    return manager


def launch(instance, *, force: bool = False, **request_fields) -> LaunchHandle:
    """
    Launch the work for ``instance`` on the default manager and record the handle.

    The row is asked to describe itself through ``build_launch_request`` (see
    :class:`~topobank.taskapp.models.TaskStateModel`); ``request_fields``
    override or extend that envelope, e.g. ``args`` and ``task_kwargs`` for a
    plain task. The returned handle is also stored in ``instance.execution_handle``.

    This is the single dispatch point of topobank. It is typically called from a
    ``transaction.on_commit`` hook so that the row a manager will read is
    visible before any worker looks for it.
    """
    request = instance.build_launch_request(force=force, **request_fields)
    manager = get_workflow_manager()
    _log.debug(
        "Launching %s %s on workflow manager %r", request.model, request.pk, manager.name
    )
    handle = manager.launch(request, instance=instance)
    instance.execution_handle = handle.model_dump()
    instance.save(update_fields=["execution_handle"])
    return handle
