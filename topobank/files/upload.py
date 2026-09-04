"""Presigned direct-to-storage uploads for user-supplied files."""

import logging
import os

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from django.core.files.storage import default_storage

from .utils import USER_UPLOAD_KINDS

_log = logging.getLogger(__name__)

#: Seconds a presigned POST stays valid.
DEFAULT_UPLOAD_EXPIRE_SECONDS = 900

#: Ceiling for a measurement file. S3 refuses a single object above 5 GiB, so a
#: larger value here would only promise what storage then rejects.
DEFAULT_MAX_MEASUREMENT_UPLOAD_BYTES = 5 * 1024**3

#: Ceiling for a single attachment.
DEFAULT_MAX_ATTACHMENT_UPLOAD_BYTES = 100 * 1024**2

#: Ceiling on attachments per dataset; bounds the unpaginated listing.
DEFAULT_MAX_ATTACHMENTS_PER_SURFACE = 200

#: Stored type for an attachment that is not previewable. Opaque on purpose: a
#: bare presigned GET serves from the bucket origin, where an inline ``.html``
#: or ``.svg`` would be stored XSS.
DEFAULT_OPAQUE_CONTENT_TYPE = "binary/octet-stream"

#: Attachment extensions a browser may render inline, mapped to the stored type.
#: SVG stays out for the reason above.
DEFAULT_INLINE_PREVIEW_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

#: Measurement files are stored opaquely regardless of extension; the preview
#: allowlist and the opaque setting apply to attachments only.
MEASUREMENT_CONTENT_TYPE = "binary/octet-stream"


def upload_expire_seconds():
    """Lifetime of presigned upload instructions, in seconds."""
    return getattr(
        settings, "TOPOBANK_UPLOAD_EXPIRE_SECONDS", DEFAULT_UPLOAD_EXPIRE_SECONDS
    )


def max_upload_bytes(kind):
    """Size ceiling for a user upload of the given manifest kind."""
    if kind not in USER_UPLOAD_KINDS:
        raise ValueError(f"Files of kind '{kind}' are not uploaded by users.")
    if kind == "raw":
        return getattr(
            settings,
            "TOPOBANK_MAX_MEASUREMENT_UPLOAD_BYTES",
            DEFAULT_MAX_MEASUREMENT_UPLOAD_BYTES,
        )
    return getattr(
        settings,
        "TOPOBANK_MAX_ATTACHMENT_UPLOAD_BYTES",
        DEFAULT_MAX_ATTACHMENT_UPLOAD_BYTES,
    )


def max_attachments_per_surface():
    """Ceiling on attachments a single dataset may hold."""
    return getattr(
        settings,
        "TOPOBANK_MAX_ATTACHMENTS_PER_SURFACE",
        DEFAULT_MAX_ATTACHMENTS_PER_SURFACE,
    )


def opaque_content_type():
    """Stored type for an attachment that is not previewable."""
    return getattr(
        settings, "TOPOBANK_OPAQUE_CONTENT_TYPE", DEFAULT_OPAQUE_CONTENT_TYPE
    )


def _preview_types():
    return getattr(
        settings, "TOPOBANK_INLINE_PREVIEW_TYPES", DEFAULT_INLINE_PREVIEW_TYPES
    )


def _extension(filename):
    return os.path.splitext(filename or "")[1].lower()


def is_previewable(filename):
    """Whether an attachment with this name may be rendered inline."""
    return _extension(filename) in _preview_types()


def storage_content_type(filename):
    """Stored type for an attachment, derived from its extension, never the client."""
    return _preview_types().get(_extension(filename), opaque_content_type())


def format_bytes_binary(num_bytes):
    """Human-readable size in binary units, e.g. ``100 MiB``."""
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            break
        value /= 1024
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{text} {unit}"


def _pinned_content_type(manifest):
    if manifest.kind == "att":
        return manifest.content_type or storage_content_type(manifest.filename)
    return MEASUREMENT_CONTENT_TYPE


def get_upload_instructions(manifest, expire=None):
    """Presign a POST for ``manifest``; ``None`` without S3 or for a bad filename.

    Only the POST form carries a policy, so the size ceiling and the stored
    content type are enforced by storage itself. The lower bound of 1 rejects
    an empty upload, which would otherwise confirm as a valid file.
    """
    # Raises for system-written kinds before the S3 guard, so a caller that
    # presigns the wrong manifest fails the same way in tests and production.
    max_bytes = max_upload_bytes(manifest.kind)
    if not getattr(settings, "USE_S3_STORAGE", False):
        return None

    try:
        storage_path = default_storage._normalize_name(manifest.generate_storage_path())
    except SuspiciousOperation:  # SuspiciousFileOperation is a subclass
        _log.warning(
            "Manifest %s: filename '%s' cannot form a storage path; "
            "no upload instructions.",
            manifest.id,
            manifest.filename,
        )
        return None

    content_type = _pinned_content_type(manifest)
    instructions = default_storage.bucket.meta.client.generate_presigned_post(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=storage_path,
        Conditions=[
            ["content-length-range", 1, max_bytes],
            {"Content-Type": content_type},
        ],
        Fields={"Content-Type": content_type},
        ExpiresIn=expire or upload_expire_seconds(),
    )
    instructions["method"] = "POST"
    return instructions
