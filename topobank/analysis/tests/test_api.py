from django.urls import reverse

def test_api():
    """Test API routes"""
    assert reverse('analysis:card-series') == '/analysis/card/series'
    assert reverse('analysis:registry') == '/analysis/registry/'
    assert reverse('analysis:data', kwargs=dict(pk=123, location='abc')) == '/analysis/data/123/abc'
