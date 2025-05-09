# Generated by Django 4.2.15 on 2024-08-19 20:24

import django.db.models.deletion
from django.db import migrations, models


def api_to_guardian(api_permission):
    """
    Translate a REST API permissions to a list of Django guardian permissions.
    The API exposes the following permissions:
        None: No access to the dataset
        'view': Basic view access, corresponding to 'view_surface'
        'edit': Edit access, corresponding to 'view_surface' and
            'change_surface'
        'full': Full access (essentially transfer), corresponding to
            'view_surface', 'change_surface', 'delete_surface',
            'share_surface' and 'publish_surface'
    """
    _permissions = {
        None: [],
        "view": ["view_surface"],
        "edit": ["view_surface", "change_surface"],
        "full": [
            "view_surface",
            "change_surface",
            "delete_surface",
            "share_surface",
            "publish_surface",
        ],
    }

    return _permissions[api_permission]


def guardian_to_api(guardian_permissions):
    """
    Translate a list of Django guardian permissions to an API permission
    keyword. The API exposes the following permissions:
        None: No access to the dataset
        'view': Basic view access, corresponding to 'view_surface'
        'edit': Edit access, corresponding to 'view_surface' and
            'change_surface'
        'full': Full access (essentially transfer), corresponding to
            'view_surface', 'change_surface', 'delete_surface',
            'share_surface' and 'publish_surface'
    """

    api_permission = None
    if "view_surface" in guardian_permissions:
        api_permission = "view"
        if "change_surface" in guardian_permissions:
            api_permission = "edit"
            if (
                "delete_surface" in guardian_permissions
                and "share_surface" in guardian_permissions
                and "publish_surface" in guardian_permissions
            ):
                api_permission = "full"
    return api_permission


def forward_func(apps, schema_editor):
    User = apps.get_model("users", "User")
    Surface = apps.get_model("manager", "Surface")
    Topography = apps.get_model("manager", "Topography")
    Property = apps.get_model("manager", "Property")
    SurfaceUserObjectPermission = apps.get_model(
        "manager", "SurfaceUserObjectPermission"
    )
    PermissionDictionary = apps.get_model("auth", "Permission")
    PermissionSet = apps.get_model("authorization", "PermissionSet")
    UserPermission = apps.get_model("authorization", "UserPermission")
    for surface in Surface.objects.all():
        # Create new permset representing the guardian permissions
        permset = PermissionSet()
        permset.save()
        users_with_access = [
            User.objects.get(pk=x["user"])
            for x in SurfaceUserObjectPermission.objects.filter(content_object=surface)
            .order_by("user")
            .distinct("user")
            .values("user")
        ]
        for user in users_with_access:
            guardian_permissions = [
                PermissionDictionary.objects.get(pk=x.permission.id).codename
                for x in SurfaceUserObjectPermission.objects.filter(
                    content_object=surface, user=user
                )
            ]
            access_level = guardian_to_api(guardian_permissions)
            if access_level is not None:
                UserPermission.objects.create(
                    parent=permset, user=user, allow=access_level
                )
        # Attach permset to surface
        surface.permissions = permset
        surface.save()
        # Attach permset to topographies
        for topography in Topography.objects.filter(surface=surface):
            topography.permissions = permset
            topography.save()
        # Attach permset to properties
        for property in Property.objects.filter(surface=surface):
            property.permissions = permset
            property.save()


class Migration(migrations.Migration):

    dependencies = [
        ("authorization", "0001_initial"),
        ("files", "0001_initial"),
        ("manager", "0053_alter_property_options_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="topography",
            options={
                "ordering": ["measurement_date", "pk"],
                "verbose_name": "measurement",
                "verbose_name_plural": "measurements",
            },
        ),
        migrations.AddField(
            model_name="property",
            name="permissions",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="authorization.permissionset",
            ),
        ),
        migrations.AddField(
            model_name="surface",
            name="permissions",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="authorization.permissionset",
            ),
        ),
        migrations.AddField(
            model_name="topography",
            name="permissions",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="authorization.permissionset",
            ),
        ),
        migrations.RunPython(forward_func),
    ]
