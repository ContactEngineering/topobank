import pytest

from django.contrib.contenttypes.models import ContentType

from ..views import SimpleCardView, PlotCardView
from ..registry import AnalysisRegistry
from ..functions import topography_analysis_function_for_tests, \
    surface_analysis_function_for_tests, \
    surfacecollection_analysis_function_for_tests, \
    VIZ_SERIES, VIZ_GENERIC
from topobank.manager.tests.utils import Topography1DFactory, UserFactory, SurfaceFactory, SurfaceCollectionFactory
from topobank.manager.models import Topography, Surface, SurfaceCollection


@pytest.mark.django_db
def test_analysis_function_implementation_for_topography():
    reg = AnalysisRegistry()

    ct = ContentType.objects.get_for_model(Topography)

    impl = reg.get_implementation("test", ct)

    assert impl.python_function() == topography_analysis_function_for_tests
    assert impl.get_default_kwargs() == dict(a=1, b="foo", bins=15, window="hann")

    t = Topography1DFactory()
    result = impl.eval(t, a=2, b="bar")
    assert result['comment'] == 'Arguments: a is 2, b is bar, bins is 15 and window is hann'

    # test function should be available because defined in analysis module
    u = UserFactory()
    assert impl.is_available_for_user(u)


@pytest.mark.django_db
def test_analysis_function_implementation_for_surface():
    reg = AnalysisRegistry()

    ct = ContentType.objects.get_for_model(Surface)

    impl = reg.get_implementation("test", ct)

    assert impl.python_function() == surface_analysis_function_for_tests
    assert impl.get_default_kwargs() == dict(a=1, c="bar")

    s = SurfaceFactory()
    result = impl.eval(s, a=2, c="bar")
    assert result['comment'] == 'a is 2 and c is bar'

    # test function should be available because defined in analysis module
    u = UserFactory()
    assert impl.is_available_for_user(u)


@pytest.mark.django_db
def test_analysis_function_implementation_for_surfacecollection():
    reg = AnalysisRegistry()

    ct = ContentType.objects.get_for_model(SurfaceCollection)

    impl = reg.get_implementation("test", ct)

    assert impl.python_function() == surfacecollection_analysis_function_for_tests
    assert impl.get_default_kwargs() == dict(a=1, d="bar")

    s1 = SurfaceFactory()
    s2 = SurfaceFactory()
    s3 = SurfaceFactory()

    sc = SurfaceCollectionFactory(surfaces=[s1, s2, s3])
    result = impl.eval(sc, a=2, d="bar")
    assert result['comment'] == 'a is 2 and d is bar'

    # test function should be available because defined in analysis module
    u = UserFactory()
    assert impl.is_available_for_user(u)


@pytest.mark.parametrize(["plugins_installed", "plugins_available_for_org", "fake_func_module", "expected_is_available"],
                         [
                            ([], None, "topobank_plugin_A", False),   # None: No organization attached
                            ([], None, "topobank.analysis.functions", True),   # None: No organization attached
                            ([], "", "topobank_plugin_A", False),
                            ([], "topobank_plugin_A", "topobank_plugin_A", False),
                            (["topobank_plugin_A"], "plugin_A", "topobank_plugin_A", False),
                            (["topobank_plugin_A"], "topobank_plugin_A", "topobank_plugin_A", True),
                            (["topobank_plugin_A"], "topobank_plugin_A, topobank_plugin_B", "topobank_plugin_A", True),
                            (["topobank_plugin_A", "topobank_plugin_B"], "topobank_plugin_A, topobank_plugin_B", "topobank_plugin_B", True),
                            (["topobank_plugin_A", "topobank_plugin_B"], "topobank_plugin_A, topobank_plugin_B", "topobank_C", False),
                         ])
@pytest.mark.django_db
def test_availability_of_implementation_in_plugin(mocker, plugins_installed, plugins_available_for_org,
                                                  fake_func_module, expected_is_available):

    from topobank.organizations.tests.test_models import OrganizationFactory
    from django.contrib.auth.models import Group

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
    assert impl.python_function() == topography_analysis_function_for_tests

    # mock .__module__ for python function such we can test for different fake origins
    # for the underlying python function
    import topobank.analysis.functions
    m1 = mocker.patch.object(topobank.analysis.functions.topography_analysis_function_for_tests,
                             "__module__", fake_func_module)

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


def test_card_view_class():
    reg = AnalysisRegistry()
    assert reg.get_card_view_class(VIZ_GENERIC) == SimpleCardView
    assert reg.get_card_view_class(VIZ_SERIES) == PlotCardView

