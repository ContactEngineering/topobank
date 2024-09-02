def file_storage_path(instance, filename: str) -> str:
    if not instance.pk:
        raise RuntimeError(
            f"Cannot construct storage path from unsaved instance {instance}."
        )
    return f"data-lake/{instance.id}/{filename}"
