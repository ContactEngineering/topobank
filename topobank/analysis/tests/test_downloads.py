"""
Test of downloads module.
"""
import pickle
import zipfile
from io import BytesIO, StringIO

from django.shortcuts import reverse

from topobank.analysis.downloads import download_plot_analyses_to_txt
from topobank.analysis.tests.utils import TopographyAnalysisFactory, AnalysisFunction
from topobank.utils import assert_in_content

import pytest


@pytest.mark.django_db
def test_download_plot_analyses_to_txt(rf):
    func = AnalysisFunction.objects.get(name="test")
    analysis = TopographyAnalysisFactory(function=func)
    request = rf.get(reverse('analysis:download',
                             kwargs=dict(ids=str(analysis.id),
                                         art='plot',
                                         file_format='txt')))

    response = download_plot_analyses_to_txt(request, [analysis])

    assert_in_content(response, 'Fibonacci')
    assert_in_content(response, '1.000000000000000000e+00 0.000000000000000000e+00 0.000000000000000000e+00')
    assert_in_content(response, '8.000000000000000000e+00 1.300000000000000000e+01 0.000000000000000000e+00')

