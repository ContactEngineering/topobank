import pytest

from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType

from ...manager.tests.utils import Topography1DFactory, SurfaceFactory, SurfaceCollectionFactory
from ...manager.models import Topography, Surface, SurfaceCollection
from ...organizations.tests.test_models import OrganizationFactory
from ...users.tests.factories import UserFactory

from ..functions import topography_analysis_function_for_tests, surface_analysis_function_for_tests, \
    surfacecollection_analysis_function_for_tests, VIZ_SERIES
from ..registry import AnalysisRegistry, AlreadyRegisteredAnalysisFunctionException, register_implementation
from ..urls import app_name


# from ..views import registry_view


@pytest.mark.django_db
def test_register_function_with_different_kwargs():
    def func1(topography, a=1, b="foo", progress_recorder=None, storage_prefix=None):
        pass

    def func2(topography, a=1, b="foo", c="bar", progress_recorder=None, storage_prefix=None):
        pass

    def func3(topography, a=1, b="bar", progress_recorder=None, storage_prefix=None):
        pass

    register_implementation(app_name, VIZ_SERIES, "test2")(func1)
    with pytest.raises(AlreadyRegisteredAnalysisFunctionException):
        register_implementation(app_name, VIZ_SERIES, "test2")(func2)
    with pytest.raises(AlreadyRegisteredAnalysisFunctionException):
        register_implementation(app_name, VIZ_SERIES, "test2")(func3)


@pytest.mark.django_db
def test_analysis_function_implementation_for_topography():
    reg = AnalysisRegistry()

    ct = ContentType.objects.get_for_model(Topography)

    impl = reg.get_implementation("test", ct)

    assert impl.python_function == topography_analysis_function_for_tests
    assert impl.default_kwargs == dict(a=1, b="foo")

    t = Topography1DFactory()
    result = impl.eval(t, a=2, b="bar")
    assert result['comment'] == 'Arguments: a is 2 and b is bar'

    # test function should be available because defined in analysis module
    u = UserFactory()
    assert impl.is_available_for_user(u)


@pytest.mark.django_db
def test_analysis_function_implementation_for_surface():
    reg = AnalysisRegistry()

    ct = ContentType.objects.get_for_model(Surface)

    impl = reg.get_implementation("test", ct)

    assert impl.python_function == surface_analysis_function_for_tests
    assert impl.default_kwargs == dict(a=1, b="foo")

    s = SurfaceFactory()
    result = impl.eval(s, a=2, b="bar")
    assert result['comment'] == 'a is 2 and b is bar'

    # test function should be available because defined in analysis module
    u = UserFactory()
    assert impl.is_available_for_user(u)


@pytest.mark.django_db
def test_analysis_function_implementation_for_surfacecollection():
    reg = AnalysisRegistry()

    ct = ContentType.objects.get_for_model(SurfaceCollection)

    impl = reg.get_implementation("test", ct)

    assert impl.python_function == surfacecollection_analysis_function_for_tests
    assert impl.default_kwargs == dict(a=1, b="foo")

    s1 = SurfaceFactory()
    s2 = SurfaceFactory()
    s3 = SurfaceFactory()

    sc = SurfaceCollectionFactory(surfaces=[s1, s2, s3])
    result = impl.eval(sc, a=2, b="bar")
    assert result['comment'] == 'a is 2 and b is bar'

    # test function should be available because defined in analysis module
    u = UserFactory()
    assert impl.is_available_for_user(u)


@pytest.mark.parametrize(
    ["plugins_installed", "plugins_available_for_org", "fake_func_module", "expected_is_available"],
    [
        ([], None, "topobank_plugin_A", False),  # None: No organization attached
        ([], None, "topobank.analysis.functions", True),  # None: No organization attached
        ([], "", "topobank_plugin_A", False),
        ([], "topobank_plugin_A", "topobank_plugin_A", False),
        (["topobank_plugin_A"], "plugin_A", "topobank_plugin_A", False),
        (["topobank_plugin_A"], "topobank_plugin_A", "topobank_plugin_A", True),
        (["topobank_plugin_A"], "topobank_plugin_A, topobank_plugin_B", "topobank_plugin_A", True),
        (["topobank_plugin_A", "topobank_plugin_B"], "topobank_plugin_A, topobank_plugin_B", "topobank_plugin_B", True),
        (["topobank_plugin_A", "topobank_plugin_B"], "topobank_plugin_A, topobank_plugin_B", "topobank_C", False),
    ])
@pytest.mark.django_db
def test_availability_of_implementation_in_plugin(api_rf, mocker, plugins_installed, plugins_available_for_org,
                                                  fake_func_module, expected_is_available):
    group = Group.objects.create(name="University")
    u = UserFactory()
    u.groups.add(group)
    if plugins_available_for_org is not None:
        OrganizationFactory(name="University",  # organization must have the same name as the group
                            group=group,
                            plugins_available=plugins_available_for_org)
        # User is now part of the organization with defined available plugins

    reg = AnalysisRegistry()

    ct = ContentType.objects.get_for_model(Topography)

    impl = reg.get_implementation("test", ct)
    assert impl.python_function == topography_analysis_function_for_tests

    # mock .__module__ for python function such we can test for different fake origins
    # for the underlying python function
    mocker.patch.object(topography_analysis_function_for_tests, "__module__", fake_func_module)

    def my_get_app_config(x):
        class FakeApp:
            pass

        a = FakeApp()

        if x == 'analysis':
            a.name = 'topobank.analysis'
            return a
        elif x in plugins_installed:
            a.name = x
            return a
        raise LookupError()

    from django.apps import apps
    mocker.patch.object(apps, 'get_app_config', new=my_get_app_config)

    # now check whether the implementation is available or not as expected
    assert impl.is_available_for_user(u) == expected_is_available

    # Check implementation list via API call
    # request = api_rf.get('/analysis/api/registry/')
    # request.user = u  # We need to set the user to mock authentication
    # view = AnalysisFunctionView().as_view()
    # response = view(request)
    # assert response.status_code == 200
    # print(response.data)
    # analysis_function_names = set(a['name'] for a in response.data)
    # print(plugins_installed)
    # print(plugins_available_for_org)
    # print(analysis_function_names)
