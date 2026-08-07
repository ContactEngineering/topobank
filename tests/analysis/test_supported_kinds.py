"""
Workflows declare which kinds of measurement they support.

With one `Measurement` model covering many kinds, the subject's model class no
longer says whether a workflow applies to it: a roughness workflow must run on
height data but not on, say, a spectrum. `Meta.supported_kinds` is that gate.
"""

import pytest

from topobank.analysis.models import Workflow
from topobank.analysis.registry import (
    WorkflowNotImplementedException,
    WorkflowRegistryException,
    get_implementation,
)
from topobank.analysis.workflows import WorkflowImplementation
from topobank.manager.models import Measurement, Surface
from topobank.testing.factories import (
    SurfaceFactory,
    TopographyMapFactory,
    UserFactory,
)
from topobank.testing.workflows import ALL_HEIGHT_KINDS

TEST_WORKFLOW = "topobank.testing.test"


def test_test_workflows_declare_the_height_kinds():
    implementation = get_implementation(name=TEST_WORKFLOW)
    assert implementation.get_supported_kinds() == ALL_HEIGHT_KINDS


def test_supports_kind():
    implementation = get_implementation(name=TEST_WORKFLOW)
    assert implementation.supports_kind("topography-map")
    assert implementation.supports_kind("nonuniform-line-scan")
    # A kind that did not exist when the workflow was written.
    assert not implementation.supports_kind("xps-spectrum")


def test_missing_declaration_is_an_error_not_a_wildcard():
    """
    A workflow that implements measurements must say which kinds it handles.

    Defaulting to "all kinds" would mean every existing height workflow silently
    claims any kind added later, which is exactly the failure this design avoids.
    """

    class Undeclared(WorkflowImplementation):
        class Meta:
            name = "topobank.testing.undeclared"
            display_name = "Undeclared"
            implementations = {Measurement: "measurement_implementation"}

        def measurement_implementation(self, analysis, **kwargs):
            pass

    with pytest.raises(WorkflowRegistryException) as excinfo:
        Undeclared.get_supported_kinds()
    assert "supported_kinds" in str(excinfo.value)


@pytest.mark.django_db
class TestSubjectSupport:
    def test_supports_a_height_measurement(self, test_workflow):
        measurement = TopographyMapFactory()
        implementation = get_implementation(name=TEST_WORKFLOW)
        assert implementation.supports_subject(measurement)

    def test_does_not_support_a_measurement_of_an_unclaimed_kind(self, test_workflow):
        measurement = TopographyMapFactory()
        Measurement.objects.filter(pk=measurement.pk).update(
            kind="xps-spectrum", metadata={"kind": "xps-spectrum"}
        )
        measurement.refresh_from_db()

        implementation = get_implementation(name=TEST_WORKFLOW)
        # The model class is implemented, but this kind is not.
        assert implementation.has_implementation(Measurement)
        assert not implementation.supports_subject(measurement)

    def test_surfaces_are_unaffected_by_the_kind_gate(self, test_workflow):
        """The gate only applies to measurements; other subjects are unchanged."""
        implementation = get_implementation(name=TEST_WORKFLOW)
        assert implementation.supports_subject(SurfaceFactory())
        assert implementation.has_implementation(Surface)


@pytest.mark.django_db
class TestSubmission:
    def test_submitting_an_unsupported_kind_is_refused(self, test_workflow):
        """
        Submission is where a user would hit this, so the refusal has to happen
        there rather than inside the worker.
        """
        user = UserFactory()
        surface = SurfaceFactory(created_by=user)
        measurement = TopographyMapFactory(surface=surface)
        Measurement.objects.filter(pk=measurement.pk).update(
            kind="xps-spectrum", metadata={"kind": "xps-spectrum"}
        )
        measurement.refresh_from_db()

        workflow = Workflow(TEST_WORKFLOW)
        with pytest.raises(WorkflowNotImplementedException) as excinfo:
            workflow.submit(user, measurement)
        assert "xps-spectrum" in str(excinfo.value)

    def test_submitting_a_supported_kind_works(self, test_workflow):
        user = UserFactory()
        surface = SurfaceFactory(created_by=user)
        measurement = TopographyMapFactory(surface=surface)

        result = Workflow(TEST_WORKFLOW).submit(user, measurement)
        assert result is not None
        assert result.subject_measurement_id == measurement.id
