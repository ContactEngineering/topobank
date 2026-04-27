import datetime

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.functions import Lower
from django.utils import timezone

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.registry import (
    WorkflowNotImplementedException,
    get_analysis_function_names,
)
from topobank.analysis.tasks import get_current_configuration
from topobank.files.models import Manifest
from topobank.manager.models import Topography
from topobank.testing.factories import (
    SurfaceAnalysisFactory,
    SurfaceFactory,
    TagAnalysisFactory,
    TagFactory,
    Topography1DFactory,
    TopographyAnalysisFactory,
)
from topobank.testing.workflows import TestImplementation


@pytest.mark.django_db
def test_topography_as_analysis_subject():
    topo = Topography1DFactory()
    analysis = TopographyAnalysisFactory(subject_topography=topo)
    assert analysis.subject == topo


@pytest.mark.django_db
def test_surface_as_analysis_subject():
    surf = SurfaceFactory()
    analysis = SurfaceAnalysisFactory(subject_surface=surf)
    assert analysis.subject == surf


@pytest.mark.django_db
def test_tag_as_analysis_subject():
    s1 = SurfaceFactory()
    s2 = SurfaceFactory()
    s3 = SurfaceFactory()
    st = TagFactory.create(surfaces=[s1, s2, s3])
    st.authorize_user(s1.created_by, "view")
    analysis = TagAnalysisFactory(subject_tag=st)
    assert analysis.subject == st


@pytest.mark.django_db
def test_exception_implementation_missing(test_analysis_function):
    # We create an implementation for surfaces, but not for analyses
    function = Workflow(name="topobank.testing.topography_only_test")
    analysis = TopographyAnalysisFactory(workflow_name=function.name)
    analysis.folder.remove_files()
    function.eval(analysis)  # that's okay, it's implemented
    analysis = SurfaceAnalysisFactory()
    with pytest.raises(WorkflowNotImplementedException):
        function.eval(analysis)  # that's not implemented


@pytest.mark.django_db
def test_analysis_function(test_analysis_function):
    assert test_analysis_function.implementation == TestImplementation

    surface = SurfaceFactory()
    t = Topography1DFactory(surface=surface)
    analysis = TopographyAnalysisFactory.create(
        subject_topography=t,
        kwargs=dict(a=2, b="bar"),
    )
    analysis.folder.remove_files()  # Make sure there are no files
    test_analysis_function.eval(analysis)
    # Results are now stored as files, access via analysis.result
    assert analysis.result["comment"] == "Arguments: a is 2 and b is bar"


@pytest.mark.django_db
def test_analysis_times(two_topos, test_analysis_function):
    now = timezone.now()

    analysis = TopographyAnalysisFactory.create(
        subject_topography=Topography.objects.first(),
        task_state=WorkflowResult.SUCCESS,
        kwargs={"a": 2, "b": "abcdef"},
        task_start_time=datetime.datetime(2018, 1, 1, 12),
        task_end_time=datetime.datetime(2018, 1, 1, 13),
    )
    analysis.save()

    assert analysis.created_at - now < datetime.timedelta(seconds=1)
    assert analysis.task_start_time == datetime.datetime(2018, 1, 1, 12)
    assert analysis.task_end_time == datetime.datetime(2018, 1, 1, 13)
    assert analysis.task_duration == datetime.timedelta(0, 3600)

    assert analysis.kwargs == {"a": 2, "b": "abcdef"}


@pytest.mark.django_db
def test_autoload_analysis_functions():
    # At least the functions defined in this app should be available
    names = get_analysis_function_names()

    # "test" function should be there
    assert "topobank.testing.test" in names

    # Registry is populated at import time; calling again returns the same result
    names2 = get_analysis_function_names()
    assert set(names) == set(names2)


@pytest.mark.django_db
def test_default_function_kwargs():
    func = Workflow(name="topobank.testing.test")
    expected_kwargs = dict(a=1, b="foo")
    assert func.get_default_kwargs() == expected_kwargs


@pytest.mark.django_db
def test_current_configuration(settings):
    settings.TRACKED_DEPENDENCIES = [
        (
            "SurfaceTopography",
            "SurfaceTopography.__version__",
            "MIT",
            "https://github.com/ContactEngineering/SurfaceTopography",
        ),
        (
            "NuMPI",
            "NuMPI.__version__",
            "MIT",
            "https://github.com/IMTEK-Simulation/NuMPI",
        ),
        (
            "muGrid",
            "muGrid.__version__",
            "LGPL-3.0",
            "https://github.com/muSpectre/muGrid",
        ),
        (
            "topobank",
            "topobank.__version__",
            "MIT",
            "https://github.com/ContactEngineering/SurfaceTopography",
        ),
        ("numpy", "numpy.version.full_version", "BSD 3-Clause", "https://numpy.org/"),
    ]

    config = get_current_configuration()

    versions = config.versions.order_by(Lower("dependency__import_name"))
    # Lower: Just to have a defined order independent of database used

    assert len(versions) == 5

    v1, v2, v3, v4, v5 = versions

    import muGrid

    assert v1.dependency.import_name == "muGrid"
    assert v1.number_as_string() == muGrid.__version__

    import NuMPI

    assert v2.dependency.import_name == "NuMPI"
    assert v2.number_as_string() == NuMPI.__version__

    import numpy

    assert v3.dependency.import_name == "numpy"
    assert v3.number_as_string() == numpy.version.full_version

    import SurfaceTopography

    assert v4.dependency.import_name == "SurfaceTopography"
    assert v4.number_as_string() == SurfaceTopography.__version__

    import topobank

    assert v5.dependency.import_name == "topobank"
    assert v5.number_as_string() == topobank.__version__


@pytest.mark.django_db
def test_analysis_delete_removes_files(test_analysis_function):
    analysis = TopographyAnalysisFactory()
    assert len(analysis.folder) == 4
    file_path = analysis.folder.files.first().file.name
    assert default_storage.exists(file_path)
    analysis.delete()
    assert len(analysis.folder) == 0
    assert not default_storage.exists(file_path)


@pytest.mark.skip(reason="Test is for deprecated functionality")
@pytest.mark.django_db
def test_fix_folder(test_analysis_function):
    # Old analyses do not have folders
    assert Manifest.objects.count() == 0
    analysis = TopographyAnalysisFactory(
        workflow_name=test_analysis_function.name,
        folder=None,
    )
    print([m for m in Manifest.objects.all()])
    assert Manifest.objects.count() == 9
    assert analysis.folder is None

    default_storage.save(
        f"{analysis.storage_prefix}/test1.txt", ContentFile(b"Hello world!")
    )
    default_storage.save(
        f"{analysis.storage_prefix}/test2.txt", ContentFile(b"Alles auf Horst!")
    )

    analysis.fix_folder()
    assert len(analysis.folder) == 3  # fix_folder implicitly creates result.json
    assert analysis.folder.open_file("test1.txt", "rb").read() == b"Hello world!"
    assert analysis.folder.open_file("test2.txt", "rb").read() == b"Alles auf Horst!"


@pytest.mark.django_db
def test_submit_again(test_analysis_function):
    analysis = TopographyAnalysisFactory()
    new_analysis = analysis.submit_again()
    assert new_analysis.task_state == WorkflowResult.PENDING
