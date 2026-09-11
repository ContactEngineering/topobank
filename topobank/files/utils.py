#: Kinds whose bytes a user uploads directly.
#: raw - measurment data
#: att - attachement file for a surface
USER_UPLOAD_KINDS = frozenset({"raw", "att"})


def file_storage_path(instance, filename: str) -> str:
    if not instance.pk:
        raise RuntimeError(
            f"Cannot construct storage path from unsaved instance {instance}."
        )
    prefix = "uploads" if instance.kind in USER_UPLOAD_KINDS else "data-lake"
    return f"{prefix}/{instance.id}/{filename}"
