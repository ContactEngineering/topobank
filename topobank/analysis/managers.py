"""
Workflow managers: the systems topobank hands workflows to.

topobank owns the *what*: a `WorkflowResult` row together with the business
rules that created it - authorization, de-duplication, permissions, ownership.
Everything after that is the *how*, and the how belongs to a workflow manager:
queueing, dependency resolution, fan-out, retries, resource limits, worker
fleets. topobank does not care whether a manager builds a DAG, when it does so,
or whether it uses Celery, Ray or a thread pool.

Each manager owns a :class:`WorkflowRegistry` of the workflows it can run. A
workflow implementation is specific to one engine, so a workflow name resolves
to exactly one manager and to that manager's *shim*: a
:class:`~topobank.analysis.descriptor.WorkflowDescriptor` subclass that gives
topobank the parameter model, display name and accepted subjects, and gives the
manager whatever it needs to run the thing. Resolution is by name over the
configured managers, in order::

    TOPOBANK_WORKFLOW_MANAGERS = [
        "topobank.analysis.celery_manager.CeleryWorkflowManager",
        "sds_api.workflows.RayWorkflowManager",
    ]

If two managers register the same name, the one listed first wins. This is how
a workflow moves between engines without changing its name: register it with
the new manager and list that manager first; rows launched earlier keep working
because each row records which manager launched it.

The contract a manager implements is small:

``launch``
    Start the workflow behind a `WorkflowResult` and return a
    :class:`LaunchHandle`, an opaque, JSON-serialisable reference that names
    the manager and carries whatever the manager needs to find the run again.
    topobank stores it on the row.

``poll`` / ``cancel``
    Report what the manager knows about a row's run, or stop it. Both receive
    the row and read its stored handle.

``report``
    Managers tell topobank how a run is going through the status contract in
    :mod:`topobank.analysis.status`; that is the only path by which lifecycle
    state reaches the database.

Managers are singletons, created once from the settings list. The Celery
manager (:mod:`topobank.analysis.celery_manager`) is topobank's original
execution path behind this interface and is always available.
"""

import logging
from typing import Any, Dict, List, Optional, Protocol, Tuple, Type, runtime_checkable

import pydantic
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from .descriptor import WorkflowDescriptor

_log = logging.getLogger(__name__)

#: Import path of the built-in Celery manager. Always part of the manager list;
#: deployments that do not configure ``TOPOBANK_WORKFLOW_MANAGERS`` get it alone.
CELERY_WORKFLOW_MANAGER = "topobank.analysis.celery_manager.CeleryWorkflowManager"

#: Name of the manager that owns rows launched before handles existed.
LEGACY_MANAGER_NAME = "celery"


