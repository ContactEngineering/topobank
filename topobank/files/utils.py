from django.utils.text import slugify


def generate_storage_path(instance, file_name: str) -> str:
    return f"{slugify(str(instance))}/{instance.id}/{file_name}"
