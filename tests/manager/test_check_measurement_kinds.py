"""The `check_measurement_kinds` command."""

from io import StringIO

import pytest
from django.core.management import call_command

from topobank.manager.models import Measurement
from topobank.testing.factories import TopographyMapFactory


def run_command(**kwargs):
    out = StringIO()
    call_command("check_measurement_kinds", stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
def test_reports_nothing_when_kinds_match():
    TopographyMapFactory()
    output = run_command()
    assert "Checked 1 measurement(s)." in output
    assert "match their data file" in output


@pytest.mark.django_db
def test_reports_a_mismatched_kind():
    """
    The case the command exists for: a kind the backfill inferred wrongly.

    Written straight to the database, since the model keeps `kind` and the
    metadata's copy of it in step.
    """
    measurement = TopographyMapFactory()
    Measurement.objects.filter(pk=measurement.pk).update(
        kind="uniform-line-scan", metadata={"kind": "uniform-line-scan"}
    )

    output = run_command()

    assert f"measurement {measurement.pk}" in output
    assert "stored 'uniform-line-scan'" in output
    assert "file says 'topography-map'" in output
    assert "refresh_cache" in output


@pytest.mark.django_db
def test_reports_a_measurement_whose_channel_is_gone():
    measurement = TopographyMapFactory()
    Measurement.objects.filter(pk=measurement.pk).update(channel_name="NoSuchChannel")

    output = run_command()

    assert "could not be checked" in output
    assert f"measurement {measurement.pk}" in output


@pytest.mark.django_db
def test_skips_uninspected_measurements():
    """A measurement with no kind has nothing to disagree with."""
    measurement = TopographyMapFactory()
    Measurement.objects.filter(pk=measurement.pk).update(kind="", metadata={})

    assert "Checked 0 measurement(s)." in run_command()


@pytest.mark.django_db
def test_kind_filter():
    TopographyMapFactory()
    assert "Checked 0 measurement(s)." in run_command(kind="uniform-line-scan")
    assert "Checked 1 measurement(s)." in run_command(kind="topography-map")