class LaunchHandle(pydantic.BaseModel):
    """
    Opaque, serialisable reference to a launched run.

    ``manager`` names the :class:`WorkflowManager` that produced the handle and
    is the only field topobank interprets: it selects the manager that
    ``poll`` and ``cancel`` are routed to. ``data`` is the manager's own, e.g.
    a Celery task id, a Ray job id, a Step Functions execution ARN.
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


class WorkflowRegistry:
    """
    The workflows one manager can run, by name.

    Plugins register their shims explicitly with the manager they target::

        from topobank.analysis.celery_manager import registry

        @registry.register
        class MyWorkflow(WorkflowImplementation):
            ...

    Registering a name twice replaces the earlier entry; the last registration
    wins, which lets a plugin override a built-in workflow.
    """

    def __init__(self):
        self._by_name: Dict[str, Type[WorkflowDescriptor]] = {}

    def register(self, descriptor_class):
        """Register a descriptor (shim) class. Usable as a decorator."""
        meta = getattr(descriptor_class, "Meta", None)
        name = getattr(meta, "name", None)
        if not name:
            raise ImproperlyConfigured(
                f"{descriptor_class!r} cannot be registered: it has no Meta.name."
            )
        if not getattr(meta, "display_name", None):
            raise ImproperlyConfigured(
                f"{descriptor_class!r} cannot be registered: it has no Meta.display_name."
            )
        self._by_name[name] = descriptor_class
        return descriptor_class

    def unregister(self, name: str) -> None:
        self._by_name.pop(name, None)

    def get(self, name: str) -> Optional[Type[WorkflowDescriptor]]:
        return self._by_name.get(name)

    def get_by_display_name(self, display_name: str) -> Optional[Type[WorkflowDescriptor]]:
        for descriptor in self._by_name.values():
            if descriptor.Meta.display_name == display_name:
                return descriptor
        return None

    def names(self) -> List[str]:
        return list(self._by_name)

    def __contains__(self, name) -> bool:
        return name in self._by_name

    def __len__(self) -> int:
        return len(self._by_name)


@runtime_checkable
class WorkflowManager(Protocol):
    """The contract a workflow management system implements."""

    #: Short, stable name recorded in every handle this manager produces.
    name: str

    #: The workflows this manager can run.
    registry: WorkflowRegistry

    def launch(self, result, *, force: bool = False) -> LaunchHandle:
        """Start the workflow behind ``result`` and return a handle to the run."""
        ...

    def poll(self, result) -> RunInfo:
        """Return what the manager knows about the run behind ``result``."""
        ...

    def cancel(self, result) -> None:
        """Stop the run behind ``result`` if it is still running."""
        ...


# --- Singleton managers ---------------------------------------------------

_managers: Optional[List[WorkflowManager]] = None


def _manager_paths() -> List[str]:
    paths = list(getattr(settings, "TOPOBANK_WORKFLOW_MANAGERS", None) or [])
    if CELERY_WORKFLOW_MANAGER not in paths:
        # The Celery manager is always available; if a deployment does not list
        # it, it comes last so that configured managers take priority.
        paths.append(CELERY_WORKFLOW_MANAGER)
    return paths


def get_workflow_managers() -> List[WorkflowManager]:
    """
    The configured managers, in priority order. Instantiated once.

    The list is rebuilt when ``TOPOBANK_WORKFLOW_MANAGERS`` changes, so tests
    can swap managers with ``override_settings``.
    """
    global _managers
    if _managers is None:
        managers = []
        seen = set()
        for path in _manager_paths():
            manager = import_string(path)()
            name = getattr(manager, "name", None)
            if not name:
                raise ImproperlyConfigured(f"Workflow manager {path!r} has no name.")
            if name in seen:
                raise ImproperlyConfigured(
                    f"Two workflow managers are called {name!r}; names must be unique."
                )
            seen.add(name)
            managers.append(manager)
        _managers = managers
    return list(_managers)


def reset_workflow_managers() -> None:
    """Forget the instantiated managers; the next lookup rebuilds them."""
    global _managers
    _managers = None


def get_workflow_manager(name: str) -> WorkflowManager:
    """Return the manager called ``name``."""
    for manager in get_workflow_managers():
        if manager.name == name:
            return manager
    raise ImproperlyConfigured(
        f"No workflow manager named {name!r}. Known managers: "
        f"{[m.name for m in get_workflow_managers()]}. Add it to TOPOBANK_WORKFLOW_MANAGERS."
    )


# --- Resolution -----------------------------------------------------------


def resolve_workflow(name: str) -> Optional[Tuple[WorkflowManager, Type[WorkflowDescriptor]]]:
    """
    Resolve a workflow name to ``(manager, descriptor)``, or ``None``.

    Managers are consulted in the order of ``TOPOBANK_WORKFLOW_MANAGERS``; the
    first one that knows the name wins.
    """
    for manager in get_workflow_managers():
        descriptor = manager.registry.get(name)
        if descriptor is not None:
            return manager, descriptor
    return None


def resolve_workflow_by_display_name(display_name: str):
    for manager in get_workflow_managers():
        descriptor = manager.registry.get_by_display_name(display_name)
        if descriptor is not None:
            return manager, descriptor
    return None


def get_workflow_names() -> List[str]:
    """All workflow names known to any manager, in resolution order, without duplicates."""
    names = []
    seen = set()
    for manager in get_workflow_managers():
        for name in manager.registry.names():
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def manager_for_result(result) -> WorkflowManager:
    """
    The manager responsible for a `WorkflowResult`'s run.

    A launched row names its manager in its handle. A row without a handle
    predates managers and was run by Celery.
    """
    handle = result.execution_handle
    if handle:
        return get_workflow_manager(LaunchHandle(**handle).manager)
    return get_workflow_manager(LEGACY_MANAGER_NAME)


# Rebuild the singletons when the manager list changes under test.
try:
    from django.test.signals import setting_changed

    def _on_setting_changed(*, setting, **kwargs):
        if setting == "TOPOBANK_WORKFLOW_MANAGERS":
            reset_workflow_managers()

    setting_changed.connect(_on_setting_changed, weak=False)
except ImportError:  # pragma: no cover
    pass
