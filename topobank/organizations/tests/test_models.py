import factory
import pytest

from topobank.manager.tests.utils import UserFactory
from ..models import Organization


class OrganizationFactory(factory.django.DjangoModelFactory):
    """Creating Organization instance for tests."""
    class Meta:
        model = "organizations.Organization"

    name = factory.Sequence(lambda n: "Organization No. {:d}".format(n))


@pytest.mark.django_db
def test_plugins_available_for_user():
    user = UserFactory()
    organization = OrganizationFactory(group=user.groups.first(),
                                       plugins_available="topobank_statistics, topobank_contact")
    # user is part of the organization
    orgs_for_user = Organization.objects.for_user(user)
    assert orgs_for_user.count() == 1
    assert orgs_for_user.first() == organization

    assert Organization.objects.get_plugins_available(user) == set(('topobank_statistics', 'topobank_contact'))







