from django.urls import reverse

def test_api():
    """Test API routes"""
    assert reverse('analysis:card-series', kwargs=dict(function_id=123)) == '/analysis/api/card/series/123'
    assert reverse('analysis:registry') == '/analysis/api/registry/'
    assert reverse('analysis:data', kwargs=dict(pk=123, location='abc')) == '/analysis/data/123/abc'
    assert reverse('analysis:results-list') == '/analysis/html/list/'
    assert reverse('analysis:results-detail', kwargs=dict(pk=123)) == '/analysis/html/detail/123/'
