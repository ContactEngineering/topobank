"""Tests for topobank.manager.v2 API URL routing."""

from django.urls import resolve, reverse

# Topography v2 URL's


def test_topography_list_url():
    """Test that topography list URL resolves correctly."""
    url = reverse("manager:topography-v2-list")
    assert url == "/manager/v2/topography/"
    resolver = resolve(url)
    assert resolver.view_name == "manager:topography-v2-list"


def test_topography_detail_url():
    """Test that topography detail URL resolves correctly."""
    url = reverse("manager:topography-v2-detail", kwargs={"pk": 1})
    assert url == "/manager/v2/topography/1/"
    resolver = resolve(url)
    assert resolver.view_name == "manager:topography-v2-detail"
    assert resolver.kwargs["pk"] == "1"


# Surface v2 URL's


def test_surface_list_url():
    """Test that surface list URL resolves correctly."""
    url = reverse("manager:surface-v2-list")
    assert url == "/manager/v2/surface/"
    resolver = resolve(url)
    assert resolver.view_name == "manager:surface-v2-list"


def test_surface_detail_url():
    """Test that surface detail URL resolves correctly."""
    url = reverse("manager:surface-v2-detail", kwargs={"pk": 1})
    assert url == "/manager/v2/surface/1/"
    resolver = resolve(url)
    assert resolver.view_name == "manager:surface-v2-detail"
    assert resolver.kwargs["pk"] == "1"


# Zip Container v2 URL's


def test_zip_container_detail_url():
    """Test that ZIP container detail URL resolves correctly."""
    url = reverse("manager:zip-container-v2-detail", kwargs={"pk": 1})
    assert url == "/manager/v2/zip-container/1/"
    resolver = resolve(url)
    assert resolver.view_name == "manager:zip-container-v2-detail"
    assert resolver.kwargs["pk"] == "1"


# Download v2 URL's


def test_download_surface_url():
    """Test that download surface URL resolves correctly."""
    url = reverse("manager:surface-download-v2", kwargs={"surface_ids": "1,2,3"})
    assert url == "/manager/v2/download-surface/1,2,3/"
    resolver = resolve(url)
    assert resolver.view_name == "manager:surface-download-v2"
    assert resolver.kwargs["surface_ids"] == "1,2,3"


def test_download_tag_url():
    """Test that download tag URL resolves correctly."""
    url = reverse("manager:tag-download-v2", kwargs={"name": "test_tag"})
    assert url == "/manager/v2/download-tag/test_tag/"
    resolver = resolve(url)
    assert resolver.view_name == "manager:tag-download-v2"
    assert resolver.kwargs["name"] == "test_tag"


# Upload v2 URL's


def test_upload_zip_start_url():
    """Test that upload ZIP start URL resolves correctly."""
    url = reverse("manager:zip-upload-start-v2")
    assert url == "/manager/v2/upload-zip/start/"
    resolver = resolve(url)
    assert resolver.view_name == "manager:zip-upload-start-v2"


def test_upload_zip_finish_url():
    """Test that upload ZIP finish URL resolves correctly."""
    url = reverse("manager:zip-upload-finish-v2", kwargs={"pk": 1})
    assert url == "/manager/v2/upload-zip/finish/1/"
    resolver = resolve(url)
    assert resolver.view_name == "manager:zip-upload-finish-v2"
    # Path converter returns int for <int:pk>
    assert resolver.kwargs["pk"] == 1
