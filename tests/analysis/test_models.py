import datetime

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.functions import Lower
from django.utils import timezone

from topobank.analysis.functions import TestImplementation
from topobank.analysis.models import Analysis, AnalysisFunction
from topobank.analysis.registry import ImplementationMissingAnalysisFunctionException
from topobank.analysis.tasks import get_current_configuration
from topobank.files.models import Manifest
from topobank.manager.models import Topography
from topobank.testing.factories import (
    FolderFactory,
    SurfaceAnalysisFactory,
    SurfaceFactory,
    TagAnalysisFactory,
    TagFactory,
    Topography1DFactory,
    TopographyAnalysisFactory,
)


@pytest.mark.django_db
def test_topography_as_analysis_subject():
    topo = Topography1DFactory()
    func = AnalysisFunction.objects.get(name="Test implementation")
    analysis = TopographyAnalysisFactory(subject_topography=topo, function=func)
    assert analysis.subject == topo


@pytest.mark.django_db
def test_surface_as_analysis_subject():
    surf = SurfaceFactory()
    func = AnalysisFunction.objects.get(name="Test implementation")
    analysis = SurfaceAnalysisFactory(subject_surface=surf, function=func)
    assert analysis.subject == surf


@pytest.mark.django_db
def test_tag_as_analysis_subject():
    s1 = SurfaceFactory()
    s2 = SurfaceFactory()
    s3 = SurfaceFactory()
    st = TagFactory.create(surfaces=[s1, s2, s3])
    st.authorize_user(s1.creator, "view")
    func = AnalysisFunction.objects.get(name="Test implementation")
    analysis = TagAnalysisFactory(subject_tag=st, function=func)
    assert analysis.subject == st


@pytest.mark.django_db
def test_exception_implementation_missing():
    # We create an implementation for surfaces, but not for analyses
    topo = Topography1DFactory()
    surface = topo.surface
    function = AnalysisFunction.objects.get(name="Test implementation")
    analysis = TopographyAnalysisFactory(function=function)
    function.eval(
        surface, analysis.kwargs, analysis.folder
    )  # that's okay, it's implemented
    with pytest.raises(ImplementationMissingAnalysisFunctionException):
        function.eval(
            analysis, analysis.kwargs, analysis.folder
        )  # that's not implemented


@pytest.mark.django_db
def test_analysis_function(test_analysis_function):
    assert test_analysis_function.implementation == TestImplementation

    surface = SurfaceFactory()
    t = Topography1DFactory(surface=surface)
    result = test_analysis_function.eval(
        t, kwargs=dict(a=2, b="bar"), folder=FolderFactory(user=surface.creator)
    )
    assert result["comment"] == "Arguments: a is 2 and b is bar"


@pytest.mark.django_db
def test_analysis_times(two_topos, test_analysis_function):
    now = timezone.now()

    analysis = TopographyAnalysisFactory.create(
        subject_topography=Topography.objects.first(),
        function=test_analysis_function,
        task_state=Analysis.SUCCESS,
        kwargs={"a": 2, "b": "abcdef"},
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13),
    )
    analysis.save()

    assert analysis.creation_time - now < datetime.timedelta(seconds=1)
    assert analysis.start_time == datetime.datetime(2018, 1, 1, 12)
    assert analysis.end_time == datetime.datetime(2018, 1, 1, 13)
    assert analysis.duration == datetime.timedelta(0, 3600)

    assert analysis.kwargs == {"a": 2, "b": "abcdef"}


@pytest.mark.django_db
def test_autoload_analysis_functions():
    # TODO this test has a problem: It's not independent from the available functions
    # At least the functions defined in this app should be available

    from django.core.management import call_command

    call_command("register_analysis_functions")

    # remember number of functions
    num_funcs = AnalysisFunction.objects.count()

    # "test" function should be there
    AnalysisFunction.objects.get(name="Test implementation")

    #
    # Call should be idempotent
    #
    call_command("register_analysis_functions")
    assert num_funcs == AnalysisFunction.objects.count()


@pytest.mark.django_db
def test_default_function_kwargs():
    from django.core.management import call_command

    call_command("register_analysis_functions")

    func = AnalysisFunction.objects.get(name="Test implementation")

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
            "muFFT",
            "muFFT.__version__",
            "LGPL-3.0",
            "https://gitlab.com/muSpectre/muFFT",
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

    import muFFT

    assert v1.dependency.import_name == "muFFT"
    assert v1.number_as_string() == muFFT.version.description()

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
    analysis = TopographyAnalysisFactory(function=test_analysis_function)
    assert len(analysis.folder) == 4
    file_path = analysis.folder.files.first().file.name
    assert default_storage.exists(file_path)
    analysis.delete()
    assert len(analysis.folder) == 0
    assert not default_storage.exists(file_path)


@pytest.mark.django_db
def test_fix_folder(test_analysis_function):
    # Old analyses do not have folders
    analysis = TopographyAnalysisFactory(
        function=test_analysis_function, folder=None,
    )
    assert Manifest.objects.count() == 1
    assert analysis.folder is None

    default_storage.save(
        f"{analysis.storage_prefix}/test1.txt", ContentFile(b"Hello world!")
    )
    default_storage.save(
        f"{analysis.storage_prefix}/test2.txt", ContentFile(b"Alles auf Horst!")
    )

    analysis.fix_folder()
    assert len(analysis.folder) == 2
    assert analysis.folder.open_file("test1.txt", "rb").read() == b"Hello world!"
    assert analysis.folder.open_file("test2.txt", "rb").read() == b"Alles auf Horst!"
