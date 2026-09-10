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
