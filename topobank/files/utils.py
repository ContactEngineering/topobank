import posixpath

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


def is_storage_key(key) -> bool:
    """Whether `key` is a storage key as the storage would use it.

    The storage normalizes a key before it uses it (django-storages turns `\\`
    into `/` after `normpath`), so a key is trusted only as it would be used:
    a non-empty string, no backslash, no leading slash, and no empty, `.` or
    `..` segment.
    """
    return (
        isinstance(key, str)
        and "\\" not in key
        and not key.startswith("/")
        and posixpath.normpath(key) == key
        and not {".", ".."} & set(key.split("/"))
    )


def confined_key(key, prefix) -> bool:
    """Whether `key` is a storage key (see `is_storage_key`) under the folder
    `prefix`, itself a storage key: an empty or malformed `prefix` confines
    nothing, so it admits no key."""
    return is_storage_key(prefix) and is_storage_key(key) and key.startswith(f"{prefix}/")


def is_folder_filename(name) -> bool:
    """Whether `name` can name a file in a folder: a relative path shaped like
    a storage key (folders hold tile trees such as `dzi_files/8/0_0.jpg`)
    that fits `Manifest.filename` (255 characters)."""
    return is_storage_key(name) and len(name) <= 255
