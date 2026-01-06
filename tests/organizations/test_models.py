import pytest
from django.contrib.auth.models import Group

from topobank.organizations.models import (
    DEFAULT_GROUP_NAME,
    DEFAULT_ORGANIZATION_NAME,
    Organization,
)
from topobank.testing.factories import OrganizationFactory, UserFactory


@pytest.mark.django_db
def test_plugins_available_for_user():
    organization = OrganizationFactory(
        name="My University", plugins_available=["topobank_statistics", "sds_ml"]
    )
    user = UserFactory()
    user.groups.add(organization.group)
    # user is part of the organization
    orgs_for_user = Organization.objects.for_user(user)
    assert orgs_for_user.count() == 1
    assert orgs_for_user.first() == organization

    assert Organization.objects.get_plugins_available(user) == set(
        ("topobank_statistics", "sds_ml")
    )


@pytest.mark.django_db
def test_group_creation_during_org_creation():
    organization = OrganizationFactory(name="MyCompany", group=None)
    assert Group.objects.filter(name=organization.name).exists()
    assert organization.group == Group.objects.get(name=organization.name)


@pytest.mark.django_db
def test_signal_for_default_group_association():
    organization = OrganizationFactory(name=DEFAULT_ORGANIZATION_NAME)
    assert Group.objects.filter(name=DEFAULT_GROUP_NAME).exists()
    assert organization.group == Group.objects.get(name=DEFAULT_GROUP_NAME)


@pytest.mark.django_db
def test_group_deletion_during_org_deletion():
    org_name = "MyCompany"
    organization = OrganizationFactory(name=org_name, group=None)
    assert organization.group == Group.objects.get(name=org_name)

    organization.delete()
    # Group should be deleted, too
    with pytest.raises(Group.DoesNotExist):
        Group.objects.get(name=org_name)
