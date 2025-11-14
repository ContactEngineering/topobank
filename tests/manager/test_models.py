"""
Tests related to the models in topobank.manager app
"""

import datetime

import pytest
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.utils import IntegrityError
from notifications.models import Notification
from notifications.signals import notify
from numpy.testing import assert_allclose

from topobank.authorization.models import PermissionSet
from topobank.manager.models import Surface, Tag, Topography
from topobank.testing.factories import (
    SurfaceFactory,
    Topography1DFactory,
    Topography2DFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_topography_name(two_topos):
    topos = Topography.objects.all().order_by("name")
    assert [t.name for t in topos] == ["Example 3 - ZSensor", "Example 4 - Default"]


@pytest.mark.django_db
def test_topography_has_periodic_flag(two_topos):
    topos = Topography.objects.all().order_by("name")
    assert not topos[0].is_periodic
    assert not topos[1].is_periodic


@pytest.mark.django_db
def test_topography_has_unit_set(two_topos):
    topos = Topography.objects.all().order_by("name")
    assert topos[0].unit == "nm"
    assert topos[1].unit == "m"


@pytest.mark.django_db
def test_topography_instrument_dict():
    instrument_parameters = {
        "tip_radius": {
            "value": 10,
            "unit": "nm",
        }
    }
    instrument_name = "My Profilometer"
    instrument_type = "contact-based"

    topo = Topography2DFactory(
        instrument_name=instrument_name,
        instrument_type=instrument_type,
        instrument_parameters=instrument_parameters,
    )

    assert topo.instrument_name == instrument_name
    assert topo.instrument_type == instrument_type
    assert topo.instrument_parameters == instrument_parameters


@pytest.mark.django_db
def test_topography_str(two_topos):
    surface = Surface.objects.get(name="Surface 1")
    topos = Topography.objects.filter(surface=surface).order_by("name")
    assert [str(t) for t in topos] == [
        "Measurement 'Example 3 - ZSensor'"
    ]

    surface = Surface.objects.get(name="Surface 2")
    topos = Topography.objects.filter(surface=surface).order_by("name")
    assert [str(t) for t in topos] == [
        "Measurement 'Example 4 - Default'"
    ]


@pytest.mark.django_db
def test_topography_to_dict():
    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    name = "Some nice topography"
    size_x = 10
    size_y = 20
    height_scale = 2.0
    detrend_mode = "curvature"
    description = """
    Some nice text about this topography.
    """
    unit = "µm"  # needs unicode
    measurement_date = datetime.date(2020, 1, 2)
    is_periodic = True
    tags = ["house", "tree", "tree/leaf"]
    instrument = {
        "name": "My nice instrument",
        "type": "microscope-based",
        "parameters": {
            "resolution": {
                "value": 10,
                "unit": "µm",
            }
        },
    }

    topo = Topography2DFactory(
        surface=surface,
        name=name,
        size_x=size_x,
        size_y=size_y,
        height_scale=height_scale,
        height_scale_editable=True,  # should be always True when height scale is given extra
        detrend_mode=detrend_mode,
        description=description,
        unit=unit,
        is_periodic=is_periodic,
        measurement_date=measurement_date,
        tags=tags,
        instrument_name=instrument["name"],
        instrument_type=instrument["type"],
        instrument_parameters=instrument["parameters"],
    )
    topo.refresh_cache()

    assert topo.to_dict() == {
        "name": name,
        "size": [size_x, size_y],
        "height_scale": height_scale,
        "detrend_mode": detrend_mode,
        "datafile": {
            "original": topo.datafile.filename,
            "squeezed-netcdf": topo.squeezed_datafile.filename,
        },
        "description": description,
        "unit": unit,
        "data_source": topo.data_source,
        "created_by": dict(name=user.name, orcid=user.orcid_id),
        "measurement_date": measurement_date,
        "is_periodic": is_periodic,
        "tags": tags,
        "instrument": instrument,
        "fill_undefined_data_mode": Topography.FILL_UNDEFINED_DATA_MODE_NOFILLING,
        "has_undefined_data": False,
    }


@pytest.mark.django_db
def test_call_topography_method_multiple_times(two_topos):
    topo = Topography.objects.get(name="Example 3 - ZSensor")

    #
    # coeffs should not change in between calls
    #
    st_topo = topo.topography(allow_squeezed=False)

    coeffs_before = st_topo.coeffs
    scaling_factor_before = st_topo.parent_topography.height_scale_factor
    st_topo = topo.topography(allow_squeezed=False)

    assert st_topo.parent_topography.height_scale_factor == scaling_factor_before
    assert (st_topo.coeffs == coeffs_before).all()


@pytest.mark.django_db
def test_unique_topography_name_in_same_surface():
    user = UserFactory()
    surface1 = SurfaceFactory(created_by=user)

    Topography1DFactory(surface=surface1, name="TOPO")

    with transaction.atomic():  # otherwise we can't proceed in this test
        with pytest.raises(IntegrityError):
            Topography1DFactory(surface=surface1, name="TOPO")

    # no problem with another surface
    surface2 = SurfaceFactory(created_by=user)
    Topography1DFactory(surface=surface2, name="TOPO")


@pytest.mark.django_db
def test_surface_description(django_user_model):
    username = "testuser"
    password = "abcd$1234"

    user = django_user_model.objects.create_user(username=username, password=password)

    surface = Surface.objects.create(name="Surface 1", created_by=user)

    assert "" == surface.description

    surface.description = "First surface"

    surface.save()

    surface = Surface.objects.get(name="Surface 1")
    assert "First surface" == surface.description


@pytest.mark.django_db
def test_surface_share_and_unshare():
    password = "abcd$1234"

    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)

    surface = SurfaceFactory(created_by=user1)

    #
    # no permissions at beginning
    #
    assert not surface.has_permission(user2, "view")

    #
    # first: share, but only with view access
    #
    surface.grant_permission(user2)  # default: only view access
    assert surface.has_permission(user2, "view")
    assert not surface.has_permission(user2, "edit")
    assert not surface.has_permission(user2, "full")

    #
    # second: share, but also with right access
    #
    surface.grant_permission(user2, "edit")
    assert surface.has_permission(user2, "view")
    assert surface.has_permission(user2, "edit")
    assert not surface.has_permission(user2, "full")

    #
    # second: share, but also with full access
    #
    surface.grant_permission(user2, "full")
    assert surface.has_permission(user2, "view")
    assert surface.has_permission(user2, "edit")
    assert surface.has_permission(user2, "full")

    #
    # third: remove all shares again
    #
    surface.revoke_permission(user2)
    assert not surface.has_permission(user2, "view")
    assert not surface.has_permission(user2, "edit")
    assert not surface.has_permission(user2, "full")

    # no problem to call this removal again
    surface.revoke_permission(user2)


