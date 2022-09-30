import factory

from ..models import Organization


class OrganizationFactory(factory.django.DjangoModelFactory):
    """Creating Organization instance for tests."""
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: "Organization No. {:d}".format(n))
