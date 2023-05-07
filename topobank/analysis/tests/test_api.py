from django.urls import reverse

def test_api():
    """Test API routes"""
    assert reverse('analysis:card-series') == '/analysis/api/card/series'
    assert reverse('analysis:registry') == '/analysis/api/registry/'
    assert reverse('analysis:data', kwargs=dict(pk=123, location='abc')) == '/analysis/data/123/abc'
    assert reverse('analysis:list') == '/analysis/html/list/'