@pytest.mark.django_db
def test_other_methods_about_sharing():
    user1 = UserFactory()
    user2 = UserFactory()

    # create surface, at first user 2 has no access
    surface = SurfaceFactory(created_by=user1)
    assert not surface.is_shared(user2)
    assert surface.get_permission(user2) is None

    # now share and test access
    surface.grant_permission(user2)

    assert surface.is_shared(user2)
    assert surface.get_permission(user2) == "view"
    assert surface.has_permission(user2, "view")

    # .. add permission to change
    surface.grant_permission(user2, "edit")
    assert surface.is_shared(user2)
    assert surface.get_permission(user2) == "edit"
    assert surface.has_permission(user2, "edit")

    # .. remove all permissions
    surface.revoke_permission(user2)
    assert not surface.is_shared(user2)
    assert surface.get_permission(user2) is None


@pytest.mark.django_db
def test_notifications_are_deleted_when_surface_deleted():
    password = "abcd$1234"
    user = UserFactory(password=password)
    surface = SurfaceFactory(created_by=user)
    surface_id = surface.id

    notify.send(
        sender=user,
        verb="create",
        target=surface,
        recipient=user,
        description="You have a new surface",
    )
    notify.send(
        sender=user,
        verb="info",
        target=surface,
        recipient=user,
        description="Another info.",
    )

    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(surface)

    assert (
        Notification.objects.filter(
            target_content_type=ct, target_object_id=surface_id
        ).count()
        == 2
    )

    #
    # now delete the surface, the notification is no longer valid and should be also deleted
    #
    surface.delete()

    assert (
        Notification.objects.filter(
            target_content_type=ct, target_object_id=surface_id
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_notifications_are_deleted_when_topography_deleted():
    password = "abcd$1234"
    user = UserFactory(password=password)
    surface = SurfaceFactory(created_by=user)

    topo = Topography1DFactory(surface=surface)
    topo_id = topo.id

    notify.send(
        sender=user,
        verb="create",
        target=topo,
        recipient=user,
        description="You have a new topography",
    )
    notify.send(
        sender=user,
        verb="info",
        target=topo,
        recipient=user,
        description="Another info.",
    )

    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(topo)

    assert (
        Notification.objects.filter(
            target_content_type=ct, target_object_id=topo_id
        ).count()
        == 2
    )

    #
    # now delete the topography, the notification is no longer valid and should be also deleted
    #
    topo.delete()

    assert (
        Notification.objects.filter(
            target_content_type=ct, target_object_id=topo_id
        ).count()
        == 0
    )


@pytest.mark.django_db
@pytest.mark.parametrize("height_scale_factor", [1, 2])
@pytest.mark.parametrize("detrend_mode", ["center", "height", "curvature"])
def test_squeezed_datafile(
    handle_usage_statistics, height_scale_factor, detrend_mode, use_dummy_cache_backend
):
    factory_kwargs = dict(height_scale_editable=True)
    if height_scale_factor is not None:
        factory_kwargs["height_scale"] = height_scale_factor
    if detrend_mode is not None:
        factory_kwargs["detrend_mode"] = detrend_mode

    topo = Topography2DFactory(**factory_kwargs)
    # Original heights are modified here. The modified values
    # should be reconstructed when loading squeezed data. This is checked here.

    assert topo.height_scale == height_scale_factor
    assert topo.detrend_mode == detrend_mode

    assert topo.squeezed_datafile
    st_topo = topo.topography(allow_squeezed=False)
    # This was read from the original data, detrending+scaling applied
    orig_heights = st_topo.heights()

    #
    # Check with pure SurfaceTopography instance
    #
    from SurfaceTopography.IO import open_topography

    df = topo.datafile.open(
        mode="rb"
    )  # no context manager, we don't want the file closed
    reader = open_topography(df)
    st_topo = reader.topography(
        topo.data_source, physical_sizes=(topo.size_x, topo.size_y)
    )
    if height_scale_factor is not None:
        st_topo = st_topo.scale(height_scale_factor)
    if detrend_mode is not None:
        st_topo = st_topo.detrend(detrend_mode)
    assert_allclose(st_topo.heights(), orig_heights)
    df.seek(0)

    #
    # so here we know that .topography(allow_squeeze=False) return the same as loading using open_topography only
    #
    # Using the squeezed data file should result in same heights

    topo.make_squeezed()
    assert topo.squeezed_datafile

    sdf = topo.squeezed_datafile.open(mode="rb")
    reader = open_topography(sdf)
    st_topo_from_squeezed = reader.topography()
    assert_allclose(st_topo_from_squeezed.heights(), orig_heights)
    sdf.seek(0)

    # Also check whether this data is returned by .topography if squeezed allowed
    st_topo_from_squeezed = topo.topography(allow_squeezed=True)
    assert_allclose(st_topo_from_squeezed.heights(), orig_heights)

    df.close()
    sdf.close()


@pytest.mark.django_db
def test_deepcopy_delete_does_not_delete_files(user_bob, handle_usage_statistics):
    surface = SurfaceFactory(created_by=user_bob)
    topo = Topography2DFactory(surface=surface)

    assert PermissionSet.objects.count() == 1

    surface_copy = surface.deepcopy()
    assert surface.topography_set.all().first().datafile
    assert surface_copy.topography_set.all().first().datafile

    assert PermissionSet.objects.count() == 2

    topo.delete()

    # Not topography left for surface but one left for surface_copy
    assert surface.topography_set.count() == 0
    assert surface_copy.topography_set.all().first().datafile

    # Both surfaces are still there so we should have two permission sets
    assert PermissionSet.objects.count() == 2

    surface.delete()
    assert PermissionSet.objects.count() == 1
    assert surface_copy.topography_set.all().first().datafile


@pytest.mark.django_db
def test_descendant_surfaces(user_alice):
    surface1 = SurfaceFactory(created_by=user_alice)
    surface2 = SurfaceFactory(created_by=user_alice)
    surface3 = SurfaceFactory(created_by=user_alice)

    surface1.tags = ["a&C"]
    surface1.save()
    surface2.tags = ["a&C/def"]
    surface2.save()
    surface3.tags = ["a&CdeF"]
    surface3.save()

    abc = Tag.objects.get(name="a&C")
    abc_slash_def = Tag.objects.get(name="a&C/def")
    abcdef = Tag.objects.get(name="a&CdeF")

    abc.authorize_user(user_alice)
    abc_slash_def.authorize_user(user_alice)
    abcdef.authorize_user(user_alice)

    assert abc.get_descendant_surfaces().count() == 2
    assert surface1 in abc.get_descendant_surfaces()
    assert surface2 in abc.get_descendant_surfaces()
    assert surface3 not in abc.get_descendant_surfaces()

    assert abc_slash_def.get_descendant_surfaces().count() == 1
    assert surface1 not in abc_slash_def.get_descendant_surfaces()
    assert surface2 in abc_slash_def.get_descendant_surfaces()
    assert surface3 not in abc_slash_def.get_descendant_surfaces()

    assert abcdef.get_descendant_surfaces().count() == 1
    assert surface1 not in abcdef.get_descendant_surfaces()
    assert surface2 not in abcdef.get_descendant_surfaces()
    assert surface3 in abcdef.get_descendant_surfaces()


@pytest.mark.django_db
def test_deepcopy_copies_attachments(user_bob, handle_usage_statistics):
    surface = SurfaceFactory(created_by=user_bob)
    topo = Topography2DFactory(surface=surface)

    surface.attachments.save_file(
        "surface-attachment.txt", "att", ContentFile("Surface attachment!")
    )
    topo.attachments.save_file(
        "topo-attachment.txt", "att", ContentFile("Topo attachment!")
    )

    assert PermissionSet.objects.count() == 1

    surface_copy = surface.deepcopy()
    assert surface.topography_set.all().first().datafile
    assert surface_copy.topography_set.all().first().datafile

    assert PermissionSet.objects.count() == 2

    assert surface.attachments.id != surface_copy.attachments.id

    file = surface.attachments.find_file("surface-attachment.txt")
    file_copy = surface_copy.attachments.find_file("surface-attachment.txt")
    assert surface.attachments.permissions.id != surface_copy.attachments.permissions.id
    assert file.id != file_copy.id
    assert file.file.name != file_copy.file.name

    topo = surface.topography_set.all().first()
    topo_copy = surface_copy.topography_set.all().first()

    assert topo.id != topo_copy.id
    assert topo.attachments.id != topo_copy.attachments.id

    file = topo.attachments.find_file("topo-attachment.txt")
    file_copy = topo_copy.attachments.find_file("topo-attachment.txt")
    assert file.id != file_copy.id
    assert file.file.name != file_copy.file.name
