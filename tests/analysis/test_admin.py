"""
Tests for the `WorkflowResult` admin.

`SubjectTypeFilter` builds its lookup key by interpolating the selected value
into ``subject_{value}__isnull``, so the value is not merely a label -- it has to
match the name of a subject field on `WorkflowResult`. A mismatch is invisible
until someone selects the filter in the admin, at which point the queryset raises
`FieldError`, which is what these tests guard against.
"""

import pytest

from topobank.analysis.admin import SubjectTypeFilter
from topobank.analysis.models import WorkflowResult
from topobank.testing.factories import (
    MeasurementAnalysisFactory,
    SurfaceAnalysisFactory,
    SurfaceFactory,
    TagAnalysisFactory,
    TagFactory,
)


def filter_for(value):
    """Build the filter with `value` selected, bypassing the request plumbing."""
    subject_filter = SubjectTypeFilter.__new__(SubjectTypeFilter)
    subject_filter.value = lambda: value
    return subject_filter


def test_every_offered_value_builds_a_valid_lookup():
    """
    Each value the filter offers must name an existing subject field.

    The values come from `lookups` rather than being written out here, so that
    this fails if the offered values and the model's fields drift apart -- which
    is the whole failure mode. Needs no database: the `FieldError` is raised while
    the lookup is resolved against the model, before any query runs.
    """
    for value, _label in filter_for(None).lookups(None, None):
        queryset = filter_for(value).queryset(None, WorkflowResult.objects.all())
        # An offered value that no branch handles would silently return the
        # queryset untouched, so check the filter was actually applied.
        assert queryset.query.where, f"{value!r} is offered but filters nothing"
        str(queryset.query)  # forces lookup resolution


def test_an_unknown_value_is_ignored_rather_than_raising():
    queryset = WorkflowResult.objects.all()
    assert filter_for("nonsense").queryset(None, queryset) is queryset


def test_the_offered_values_are_exactly_the_ones_handled():
    """
    The lookups and the `queryset` branch are two lists that have to agree.

    They are written out separately, so a value added to one and not the other
    would silently do nothing.
    """
    offered = {value for value, _label in filter_for(None).lookups(None, None)}
    assert offered == {"tag", "surface", "measurement"}


@pytest.mark.django_db
def test_the_measurement_filter_selects_measurement_results():
    """The filter has to actually select, not just resolve."""
    measurement_analysis = MeasurementAnalysisFactory()
    SurfaceAnalysisFactory()
    surface = SurfaceFactory()
    tag = TagFactory.create(surfaces=[surface])
    # A tag resolves its surfaces through the permission system, so it needs an
    # authorized user before an analysis can be built for it.
    tag.authorize_user(surface.created_by, "view")
    TagAnalysisFactory(subject_tag=tag)

    selected = filter_for("measurement").queryset(None, WorkflowResult.objects.all())

    assert list(selected) == [measurement_analysis]


@pytest.mark.django_db
def test_the_subject_type_column_names_the_model():
    from topobank.analysis.admin import WorkflowResultAdmin

    analysis = MeasurementAnalysisFactory()
    admin = WorkflowResultAdmin.__new__(WorkflowResultAdmin)

    assert admin.subject_type(analysis) == "Measurement"
