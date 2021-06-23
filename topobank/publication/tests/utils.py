import pytest
import datetime
from freezegun import freeze_time

from topobank.manager.tests.utils import SurfaceFactory, UserFactory


@pytest.mark.django_db
@pytest.fixture
def example_pub():
    """Fixture returning a publication which can be used as test example"""

    user = UserFactory()

    authors = "Alice, Bob"
    publication_date = datetime.date(2020,1,1)
    description = "This is a nice surface for testing."
    name = "Diamond Structure"

    surface = SurfaceFactory(name=name, creator=user, description=description)
    surface.tags = ['diamond']

    with freeze_time(publication_date):
        pub = surface.publish('cc0-1.0', authors)

    return pub
