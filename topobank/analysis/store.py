"""
Turning a `ResultRequest` into a `WorkflowResult` row.

Every `WorkflowResult` is created here, whether a user asked for it
(`Workflow.submit`, `Workflow.submit_for_surfaces`) or a workflow declared it
as a dependency (the Celery engine's `prepare_dependency_tasks`). The callers
differ only in *when an existing row may stand in for a new one*, which they
state as a `Reuse` policy, and in the ownership and permissions of a row that
has to be created.

`find_or_create` serializes the check-then-create for one
(workflow, subject, parameters) triple with an advisory lock, so two concurrent
requests for the same thing yield one row. It never dispatches anything: the
caller decides what to do with a result that `needs_run`.
"""

import enum
import json
import logging
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.db.models import Q

from ..manager.models import Tag
from ..supplib.db import advisory_lock
from .workflows import ResultRequest

_log = logging.getLogger(__name__)


class Reuse(enum.Enum):
    """When an existing `WorkflowResult` may stand in for a requested one."""

    #: Reuse a result that is pending, running or finished successfully. A
    #: request that finds none of these deletes the failed, unnamed leftovers
    #: for the same triple and creates a fresh row. This is what a user
    #: submitting a workflow wants: the newest viable answer, computed once.
    VIABLE = "viable"

    #: Reuse whatever exists, finished or not, and report through `needs_run`
    #: whether it still has to run. Failed results are reused too - a
    #: dependency that failed once is not retried behind the parent's back.
    #: This is what dependency resolution wants.
    FINISHED = "finished"

    #: Always create a new row, leaving existing ones untouched.
    NEVER = "never"


@dataclass(frozen=True)
class Found:
    """The outcome of `find_or_create`."""

    #: The result row that answers the request.
    result: object

    #: Whether the row was created by this call.
    created: bool

    #: Whether the row still has to be run (it is new, or was reused in a
    #: non-terminal state, or the caller forced a rerun). A caller that
    #: dispatches work does so exactly when this is set.
    needs_run: bool


def find_or_create(
    request: ResultRequest,
    *,
    user=None,
    reuse: Reuse = Reuse.VIABLE,
    force: bool = False,
    for_user: bool = False,
    owned_by_id=None,
    permissions=None,
    metadata: Optional[dict] = None,
) -> Found:
    """
    Find the `WorkflowResult` answering `request`, or create it.

    Parameters
    ----------
    request : ResultRequest
        What is asked for. Its `kwargs` are validated and completed against the
        workflow's `Parameters` model first; a request for a workflow no
        engine knows raises `WorkflowNotRegisteredException`.
    user : User, optional
        The user acting. Recorded as `created_by`/`updated_by` on a new row
        and, unless `permissions` are given, granted `edit` on it. Tag
        results are private to the user, so for a `Tag` subject only that
        user's results are candidates for reuse.
    reuse : Reuse
        Which existing rows may stand in for a new one. See `Reuse`.
    force : bool
        Behave as if no existing row were viable or finished: under `VIABLE`
        this creates a fresh row (deleting unnamed leftovers), under
        `FINISHED` it marks a reused row as needing a run.
    for_user : bool
        Restrict the candidates for reuse to results `user` may see
        (`WorkflowResult.objects.for_user`). Submission does this;
        dependency resolution, which works on behalf of a parent result,
        does not.
    owned_by_id : int, optional
        Owner of a new row. Defaults to the owner of the first surface for a
        surface-set request; left to the model's default otherwise.
    permissions : PermissionSet, optional
        Permission set a new row joins (a dependency shares its parent's).
        When omitted, a new row gets its own set with `user` granted `edit`.
    metadata : dict, optional
        Stored on a new row (dependencies record their parent here).

    Returns
    -------
    Found
        The row, whether it was created, and whether it still needs to run.
    """
    from .models import Workflow, WorkflowResult

    kwargs = Workflow(name=request.workflow_name).clean_kwargs(request.kwargs)

    q = Q(workflow_name=request.workflow_name, kwargs=kwargs)
    if request.surfaces is not None:
        q &= Q(subject_hash=request.subject_hash)
    else:
        q &= WorkflowResult.Q(request.subject)
        if isinstance(request.subject, Tag) and user is not None:
            # Tag results cannot be shared: only this user's are candidates
            q &= Q(permissions__user_permissions__user=user)

    def create():
        _log.info(
            "Creating WorkflowResult for workflow %r, %s %s, kwargs %s (user %s)",
            request.workflow_name,
            request.subject_type,
            request.subject_ids,
            kwargs,
            user,
        )
        create_kwargs = dict(
            workflow_name=request.workflow_name,
            kwargs=kwargs,
            subject_hash=request.subject_hash,
            created_by=user,
            updated_by=user,
        )
        if permissions is not None:
            create_kwargs["permissions"] = permissions
        if metadata is not None:
            create_kwargs["metadata"] = metadata
        if request.surfaces is not None:
            create_kwargs["owned_by_id"] = owned_by_id or request.surfaces[0].owned_by_id
        elif owned_by_id is not None:
            create_kwargs["owned_by_id"] = owned_by_id
        if request.subject is not None:
            create_kwargs[f"subject_{request.subject_type}"] = request.subject

        result = WorkflowResult.objects.create(**create_kwargs)
        if request.surfaces is not None:
            # Many-to-many relations can only be set once the row exists
            result.surfaces.set(request.surfaces)
        result.set_pending_state()
        if permissions is None and user is not None:
            result.permissions.grant_for_user(user, "edit")
        return Found(result=result, created=True, needs_run=True)

    # Serialize the check-then-create against concurrent identical requests.
    # Without this, two requests for the same workflow/subject/kwargs can both
    # observe "nothing to reuse" and both create (and run) a row. The lock is
    # released when the surrounding transaction commits.
    with transaction.atomic(), advisory_lock(
        "workflow-result",
        request.workflow_name,
        request.subject_hash,
        json.dumps(kwargs, sort_keys=True, default=str),
    ):
        if reuse is Reuse.NEVER:
            return create()

        manager = WorkflowResult.objects
        existing = (manager.for_user(user) if for_user else manager).filter(q)

        if reuse is Reuse.VIABLE:
            viable = existing.filter(
                task_state__in=[
                    WorkflowResult.PENDING,
                    WorkflowResult.PENDING_DEPENDENCIES,
                    WorkflowResult.RETRY,
                    WorkflowResult.STARTED,
                    WorkflowResult.SUCCESS,
                ]
            )
            if force or not viable.exists():
                # Whatever is left for this triple has failed or never ran.
                # Named results are kept: a name is what saves a result from
                # following its subject to the grave.
                existing.filter(name__isnull=True).delete()
                return create()
            # Pick from the viable set: never-run rows have a NULL
            # task_start_time, which sorts last in PostgreSQL, so ordering the
            # full set could hand back a NOTRUN row instead of a SUCCESS one.
            return Found(
                result=viable.order_by("task_start_time").last(),
                created=False,
                needs_run=False,
            )

        # Reuse.FINISHED
        result = (
            existing.select_related("subject_topography", "subject_surface", "subject_tag")
            .order_by("-task_start_time")
            .first()
        )
        if result is None:
            return create()
        # task_state is the state the run reported itself, not the engine's
        finished = result.task_state in [WorkflowResult.FAILURE, WorkflowResult.SUCCESS]
        return Found(result=result, created=False, needs_run=force or not finished)
