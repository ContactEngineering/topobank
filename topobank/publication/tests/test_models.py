import pytest
import datetime
from freezegun import freeze_time

from topobank.manager.tests.utils import SurfaceFactory, UserFactory


@pytest.mark.django_db
@pytest.fixture
def example_pub():

    user = UserFactory()

    authors = "Alice, Bob"
    publication_date = datetime.date(2020,1,1)
    description = "This is a nice surface for testing."
    name = "Diamond Structure"

    surface = SurfaceFactory(name=name, creator=user, description=description)

    with freeze_time(publication_date):
        pub = surface.publish('cc0-1.0', authors)

    return pub


@pytest.mark.django_db
def test_citation_html(rf, example_pub):

    request = rf.get(example_pub.get_absolute_url())

    exp_html = """
    Alice, Bob. (2020). contact.engineering. <em>Diamond Structure (Version 1)</em>. <a href="{url}">{url}</a>
    """.format(url=example_pub.get_full_url(request)).strip()

    result_html = example_pub.get_citation('html', request).strip()

    assert exp_html == result_html
