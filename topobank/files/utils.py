def file_storage_path(instance, filename: str) -> str:
    return f"data-lake/{instance.id}/{filename}"
