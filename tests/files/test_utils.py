import pytest

from topobank.files.utils import file_storage_path


class _Stub:
    """The two attributes `file_storage_path` reads off a manifest."""

    def __init__(self, kind, pk=7):
        self.kind = kind
        self.pk = pk
        self.id = pk


@pytest.mark.parametrize("kind", ["raw", "att"])
def test_user_uploaded_files_store_under_uploads(kind):
    # Deployments point their storage-upload notification at this prefix, so a
    # kind that moves out of it stops confirming over that notification.
    assert file_storage_path(_Stub(kind), "report.pdf") == "uploads/7/report.pdf"


@pytest.mark.parametrize("kind", ["der", "N/A"])
def test_system_written_files_store_under_the_data_lake(kind):
    assert file_storage_path(_Stub(kind), "result.nc") == "data-lake/7/result.nc"


def test_an_unsaved_manifest_has_no_storage_path():
    with pytest.raises(RuntimeError):
        file_storage_path(_Stub("raw", pk=None), "report.pdf")
