"""Backfill NULL ``Surface``/``Topography.owned_by`` from available ownership information.

Datasets with NULL ``owned_by`` are eligible for custodian cleanup, but on databases
upgraded from versions that predate organization ownership the owning organization is
often still derivable. This data migration fills in what can be determined
unambiguously:

1. **Surfaces**: the creator's organization. Organization models link
   membership to a Django auth group (a ``group_id`` column on the organization
   table). When that column is present in the database, each unowned surface is
   assigned its creator's organization, resolved through the creator's auth-group
   memberships. The actual database is introspected; if the column is absent, the
   membership information is not available and this step is skipped. Creators
   belonging to several organizations are ambiguous and left NULL.
2. **Topographies**: the parent surface's organization (always derivable).

The organization and user models are resolved from the ``owned_by``/``created_by``
foreign keys, so configured ``TOPOBANK_ORGANIZATION_MODEL``/``AUTH_USER_MODEL`` are
honored. No-op on fresh databases (empty tables). Reverse is a no-op.
"""

import logging

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db import migrations
from django.db.models import OuterRef, Subquery

_log = logging.getLogger(__name__)

# Column on the organization table that historically linked an organization to a
# Django auth group. Discovered by database introspection, not model state.
GROUP_COLUMN = "group_id"


def _table_columns(connection, table_name):
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(
                cursor, table_name
            )
        }


def backfill_owned_by(apps, schema_editor):
    connection = schema_editor.connection
    alias = connection.alias
    Surface = apps.get_model("manager", "Surface")
    Topography = apps.get_model("manager", "Topography")

    # Resolve the related models from the fields so that a configured
    # TOPOBANK_ORGANIZATION_MODEL / AUTH_USER_MODEL is honored.
    Organization = Surface._meta.get_field("owned_by").remote_field.model
    User = Surface._meta.get_field("created_by").remote_field.model

    n_surfaces = _backfill_surfaces(connection, alias, Surface, Organization, User)
    n_topographies = (
        Topography.objects.using(alias)
        .filter(owned_by__isnull=True, surface__owned_by__isnull=False)
        .update(
            owned_by=Subquery(
                Surface.objects.using(alias)
                .filter(pk=OuterRef("surface_id"))
                .values("owned_by")[:1]
            )
        )
    )
    if n_surfaces or n_topographies:
        _log.info(
            "Backfilled owned_by on %d surfaces and %d topographies",
            n_surfaces,
            n_topographies,
        )


def _backfill_surfaces(connection, alias, Surface, Organization, User):
    org_table = Organization._meta.db_table
    if GROUP_COLUMN not in _table_columns(connection, org_table):
        _log.debug(
            "%s has no %s column; surface owned_by cannot be derived from "
            "organization membership",
            org_table,
            GROUP_COLUMN,
        )
        return 0
    try:
        groups_field = User._meta.get_field("groups")
    except FieldDoesNotExist:
        _log.debug(
            "User model has no group memberships; skipping surface owned_by backfill"
        )
        return 0

    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {quote(GROUP_COLUMN)}, {quote(Organization._meta.pk.column)} "
            f"FROM {quote(org_table)} WHERE {quote(GROUP_COLUMN)} IS NOT NULL"
        )
        group_to_org = dict(cursor.fetchall())
    if not group_to_org:
        return 0

    # creator -> organizations via auth-group membership; multi-org creators are
    # ambiguous and skipped (their datasets keep NULL owned_by).
    user_orgs = {}
    membership_qs = (
        groups_field.remote_field.through.objects.using(alias)
        .filter(group_id__in=group_to_org)
        .values_list("user_id", "group_id")
    )
    for user_id, group_id in membership_qs:
        user_orgs.setdefault(user_id, set()).add(group_to_org[group_id])
    ambiguous = {user_id for user_id, orgs in user_orgs.items() if len(orgs) > 1}
    if ambiguous:
        _log.warning(
            "Skipping owned_by backfill for surfaces created by %d user(s) "
            "belonging to more than one organization (sample: %s)",
            len(ambiguous),
            sorted(ambiguous)[:10],
        )

    n_backfilled = 0
    org_users = {}
    for user_id, orgs in user_orgs.items():
        if user_id in ambiguous:
            continue
        org_users.setdefault(next(iter(orgs)), []).append(user_id)
    for org_id, user_ids in org_users.items():
        n_backfilled += (
            Surface.objects.using(alias)
            .filter(owned_by__isnull=True, created_by_id__in=user_ids)
            .update(owned_by_id=org_id)
        )
    return n_backfilled


class Migration(migrations.Migration):

    dependencies = [
        ("manager", "0078_surface_surface_active_name_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(backfill_owned_by, migrations.RunPython.noop),
    ]
