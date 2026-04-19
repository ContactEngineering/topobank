"""
Celery tasks for muFlow integration.

This module contains the completion callback task that is invoked
when a muFlow plan finishes execution.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from muflow import PlanHandle
from muflow.storage import S3StorageBackend

from ...files.models import Manifest
from ..models import WorkflowResult

_log = logging.getLogger(__name__)


@shared_task(name="topobank.analysis.muflow.on_muflow_complete")
def on_muflow_complete(
    plan_id: str,
    success: bool,
    error: str = None,
    analysis_id: int = None,
):
    """
    Called by muFlow CeleryCompletionCallback when a plan finishes.

    This task:
    1. Finds the WorkflowResult by analysis_id (passed via task_kwargs)
    2. Creates Manifest entries pointing to muFlow files (no copy)
    3. Updates WorkflowResult.task_state

    Parameters
    ----------
    plan_id : str
        The muFlow plan ID that completed.
    success : bool
        Whether the plan completed successfully.
    error : str, optional
        Error message if the plan failed.
    analysis_id : int, optional
        The WorkflowResult ID to update.
    """
    _log.info(
        f"muFlow completion callback: plan_id={plan_id}, success={success}, "
        f"analysis_id={analysis_id}"
    )

    if analysis_id is None:
        _log.error("No analysis_id provided to completion callback")
        return

    try:
        analysis = WorkflowResult.objects.get(id=analysis_id)
    except WorkflowResult.DoesNotExist:
        _log.error(f"WorkflowResult {analysis_id} not found")
        return

    # Update end time
    analysis.task_end_time = timezone.now()

    if not success:
        # Mark as failed
        analysis.task_state = WorkflowResult.FAILURE
        if error:
            _log.error(f"muFlow plan {plan_id} failed: {error}")
        analysis.save(update_fields=["task_state", "task_end_time"])
        return

    # Plan succeeded - link the output files
    try:
        _link_muflow_results(analysis, plan_id)
        analysis.task_state = WorkflowResult.SUCCESS
    except Exception as e:
        _log.exception(f"Failed to link muFlow results for analysis {analysis_id}: {e}")
        analysis.task_state = WorkflowResult.FAILURE

    analysis.save(update_fields=["task_state", "task_end_time"])


def _link_muflow_results(analysis, plan_id: str):
    """
    Link muFlow output files to the WorkflowResult's ManifestSet.

    This creates Manifest entries that point directly to the muFlow
    output files in S3, without copying data. If a Manifest for the
    same S3 key already exists (from another pipeline that produced
    the same cached result), we reuse it.

    Parameters
    ----------
    analysis : WorkflowResult
        The analysis to link files to.
    plan_id : str
        The muFlow plan ID to get results from.
    """
    # Get handle from metadata
    handle_json = analysis.metadata.get("muflow_handle")
    if not handle_json:
        raise ValueError(f"No muflow_handle in analysis {analysis.id} metadata")

    handle = PlanHandle.from_json(handle_json)

    # Get storage configuration
    bucket_name = getattr(settings, "MUFLOW_S3_BUCKET", None)
    if bucket_name is None:
        bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "topobank")

    # Get the root node's output prefix
    root_key = handle.root_key
    root_prefix = handle.node_prefixes.get(root_key)
    if not root_prefix:
        raise ValueError(f"No prefix found for root node '{root_key}'")

    # Read the manifest from muFlow storage
    storage = S3StorageBackend(prefix=root_prefix, bucket=bucket_name)
    try:
        manifest_data = storage.read_json("manifest.json")
    except FileNotFoundError:
        _log.warning(f"No manifest.json found for plan {plan_id}")
        manifest_data = {}

    # Ensure analysis has a folder
    analysis.fix_folder()

    # Link each output file
    files = manifest_data.get("files", [])
    for filename in files:
        # Skip internal muFlow files
        if filename in ["context.json", "manifest.json"]:
            continue

        # Full S3 key for this file
        s3_key = f"{root_prefix}/{filename}"

        # Get or create Manifest for this S3 file
        # Using get_or_create with the S3 key as identifier
        manifest, created = Manifest.objects.get_or_create(
            file=s3_key,
            defaults={
                "filename": filename,
                "kind": "der",
                "confirmed_at": timezone.now(),
                "permissions": analysis.permissions,
            }
        )

        # Add this ManifestSet to the manifest's folders (M2M)
        manifest.folders.add(analysis.folder)

        # Ensure permissions are set
        if manifest.permissions is None:
            manifest.permissions = analysis.permissions
            manifest.save(update_fields=["permissions"])

        if created:
            _log.debug(f"Created Manifest for {s3_key}")
        else:
            _log.debug(f"Linked existing Manifest for {s3_key}")
