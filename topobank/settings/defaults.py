"""Default values for the ``TOPOBANK_*`` settings.

A deployment overrides any of these in its own Django settings module.
"""

#: Seconds a presigned upload POST stays valid.
TOPOBANK_UPLOAD_EXPIRE_SECONDS = 900

#: Ceiling for a measurement file. S3 refuses a single object above 5 GiB, so a
#: larger value here would only promise what storage then rejects.
TOPOBANK_MAX_MEASUREMENT_UPLOAD_BYTES = 5 * 1024**3

#: Ceiling for a single attachment.
TOPOBANK_MAX_ATTACHMENT_UPLOAD_BYTES = 100 * 1024**2

#: Ceiling on attachments per dataset; bounds the unpaginated listing.
TOPOBANK_MAX_ATTACHMENTS_PER_SURFACE = 200

#: Stored type for an attachment that is not previewable. Opaque on purpose: a
#: bare presigned GET serves from the bucket origin, where an inline ``.html``
#: or ``.svg`` would be stored XSS.
TOPOBANK_OPAQUE_CONTENT_TYPE = "binary/octet-stream"

#: Attachment extensions a browser may render inline, mapped to the stored type.
#: SVG stays out for the reason above.
TOPOBANK_INLINE_PREVIEW_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

#: Seconds after which a delivered message may take over a task that is still
#: recorded as ``STARTED`` under the same Celery task id. With ``task_acks_late``
#: the broker redelivers the message of a worker that died mid-run once its
#: visibility timeout lapses, but it redelivers the message of a run that merely
#: outlives that timeout just the same, and a second delivery must not take over
#: a live run. ``None`` (the default) takes a run over only once it is older than
#: the task's hard time limit, past which the worker has killed it; a task with
#: no hard time limit is never taken over. Set a number of seconds to take over
#: sooner, on an installation where no run can live that long.
TOPOBANK_TASK_RECLAIM_AFTER = None

#: Detrending applied to a measurement's thumbnail and deep zoom images on top of
#: its own ``detrend_mode`` -- one of the ``Topography.DETREND_MODE_CHOICES`` keys,
#: or ``None`` to show the measurement exactly as analyses see it. Only the images
#: are affected.
TOPOBANK_VISUALIZATION_DETREND_MODE = None

#: Image format of a measurement's thumbnail
TOPOBANK_THUMBNAIL_FORMAT = "jpeg"

#: Storage prefix under which the processing of a measurement writes its derived
#: files (squeezed datafile, thumbnail, deep zoom images), one folder per
#: measurement and run.
#: The manifests created for them reference the files where they were written.
TOPOBANK_PROCESSING_STORAGE_PREFIX = "data-lake/processing"

#: Dotted path of a callable ``backend(topography, task_id)`` that runs the
#: claimed processing of a measurement instead of the Celery task, or ``None``
#: (the default) for the Celery task. It is called once the dispatching
#: transaction commits, often within a web request, with the run started and the
#: measurement as it is then; it only hands the run off (an asynchronous
#: invocation, say) and returns, and an exception it raises fails the run. The
#: backend takes what it needs at that point
#: (``Topography.inspection_parameters``), inspects the data file with
#: ``topobank.manager.processing.inspect_datafile``, writing the derived files
#: in a folder of its own for each attempt within
#: ``Topography.processing_folder(task_id)``, so that a retried attempt cannot
#: touch the files of one that was recorded, and ends the run with
#: ``Topography.apply_backend_result(task_id, result)`` (in a worker, as it
#: deletes the files the result replaces), or with ``error`` if the inspection
#: failed. A run it never ends is failed by the custodian as lost once it is
#: older than the custodian's minimum age (15 minutes by default).
TOPOBANK_PROCESSING_BACKEND = None
