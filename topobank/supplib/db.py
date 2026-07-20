"""Small database helpers shared across apps."""

import contextlib
import hashlib

from django.db import connection


def _advisory_lock_key(*parts) -> int:
    """Map arbitrary parts to a signed 64-bit int for pg_advisory_xact_lock.

    PostgreSQL advisory locks are keyed by a bigint, so we hash the string
    representation of the parts into the signed 64-bit range.
    """
    key = "\x00".join(str(p) for p in parts)
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@contextlib.contextmanager
def advisory_lock(*parts):
    """Serialize a critical section across processes with a PostgreSQL
    transaction-level advisory lock.

    Must be used inside a ``transaction.atomic()`` block; the lock is released
    automatically when that transaction commits or rolls back. Concurrent
    callers requesting the same key block until the holder's transaction ends,
    which lets a check-then-create critical section run without racing.

    On non-PostgreSQL backends this is a no-op (advisory locks are
    Postgres-specific), so behavior degrades to the previous unserialized
    check-then-create rather than erroring.
    """
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)", [_advisory_lock_key(*parts)]
            )
    yield
