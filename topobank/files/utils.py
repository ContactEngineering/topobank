from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework.reverse import reverse
from storages.utils import clean_name


def generate_upload_path(instance, file_name: str) -> str:
    owner_type, owner_obj = instance.parent.get_owner()
    return f"{owner_type}/{owner_obj.id}/{instance.kind}/{instance.id}/{file_name}"


def get_upload_instructions(instance, name, expire, method=None):
    """Generate a presigned URL for an upload direct to S3"""
    # Preserve the trailing slash after normalizing the path.
    if method is None:
        method = settings.UPLOAD_METHOD

    if settings.USE_S3_STORAGE:
        name = default_storage._normalize_name(clean_name(name))
        if method == "POST":
            upload_instructions = (
                default_storage.bucket.meta.client.generate_presigned_post(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=name, ExpiresIn=expire
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
                        "ContentType": "binary/octet-stream",  # must match content type of put request
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
            "url": reverse("manager:upload-topography", kwargs=dict(pk=instance.id)),
            "fields": {},
        }
    return upload_instructions
