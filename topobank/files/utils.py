def file_storage_path(instance, filename: str) -> str:
    if not instance.pk:
        raise RuntimeError(
            f"Cannot construct storage path from unsaved instance {instance}."
        )
    prefix = "uploads" if instance.kind == "raw" else "data-lake"
    return f"{prefix}/{instance.id}/{filename}"
