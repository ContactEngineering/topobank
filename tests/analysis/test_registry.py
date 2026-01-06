import pytest
from django.contrib.auth.models import Group

from topobank.analysis.registry import get_implementation
from topobank.testing.factories import OrganizationFactory, UserFactory
from topobank.testing.workflows import TestImplementation


@pytest.mark.parametrize(
    [
        "plugins_installed",
        "plugins_available_for_org",
        "fake_func_module",
        "expected_is_available",
    ],
    [
        ([], None, "topobank_plugin_A", False),  # None: No organization attached
        (
            [],
            None,
            "topobank.testing.workflows",
            True,
        ),  # None: No organization attached
        ([], [], "topobank_plugin_A", False),
        ([], ["topobank_plugin_A"], "topobank_plugin_A", False),
        (["topobank_plugin_A"], ["plugin_A"], "topobank_plugin_A", False),
        (["topobank_plugin_A"], ["topobank_plugin_A"], "topobank_plugin_A", True),
        (
            ["topobank_plugin_A"],
            ["topobank_plugin_A", "topobank_plugin_B"],
            "topobank_plugin_A",
            True,
        ),
        (
            ["topobank_plugin_A", "topobank_plugin_B"],
            ["topobank_plugin_A", "topobank_plugin_B"],
            "topobank_plugin_B",
            True,
        ),
        (
            ["topobank_plugin_A", "topobank_plugin_B"],
            ["topobank_plugin_A", "topobank_plugin_B"],
            "topobank_C",
            False,
        ),
    ],
)
@pytest.mark.django_db
def test_availability_of_implementation_in_plugin(
    api_rf,
    mocker,
    plugins_installed,
    plugins_available_for_org,
    fake_func_module,
    expected_is_available,
):
    group = Group.objects.create(name="University")
    u = UserFactory()
    u.groups.add(group)
    if plugins_available_for_org is not None:
        OrganizationFactory(
            name="University",  # organization must have the same name as the group
            group=group,
            plugins_available=plugins_available_for_org,
        )
        # User is now part of the organization with defined available plugins

    impl = get_implementation(name="topobank.testing.test")
    assert impl == TestImplementation

    # mock .__module__ for runner class such we can test for different fake origins
    # for the underlying runner
    mocker.patch.object(
        TestImplementation, "__module__", fake_func_module
    )

    def my_get_app_config(x):
        class FakeApp:
            pass

        a = FakeApp()

        if x == "testing":
            a.name = "topobank.testing"
            return a
        elif x in plugins_installed:
            a.name = x
            return a
        raise LookupError()

    from django.apps import apps

    mocker.patch.object(apps, "get_app_config", new=my_get_app_config)

    # now check whether the implementation is available or not as expected
    assert impl.has_permission(u) == expected_is_available
