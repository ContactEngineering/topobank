"""
Workflow engines: the systems topobank hands workflows to.

topobank owns the *what*: a `WorkflowResult` row together with the business
rules that created it - authorization, de-duplication, permissions, ownership.
Everything after that is the *how*, and the how belongs to a workflow engine:
queueing, dependency resolution, fan-out, retries, resource limits, worker
fleets. topobank does not care whether an engine builds a DAG, when it does so,
or whether it uses Celery, Ray or a thread pool.

Each engine owns a :class:`WorkflowRegistry` of the workflows it can run. A
workflow implementation is specific to one engine, so a workflow name resolves
to exactly one engine and to that engine's *shim*: a
:class:`~topobank.analysis.descriptor.WorkflowDescriptor` subclass that gives
topobank the parameter model, display name and accepted subjects, and gives the
engine whatever it needs to run the thing. Resolution is by name over the
configured engines, in order::

    TOPOBANK_WORKFLOW_ENGINES = [
        "topobank.analysis.celery.engine.CeleryWorkflowEngine",
        "sds_api.workflows.RayWorkflowEngine",
    ]

If two engines register the same name, the one listed first wins. This is how
a workflow moves between engines without changing its name: register it with
the new engine and list that engine first; rows launched earlier keep working
because each row records which engine launched it.

The contract an engine implements is small:

``launch``
    Start the workflow behind a `WorkflowResult` and return a
    :class:`LaunchHandle`, an opaque, JSON-serialisable reference that names
    the engine and carries whatever the engine needs to find the run again.
    topobank stores it on the row.

``poll`` / ``cancel``
    Report what the engine knows about a row's run, or stop it. Both receive
    the row and read its stored handle.

``report``
    Engines tell topobank how a run is going through the status contract in
    :mod:`topobank.analysis.status`; that is the only path by which lifecycle
    state reaches the database.

Engines are singletons, created once from the settings list. The Celery
engine (:mod:`topobank.analysis.celery.engine`) is topobank's original
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

#: Import path of the built-in Celery engine. Always part of the engine list;
#: deployments that do not configure ``TOPOBANK_WORKFLOW_ENGINES`` get it alone.
CELERY_WORKFLOW_ENGINE = "topobank.analysis.celery.engine.CeleryWorkflowEngine"

#: Name of the engine that owns rows launched before handles existed.
LEGACY_ENGINE_NAME = "celery"


class LaunchHandle(pydantic.BaseModel):
    """
    Opaque, serialisable reference to a launched run.

    ``engine`` names the :class:`WorkflowEngine` that produced the handle and
    is the only field topobank interprets: it selects the engine that
    ``poll`` and ``cancel`` are routed to. ``data`` is the engine's own, e.g.
    a Celery task id, a Ray job id, a Step Functions execution ARN.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    engine: str
    data: Dict[str, Any] = pydantic.Field(default_factory=dict)


class RunInfo(pydantic.BaseModel):
    """
    What an engine knows about a run when polled.

    ``state`` uses the two-letter codes of
    :class:`~topobank.taskapp.models.TaskStateModel` (``"pe"``, ``"st"``,
    ``"su"``, ``"fa"``, ...). ``progress`` is a percentage or ``None`` when the
    engine cannot tell. ``messages`` are the progress messages of the run and
    its children, if the engine tracks them. ``error`` is set when the engine
    holds an error the run did not report itself, e.g. because its process died.
    """

    model_config = pydantic.ConfigDict(extra="forbid")

    state: str
    progress: Optional[float] = None
    messages: Optional[List[str]] = None
    error: Optional[str] = None


