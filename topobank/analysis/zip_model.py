import logging
import tempfile

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils.text import slugify

from ..authorization.mixins import PermissionMixin
from ..authorization.models import AuthorizedManager
from ..files.models import Manifest
from ..taskapp.models import TaskStateModel
from .export_zip import export_results_zip
from .models import WorkflowResult

_log = logging.getLogger(__name__)


class ResultZipContainer(PermissionMixin, TaskStateModel):
    """
    A ZIP archive of the files of one or more workflow results, built by a
    Celery worker.

    Bundling is deferred to a worker because a result can hold a large number of
    large files; doing it in the request would block a web worker for the whole
    duration. The client creates a container, polls its task state, and follows
    the URL of `manifest` once the task has succeeded. Containers are transient
    and are removed again by the custodian.
    """

    #
    # Celery task queue
    #
    celery_queue = settings.TOPOBANK_ANALYSIS_QUEUE

    #
    # Manager
    #
    objects = AuthorizedManager()

    #
    # Model hierarchy and permissions
    #
    permissions = models.ForeignKey(
        getattr(settings, "TOPOBANK_PERMISSION_MODEL", "authorization.PermissionSet"),
        on_delete=models.CASCADE,
        null=True,
    )

    # The archive itself, set once the task has succeeded
    manifest = models.ForeignKey(
        Manifest,
        null=True,
        on_delete=models.SET_NULL,
        related_name="result_zip_containers",
    )

    # Timestamps of creation and last modification of this container
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def export_zip(self, result_ids, progress_recorder=None):
        #
        # Fetch user
        #
        user = self.permissions.user_permissions.first().user

        #
        # Collect results, checking that the user may see each of them
        #
        results = []
        for result_id in result_ids:
            result = WorkflowResult.objects.get(id=result_id)
            if not result.has_permission(user, "view"):
                raise PermissionDenied()
            if result.get_task_state() != WorkflowResult.SUCCESS:
                # Nothing to bundle for a result that did not complete
                continue
            results.append(result)

        if not results:
            raise RuntimeError(
                "None of the requested analyses has results that can be downloaded."
            )

        #
        # Guess a filename
        #
        if len(results) == 1:
            workflow = results[0].function
            name = "analysis" if workflow is None else workflow.display_name
            container_filename = f"{slugify(name)}.zip"
        else:
            container_filename = "analysis-results.zip"

        #
        # Build the archive. This goes to a temporary file rather than to memory
        # because the archive can be large.
        #
        _log.info(
            "Preparing ZIP container of workflow results with ids "
            f"{' '.join(str(r.id) for r in results)} for download..."
        )
        with tempfile.TemporaryFile() as container_data:
            export_results_zip(
                container_data, results, progress_recorder=progress_recorder
            )
            container_data.seek(0)

            #
            # Create and write the file to storage
            #
            self.manifest = Manifest.objects.create(
                permissions=self.permissions,
                filename=container_filename,
                kind="der",
            )
            self.manifest.save_file(container_data)

    def task_worker(self, result_ids=None, progress_recorder=None):
        if self.permissions.user_permissions.count() != 1:
            raise PermissionDenied(
                "Internal error: There should only be a single user for ZIP downloads."
            )
        if result_ids is None:
            raise RuntimeError("Please specify the analyses to bundle.")
        self.export_zip(result_ids, progress_recorder=progress_recorder)
