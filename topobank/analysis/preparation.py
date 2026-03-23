"""Write-ahead manifest preparation and reconciliation.

This module handles the "write-ahead" pattern where database records are created
before computation begins, allowing:
- Upfront permission setup
- Pre-computed storage paths
- Atomic plan creation
- Post-execution validation
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from muflow import WorkflowPlan

from topobank.analysis.models import (
    PlanRecord,
    Workflow,
    WorkflowResult,
    WorkflowSubject,
)
from topobank.authorization import get_permission_model
from topobank.files.models import Manifest, ManifestSet
from topobank.manager.models import Surface, Tag, Topography

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser

_log = logging.getLogger(__name__)


def get_subject_from_key(subject_key: str):
    """Resolve a subject from its key.

    Parameters
    ----------
    subject_key : str
        Subject key like "topography:123" or "surface:456".

    Returns
    -------
    Tag, Topography, or Surface
        The resolved subject.

    Raises
    ------
    ValueError
        If the subject key format is invalid.
    """
    try:
        type_name, id_str = subject_key.split(":", 1)
        obj_id = int(id_str)
    except ValueError:
        raise ValueError(f"Invalid subject key format: {subject_key}")

    if type_name == "topography":
        return Topography.objects.get(id=obj_id)
    elif type_name == "surface":
        return Surface.objects.get(id=obj_id)
    elif type_name == "tag":
        return Tag.objects.get(id=obj_id)
    else:
        raise ValueError(f"Unknown subject type: {type_name}")


def prepare_plan_records(
    plan: WorkflowPlan,
    user: "AbstractUser",
) -> PlanRecord:
    """Create all database entries upfront, before any computation.

    This function:
    1. Creates a PlanRecord to store the plan
    2. Creates WorkflowResult entries for each non-cached node
    3. Creates ManifestSet entries with storage_prefix
    4. Creates write-ahead Manifest entries (confirmed_at=None)

    All records are created in a single transaction for atomicity.

    Parameters
    ----------
    plan : WorkflowPlan
        The execution plan to prepare.
    user : User
        The user creating the plan.

    Returns
    -------
    PlanRecord
        The created plan record with all associated results.
    """
    from topobank.authorization.models import EDIT, FULL

    with transaction.atomic():
        # Get root workflow
        root_node = plan.nodes[plan.root_key]
        try:
            root_workflow = Workflow.objects.get(name=root_node.function)
        except Workflow.DoesNotExist:
            raise ValueError(f"Unknown workflow: {root_node.function}")

        # Create plan record
        plan_permissions = get_permission_model().objects.create()
        plan_permissions.grant(user, FULL)

        plan_record = PlanRecord.objects.create(
            plan_json=plan.to_dict(),
            root_function=root_workflow,
            root_kwargs=root_node.kwargs,
            created_by=user,
            permissions=plan_permissions,
        )

        # Create WorkflowResult entries for each non-cached node
        for node in plan.nodes.values():
            if node.cached:
                # Cached nodes already have a WorkflowResult
                continue

            # Create permissions for this result
            result_permissions = get_permission_model().objects.create()
            result_permissions.grant(user, FULL)

            # Create ManifestSet with storage_prefix
            folder = ManifestSet.objects.create(
                permissions=result_permissions,
                storage_prefix=node.storage_prefix,
                read_only=True,
            )

            # Create write-ahead manifests (confirmed_at=None)
            for filename in node.output_files:
                Manifest.objects.create(
                    folder=folder,
                    filename=filename,
                    kind="der",
                    permissions=result_permissions,
                    confirmed_at=None,  # Write-ahead: not yet written
                )

            # Get workflow for this node
            try:
                workflow = Workflow.objects.get(name=node.function)
            except Workflow.DoesNotExist:
                raise ValueError(f"Unknown workflow: {node.function}")

            # Resolve subject
            subject = get_subject_from_key(node.subject_key)

            # Create WorkflowResult
            analysis = WorkflowResult.objects.create(
                folder=folder,
                function=workflow,
                kwargs=node.kwargs,
                task_state=WorkflowResult.PENDING,
                plan=plan_record,
                node_key=node.key,
                created_by=user,
                permissions=result_permissions,
                subject_dispatch=WorkflowSubject.objects.create(subject=subject),
            )

            # Grant edit access to user
            result_permissions.grant(user, EDIT)

            # Update node with analysis ID
            node.analysis_id = analysis.id

        # Update plan with analysis IDs
        plan_record.plan_json = plan.to_dict()
        plan_record.save(update_fields=["plan_json"])

        _log.info(
            f"Prepared plan {plan_record.id} with {len(plan.nodes)} nodes "
            f"({sum(1 for n in plan.nodes.values() if not n.cached)} to execute)"
        )

        return plan_record


def reconcile_manifest_set(analysis: "WorkflowResult") -> None:
    """Verify expected files exist and confirm manifests.

    Called after a workflow node completes to:
    1. Check that all expected output files exist in storage
    2. Update manifest records with actual file paths
    3. Set confirmed_at timestamps

    Parameters
    ----------
    analysis : WorkflowResult
        The completed workflow result to reconcile.

    Raises
    ------
    RuntimeError
        If a required file is missing.
    """
    folder = analysis.folder
    if folder is None:
        _log.warning(f"Analysis {analysis.id} has no folder - skipping reconciliation")
        return

    storage_prefix = folder.storage_prefix
    if storage_prefix is None:
        # Legacy mode - no reconciliation needed
        _log.debug(f"Analysis {analysis.id} uses legacy storage - skipping reconciliation")
        return

    # Get outputs schema if available
    outputs_schema = {}
    if analysis.function:
        schema_list = analysis.function.get_outputs_schema()
        outputs_schema = {f["filename"]: f for f in schema_list if "filename" in f}

    # Reconcile each unconfirmed manifest
    unconfirmed = folder.files.filter(confirmed_at__isnull=True)
    for manifest in unconfirmed:
        storage_path = f"{storage_prefix}/{manifest.filename}"

        if default_storage.exists(storage_path):
            # File exists - confirm the manifest
            manifest.file.name = storage_path
            manifest.confirmed_at = timezone.now()
            manifest.save(update_fields=["file", "confirmed_at"])
            _log.debug(f"Confirmed manifest {manifest.id}: {storage_path}")
        else:
            # File doesn't exist - check if optional
            spec = outputs_schema.get(manifest.filename, {})
            if not spec.get("optional", False):
                raise RuntimeError(
                    f"Required file '{manifest.filename}' missing from "
                    f"workflow '{analysis.function.name}' at {storage_path}"
                )
            else:
                _log.debug(f"Optional file {manifest.filename} not produced")

    # Also check for unexpected files (files written but not declared)
    if storage_prefix:
        try:
            dirs, files = default_storage.listdir(storage_prefix)
            declared_files = set(folder.files.values_list("filename", flat=True))
            for filename in files:
                if filename not in declared_files:
                    _log.warning(
                        f"Undeclared file '{filename}' found in {storage_prefix} "
                        f"for workflow {analysis.function.name}"
                    )
        except (FileNotFoundError, OSError):
            # Storage path might not exist as a directory
            pass
