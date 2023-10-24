"""Tests related to publication models."""
import os
import tempfile

import pytest
import datetime
import zipfile
import yaml

from freezegun import freeze_time


@pytest.mark.django_db
def test_publication_publisher_orcid_id(example_pub):
    assert example_pub.publisher_orcid_id == example_pub.surface.creator.orcid_id


@pytest.mark.django_db
def test_citation_html(rf, example_pub):

    request = rf.get(example_pub.get_absolute_url())

    exp_html = """
    Hermione Granger, Harry Potter. (2020). contact.engineering. <em>Diamond Structure (Version 1)</em>. <a href="{url}">{url}</a>
    """.format(url=example_pub.get_full_url()).strip()

    result_html = example_pub.get_citation('html').strip()

    assert exp_html == result_html


@pytest.mark.django_db
def test_citation_ris(rf, example_pub):

    request = rf.get(example_pub.get_absolute_url())

    exp_ris = """
TY  - ELEC
TI  - Diamond Structure (Version 1)
AU  - Hermione Granger
AU  - Harry Potter
PY  - 2020/01/01/
UR  - {url}
DB  - contact.engineering
N1  - This is a nice surface for testing.
KW  - surface
KW  - topography
KW  - diamond
ER  -
    """.format(url=example_pub.get_full_url()).strip()

    result_ris = example_pub.get_citation('ris').strip()

    assert exp_ris == result_ris


@pytest.mark.django_db
def test_citation_bibtex(rf, example_pub):

    request = rf.get(example_pub.get_absolute_url())

    exp_bibtex = """
        @misc{{
            diamond_structure_v1,
            title  = {{Diamond Structure (Version 1)}},
            author = {{Hermione Granger and Harry Potter}},
            year   = {{2020}},
            note   = {{This is a nice surface for testing.}},
            keywords = {{surface,topography,diamond}},
            howpublished = {{{url}}},
        }}
    """.format(url=example_pub.get_full_url()).strip()

    result_bibtex = example_pub.get_citation('bibtex').strip()

    assert exp_bibtex == result_bibtex


@pytest.mark.django_db
def test_citation_biblatex(rf, example_pub):

    request = rf.get(example_pub.get_absolute_url())

    exp_biblatex = """
        @online{{
            diamond_structure_v1,
            title  = {{Diamond Structure}},
            version = {{1}},
            author = {{Hermione Granger and Harry Potter}},
            year   = {{2020}},
            month  = {{1}},
            date   = {{2020-01-01}},
            note   = {{This is a nice surface for testing.}},
            keywords = {{surface,topography,diamond}},
            url = {{{url}}},
            urldate = {{2020-10-01}}
        }}""".format(url=example_pub.get_full_url()).strip()

    with freeze_time(datetime.date(2020, 10, 1)):
        result_biblatex = example_pub.get_citation('biblatex').strip()

    assert exp_biblatex == result_biblatex


@pytest.mark.django_db
def test_container_attributes_of_publication(example_pub):
    short_url = example_pub.short_url
    assert example_pub.container_storage_path == f'publications/{short_url}/ce-{short_url}.zip'
    assert hasattr(example_pub, 'container')
    assert not example_pub.has_doi
    assert not example_pub.has_container


@pytest.mark.parametrize('should_have_doi', [False, True])
@pytest.mark.django_db
def test_publication_full_url(example_pub, mocker, should_have_doi):
    if should_have_doi:
        has_doi_mock = mocker.patch('topobank.publication.models.Publication.has_doi', new_callable=mocker.PropertyMock)
        has_doi_mock.return_value = True

        doi_url_mock = mocker.patch('topobank.publication.models.Publication.doi_url', new_callable=mocker.PropertyMock)
        doi_url_mock.return_value = 'http://example.org'

        assert example_pub.get_full_url() == 'http://example.org'
    else:
        assert f'go/{example_pub.short_url}' in example_pub.get_full_url()


@pytest.mark.django_db
def test_renew_container(example_pub):
    assert not example_pub.has_container
    example_pub.renew_container()
    assert example_pub.has_container

    # write container to temporary file
    tmpfile = tempfile.NamedTemporaryFile(mode='wb', delete=False)
    tmpfile.write(example_pub.container.read())
    tmpfile.close()

    # check whether it's a valid zip file with one surface
    with zipfile.ZipFile(tmpfile.name) as zf:
        meta_file = zf.open('meta.yml')
        meta = yaml.safe_load(meta_file)

        meta_surfaces = meta['surfaces']

        assert len(meta_surfaces) == 1

    os.remove(tmpfile.name)



