from django.urls import reverse

def test_api():
    """Test API routes"""
    assert reverse('analysis:card-series', kwargs=dict(function_id=123)) == '/analysis/api/card/series/123'
    assert reverse('analysis:configuration-detail', kwargs=dict(pk=123)) == '/analysis/api/configuration/123/'
    assert reverse('analysis:data', kwargs=dict(pk=123, location='abc')) == '/analysis/data/123/abc'
    assert reverse('analysis:function-list') == '/analysis/api/function/'
    assert reverse('analysis:function-detail', kwargs=dict(pk=123)) == '/analysis/api/function/123/'
    assert reverse('analysis:result-detail', kwargs=dict(pk=123)) == '/analysis/api/result/123/'