class WorkflowRegistry:
    """
    The workflows one engine can run, by name.

    Plugins register their shims explicitly with the engine they target::

        from topobank.analysis.celery.engine import registry

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
class WorkflowEngine(Protocol):
    """The contract a workflow management system implements."""

    #: Short, stable name recorded in every handle this engine produces.
    name: str

    #: The workflows this engine can run.
    registry: WorkflowRegistry

    def launch(self, result, *, force: bool = False) -> LaunchHandle:
        """Start the workflow behind ``result`` and return a handle to the run."""
        ...

    def poll(self, result) -> RunInfo:
        """Return what the engine knows about the run behind ``result``."""
        ...

    def cancel(self, result) -> None:
        """Stop the run behind ``result`` if it is still running."""
        ...


# --- Singleton engines ---------------------------------------------------

_engines: Optional[List[WorkflowEngine]] = None


def _engine_paths() -> List[str]:
    paths = list(getattr(settings, "TOPOBANK_WORKFLOW_ENGINES", None) or [])
    if CELERY_WORKFLOW_ENGINE not in paths:
        # The Celery engine is always available; if a deployment does not list
        # it, it comes last so that configured engines take priority.
        paths.append(CELERY_WORKFLOW_ENGINE)
    return paths


def get_workflow_engines() -> List[WorkflowEngine]:
    """
    The configured engines, in priority order. Instantiated once.

    The list is rebuilt when ``TOPOBANK_WORKFLOW_ENGINES`` changes, so tests
    can swap engines with ``override_settings``.
    """
    global _engines
    if _engines is None:
        engines = []
        seen = set()
        for path in _engine_paths():
            engine = import_string(path)()
            name = getattr(engine, "name", None)
            if not name:
                raise ImproperlyConfigured(f"Workflow engine {path!r} has no name.")
            if name in seen:
                raise ImproperlyConfigured(
                    f"Two workflow engines are called {name!r}; names must be unique."
                )
            seen.add(name)
            engines.append(engine)
        _engines = engines
    return list(_engines)


def reset_workflow_engines() -> None:
    """Forget the instantiated engines; the next lookup rebuilds them."""
    global _engines
    _engines = None


def get_workflow_engine(name: str) -> WorkflowEngine:
    """Return the engine called ``name``."""
    for engine in get_workflow_engines():
        if engine.name == name:
            return engine
    raise ImproperlyConfigured(
        f"No workflow engine named {name!r}. Known engines: "
        f"{[m.name for m in get_workflow_engines()]}. Add it to TOPOBANK_WORKFLOW_ENGINES."
    )


# --- Resolution -----------------------------------------------------------


def resolve_workflow(name: str) -> Optional[Tuple[WorkflowEngine, Type[WorkflowDescriptor]]]:
    """
    Resolve a workflow name to ``(engine, descriptor)``, or ``None``.

    Engines are consulted in the order of ``TOPOBANK_WORKFLOW_ENGINES``; the
    first one that knows the name wins.
    """
    for engine in get_workflow_engines():
        descriptor = engine.registry.get(name)
        if descriptor is not None:
            return engine, descriptor
    return None


def resolve_workflow_by_display_name(display_name: str):
    for engine in get_workflow_engines():
        descriptor = engine.registry.get_by_display_name(display_name)
        if descriptor is not None:
            return engine, descriptor
    return None


def get_workflow_names() -> List[str]:
    """All workflow names known to any engine, in resolution order, without duplicates."""
    names = []
    seen = set()
    for engine in get_workflow_engines():
        for name in engine.registry.names():
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def engine_for_result(result) -> WorkflowEngine:
    """
    The engine responsible for a `WorkflowResult`'s run.

    A launched row names its engine in its handle. A row without a handle
    predates engines and was run by Celery.
    """
    handle = result.execution_handle
    if handle:
        return get_workflow_engine(LaunchHandle(**handle).engine)
    return get_workflow_engine(LEGACY_ENGINE_NAME)


# Rebuild the singletons when the engine list changes under test.
try:
    from django.test.signals import setting_changed

    def _on_setting_changed(*, setting, **kwargs):
        if setting == "TOPOBANK_WORKFLOW_ENGINES":
            reset_workflow_engines()

    setting_changed.connect(_on_setting_changed, weak=False)
except ImportError:  # pragma: no cover
    pass
