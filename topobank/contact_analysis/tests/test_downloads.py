import pytest
import zipfile
from io import StringIO, BytesIO

from django.shortcuts import reverse

from topobank.analysis.models import AnalysisFunction
from topobank.analysis.tests.utils import TopographyAnalysisFactory

from topobank.contact_analysis.downloads import download_contact_mechanics_analyses_as_zip
from topobank.contact_analysis.functions import ART_CONTACT_MECHANICS


@pytest.mark.django_db
def test_download_contact_analyses_to_zip(rf, example_contact_analysis):

    request = rf.get(reverse('analysis:download',
                             kwargs=dict(ids=str(example_contact_analysis.id),
                                         art=ART_CONTACT_MECHANICS,
                                         file_format='zip')))

    response = download_contact_mechanics_analyses_as_zip(request, [example_contact_analysis])

    archive = zipfile.ZipFile(BytesIO(response.content))

    expected_filenames = [
        "README.txt",
        f"{example_contact_analysis.subject.name}/plot.csv",
        f"{example_contact_analysis.subject.name}/info.txt",
        f"{example_contact_analysis.subject.name}/result-step-0.nc",
        f"{example_contact_analysis.subject.name}/result-step-1.nc",
        f"{example_contact_analysis.subject.name}/result-step-2.nc",
        f"{example_contact_analysis.subject.name}/result-step-3.nc",
    ]

    assert sorted(expected_filenames) == sorted(archive.namelist())
    # TODO check file contents
    # TODO delete temporary data from storage
