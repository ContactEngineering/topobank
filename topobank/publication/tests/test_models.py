"""Tests related to publication models."""
import pytest
import datetime
from freezegun import freeze_time

from django.shortcuts import reverse

from .utils import example_pub


@pytest.mark.django_db
def test_publication_orcid_id(example_pub):
    assert example_pub.publisher_orcid_id == example_pub.surface.creator.orcid_id


@pytest.mark.django_db
def test_citation_html(rf, example_pub):

    request = rf.get(example_pub.get_absolute_url())

    exp_html = """
    Alice, Bob. (2020). contact.engineering. <em>Diamond Structure (Version 1)</em>. <a href="{url}">{url}</a>
    """.format(url=example_pub.get_full_url(request)).strip()

    result_html = example_pub.get_citation('html', request).strip()

    assert exp_html == result_html


@pytest.mark.django_db
def test_citation_ris(rf, example_pub):

    request = rf.get(example_pub.get_absolute_url())

    exp_ris = """
TY  - ELEC
TI  - Diamond Structure (Version 1)
AU  - Alice
AU  - Bob
PY  - 2020/01/01/
UR  - {url}
DB  - contact.engineering
N1  - This is a nice surface for testing.
KW  - surface
KW  - topography
KW  - diamond
ER  -
    """.format(url=example_pub.get_full_url(request)).strip()

    result_ris = example_pub.get_citation('ris', request).strip()

    assert exp_ris == result_ris


@pytest.mark.django_db
def test_citation_bibtex(rf, example_pub):

    request = rf.get(example_pub.get_absolute_url())

    exp_bibtex = """
        @misc{{
            diamond_structure_v1,
            title  = {{Diamond Structure (Version 1)}},
            author = {{Alice and Bob}},
            year   = {{2020}},
            note   = {{This is a nice surface for testing.}},
            keywords = {{surface,topography,diamond}},
            howpublished = {{{url}}},
        }}
    """.format(url=example_pub.get_full_url(request)).strip()

    result_bibtex = example_pub.get_citation('bibtex', request).strip()

    assert exp_bibtex == result_bibtex


@pytest.mark.django_db
def test_citation_biblatex(rf, example_pub):

    request = rf.get(example_pub.get_absolute_url())

    exp_biblatex = """
        @online{{
            diamond_structure_v1,
            title  = {{Diamond Structure}},
            version = {{1}},
            author = {{Alice and Bob}},
            year   = {{2020}},
            month  = {{1}},
            date   = {{2020-01-01}},
            note   = {{This is a nice surface for testing.}},
            keywords = {{surface,topography,diamond}},
            url = {{{url}}},
            urldate = {{2020-10-01}}
        }}""".format(url=example_pub.get_full_url(request)).strip()

    with freeze_time(datetime.date(2020, 10, 1)):
        result_biblatex = example_pub.get_citation('biblatex', request).strip()

    assert exp_biblatex == result_biblatex


@pytest.mark.django_db
def test_redirection_invalid_publication_link(client, handle_usage_statistics):
    response = client.get(reverse('publication:go', kwargs=dict(short_url='THISISNONSENSE')))
    assert response.status_code == 404
