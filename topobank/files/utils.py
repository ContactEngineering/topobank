from datetime import datetime


def file_storage_path(instance, filename: str) -> str:
    if not instance.pk:
        raise RuntimeError(
            f"Cannot construct storage path from unsaved instance {instance}."
        )
    return f"data-lake/{instance.id}/{filename}"


def format_datetime(dt: datetime) -> (str, str):
    date_str = dt.strftime('%Y-%m-%d')
    time_utc_str = dt.utcnow().strftime('%H:%M:%S')
    return date_str, time_utc_str
