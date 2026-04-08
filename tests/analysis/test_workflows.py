import pytest

from topobank.analysis.models import Workflow
from topobank.analysis.registry import sync_implementation_classes
from topobank.testing.workflows import TestImplementation


@pytest.mark.django_db
def test_sync_and_retrieve_legacy_and_muflow_workflows():
    # Sync should pick up the TestImplementation (legacy) which is registered
    sync_implementation_classes()

    workflows = Workflow.objects.all()
    names = [w.name for w in workflows]

    assert TestImplementation.Meta.name in names, "Legacy workflow not synced to DB!"

    # We should also check for muFlow workflows, e.g., 'sds_workflows.gpr' or whatever is in muflow registry
    try:
        from muflow import registry as muflow_registry
        muflow_names = list(muflow_registry.get_all())
        if muflow_names:
            assert muflow_names[0] in names, "muFlow workflow not synced to DB!"
    except ImportError:
        pass


@pytest.mark.django_db
def test_workflow_schema_generation():
    """
    Ensure that get_kwargs_schema and get_default_kwargs do not crash for any
    registered workflows (both legacy and muFlow), which would break the API
    endpoint when listing without a subject_type filter.
    """
    sync_implementation_classes()
    workflows = Workflow.objects.all()

    assert workflows.count() > 0, "No workflows found to test"

    for workflow in workflows:
        # These methods should not raise exceptions (e.g. ValidationError)
        kwargs_schema = workflow.get_kwargs_schema()
        assert isinstance(kwargs_schema, dict), f"Expected dict for schema of {workflow.name}"

        default_kwargs = workflow.get_default_kwargs()
        assert isinstance(default_kwargs, dict), f"Expected dict for defaults of {workflow.name}"

        # Test has_implementation doesn't crash on any model class
        from topobank.manager.models import Surface, Tag, Topography
        workflow.has_implementation(Topography)
        workflow.has_implementation(Surface)
        workflow.has_implementation(Tag)
