import pytest

from topobank.analysis.models import Workflow
from topobank.analysis.registry import get_analysis_function_names
from topobank.testing.workflows import TestImplementation


@pytest.mark.django_db
def test_retrieve_registry_workflows():
    names = get_analysis_function_names()

    assert TestImplementation.Meta.name in names, "Legacy workflow not in registry!"

    try:
        from muflow import registry as muflow_registry
        muflow_names = list(muflow_registry.get_all())
        if muflow_names:
            assert muflow_names[0] in names, "muFlow workflow not in registry!"
    except ImportError:
        pass


@pytest.mark.django_db
def test_workflow_schema_generation():
    """
    Ensure that get_kwargs_schema and get_default_kwargs do not crash for any
    registered workflows (both legacy and muFlow).
    """
    names = get_analysis_function_names()
    assert len(names) > 0, "No workflows found to test"

    for name in names:
        workflow = Workflow(name=name)

        # These methods should not raise exceptions (e.g. ValidationError)
        kwargs_schema = workflow.get_kwargs_schema()
        assert isinstance(kwargs_schema, dict), f"Expected dict for schema of {name}"

        default_kwargs = workflow.get_default_kwargs()
        assert isinstance(default_kwargs, dict), f"Expected dict for defaults of {name}"

        # Test has_implementation doesn't crash on any model class
        from topobank.manager.models import Surface, Tag, Topography
        workflow.has_implementation(Topography)
        workflow.has_implementation(Surface)
        workflow.has_implementation(Tag)
