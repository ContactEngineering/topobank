def generate_storage_path(instance, file_name: str) -> str:
    return f"{instance.__class__.__name__}/{instance.id}/{file_name}"
