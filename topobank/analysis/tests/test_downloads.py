"""
Test of downloads module.
"""

import zipfile
from io import BytesIO, StringIO

from django.shortcuts import reverse

from topobank.analysis.downloads import download_plot_analyses_to_txt, download_contact_mechanics_analyses_as_zip
from topobank.analysis.tests.utils import TopographyAnalysisFactory, AnalysisFunctionImplementationFactory, \
    AnalysisFunctionFactory, AnalysisFunction
from topobank.utils import assert_in_content

import pytest


@pytest.mark.django_db
def test_download_plot_analyses_to_txt(rf):
    func = AnalysisFunctionFactory()
    impl = AnalysisFunctionImplementationFactory(function=func)
    analysis = TopographyAnalysisFactory(function=func)
    request = rf.get(reverse('analysis:download',
                             kwargs=dict(ids=str(analysis.id),
                                         card_view_flavor='plot',
                                         file_format='txt')))

    response = download_plot_analyses_to_txt(request, [analysis])

    assert_in_content(response, 'Fibonacci')
    assert_in_content(response, '1.000000000000000000e+00 0.000000000000000000e+00 0.000000000000000000e+00')
    assert_in_content(response, '8.000000000000000000e+00 1.300000000000000000e+01 0.000000000000000000e+00')


@pytest.mark.django_db
def test_download_contact_analyses_to_zip(rf):
    func = AnalysisFunctionFactory()
    impl = AnalysisFunctionImplementationFactory(function=func)

    storage_prefix = "test/"

    result = dict(
        name='Contact mechanics',
        area_per_pt=0.1,
        maxiter=100,
        min_pentol=0.01,
        mean_pressures=[1, 2, 3, 4],
        total_contact_areas=[2, 4, 6, 8],
        mean_displacements=[3, 5, 7, 9],
        mean_gaps=[4, 6, 8, 10],
        converged=[True, True, False, True],
        data_paths=[storage_prefix + "step-0", storage_prefix + "step-1",
                    storage_prefix + "step-2", storage_prefix + "step-3", ],
        effective_kwargs=dict(
            substrate_str="periodic",
            hardness=1,
            nsteps=11,
            pressures=[1, 2, 3, 4],
            maxiter=100,
        )
    )

    analysis = TopographyAnalysisFactory(function=func, result=result)

    # create files in storage for zipping
    from django.core.files.storage import default_storage

    # files_to_delete = []

    for k in range(4):
        fn = f"{analysis.storage_prefix}/step-{k}/nc/results.nc"
        default_storage.save(fn, StringIO(f"test content for step {k}"))

    request = rf.get(reverse('analysis:download',
                             kwargs=dict(ids=str(analysis.id),
                                         card_view_flavor=AnalysisFunction.CONTACT_MECHANICS,
                                         file_format='zip')))

    response = download_contact_mechanics_analyses_as_zip(request, [analysis])

    archive = zipfile.ZipFile(BytesIO(response.content))

    expected_filenames = [
        "README.txt",
        f"{analysis.subject.name}/plot.csv",
        f"{analysis.subject.name}/info.txt",
        f"{analysis.subject.name}/result-step-0.nc",
        f"{analysis.subject.name}/result-step-1.nc",
        f"{analysis.subject.name}/result-step-2.nc",
        f"{analysis.subject.name}/result-step-3.nc",
    ]

    assert sorted(expected_filenames) == sorted(archive.namelist())
    # TODO check file contents
    # TODO delete temporary data from storage
