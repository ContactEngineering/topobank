"""Reading a measurement before it was processed keeps the file's instrument data.

The instrument fields of a measurement hold their defaults until `refresh_cache`
copies them from the file. Passed to the reader, those defaults replaced the
file's own instrument block, so an unprocessed read (a prediction on a fresh
upload, say) lost the tip radius and with it the reliability cutoff that a read
after processing has.
"""

import pytest

from topobank.manager.models import Topography
from topobank.testing.factories import Topography1DFactory

# A stylus profile whose file carries the tip radius
INSTRUMENTED_FILE = "dektak-1.csv"


def _unprocessed(topo):
    """The measurement as it is before its first processing."""
    Topography.objects.filter(pk=topo.pk).update(
        data_source=None,
        instrument_name="",
        instrument_type=Topography.INSTRUMENT_TYPE_UNDEFINED,
        instrument_parameters={},
    )
    return Topography.objects.get(pk=topo.pk)


@pytest.mark.django_db
def test_an_unprocessed_read_keeps_the_instrument_data_of_the_file():
    topo = _unprocessed(Topography1DFactory(filename=INSTRUMENTED_FILE))
    assert not topo.has_instrument_info

    before = topo.read(allow_squeezed=False, apply_filters=False)
    topo.refresh_cache()
    after = Topography.objects.get(pk=topo.pk).read(
        allow_squeezed=False, apply_filters=False
    )

    # The database adds an (empty) instrument name once processed; what matters
    # to an analysis are the parameters and the reliability cutoff they give
    assert before.info["instrument"]["parameters"] == after.info["instrument"]["parameters"]
    assert before.info["instrument"]["parameters"]["tip_radius"]["value"] == 2.5
    assert before.short_reliability_cutoff() == after.short_reliability_cutoff()
    assert before.short_reliability_cutoff() is not None


@pytest.mark.django_db
def test_processing_copies_the_instrument_data_into_the_database():
    topo = _unprocessed(Topography1DFactory(filename=INSTRUMENTED_FILE))

    topo.refresh_cache()

    assert topo.has_instrument_info
    assert topo.instrument_type == Topography.INSTRUMENT_TYPE_CONTACT_BASED
    assert topo.instrument_parameters["tip_radius"] == {"value": 2.5, "unit": "µm"}


@pytest.mark.django_db
def test_instrument_data_entered_for_an_unprocessed_measurement_is_used():
    topo = _unprocessed(Topography1DFactory(filename=INSTRUMENTED_FILE))
    Topography.objects.filter(pk=topo.pk).update(
        instrument_parameters={"tip_radius": {"value": 10, "unit": "µm"}}
    )
    topo = Topography.objects.get(pk=topo.pk)
    assert topo.has_instrument_info

    read = topo.read(allow_squeezed=False, apply_filters=False)

    assert read.info["instrument"]["parameters"]["tip_radius"]["value"] == 10


@pytest.mark.django_db
def test_a_processed_measurement_reads_with_the_database_values():
    """As before: once processed, the database is the source of the instrument
    data, including a user's later edits."""
    topo = Topography1DFactory(filename=INSTRUMENTED_FILE)
    Topography.objects.filter(pk=topo.pk).update(
        instrument_parameters={"tip_radius": {"value": 10, "unit": "µm"}}
    )
    topo = Topography.objects.get(pk=topo.pk)

    read = topo.read(allow_squeezed=False, apply_filters=False)

    assert read.info["instrument"]["parameters"]["tip_radius"]["value"] == 10
