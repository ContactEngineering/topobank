import logging

from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework.reverse import reverse
from storages.utils import clean_name

_log = logging.getLogger(__name__)


def get_upload_instructions(manifest, expire=10, method=None):
    """Generate a presigned URL for an upload directly to S3"""
    # Preserve the trailing slash after normalizing the path.
    if method is None:
        method = settings.UPLOAD_METHOD

    if settings.USE_S3_STORAGE:
        name = default_storage._normalize_name(clean_name(manifest.filename))
        if method == "POST":
            upload_instructions = (
                default_storage.bucket.meta.client.generate_presigned_post(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Key=name,
                    ExpiresIn=expire,
                )
            )
            upload_instructions["method"] = "POST"
        elif method == "PUT":
            upload_instructions = {
                "method": "PUT",
                "url": default_storage.bucket.meta.client.generate_presigned_url(
                    ClientMethod="put_object",
                    Params={
                        "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                        "Key": name,
                        # ContentType must match content type of put request
                        "ContentType": "binary/octet-stream",
                    },
                    ExpiresIn=expire,
                ),
            }
        else:
            raise RuntimeError(f"Unknown upload method: {method}")
    else:
        if method != "POST":
            raise RuntimeError("Only POST uploads are supported without S3")
        upload_instructions = {
            "method": "POST",
            "url": reverse(
                "files:upload-direct-local", kwargs=dict(manifest_id=manifest.id)
            ),
            "fields": {},
        }
    return upload_instructions
