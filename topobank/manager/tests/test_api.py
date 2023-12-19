from django.urls import reverse


def test_api():
    """Test API routes"""
    assert reverse('manager:surface-api-list') == '/manager/api/surface/'
    assert reverse('manager:surface-api-detail', kwargs=dict(pk=123)) == '/manager/api/surface/123/'
    assert reverse('manager:topography-api-list') == '/manager/api/topography/'
    assert reverse('manager:topography-api-detail', kwargs=dict(pk=123)) == '/manager/api/topography/123/'
