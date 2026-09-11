from unittest.mock import patch

import pytest
from django.core.exceptions import SuspiciousFileOperation, SuspiciousOperation

from topobank.files.upload import (
    MEASUREMENT_CONTENT_TYPE,
    format_bytes_binary,
    get_upload_instructions,
    is_previewable,
    max_upload_bytes,
    storage_content_type,
)
from topobank.settings import defaults


class _Stub:
    """What `get_upload_instructions` reads off a manifest."""

    def __init__(self, kind, filename, content_type="", pk=7):
        self.id = pk
        self.kind = kind
        self.filename = filename
        self.content_type = content_type

    def generate_storage_path(self):
        return f"uploads/{self.id}/{self.filename}"


@pytest.fixture
def s3(settings):
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    with patch("topobank.files.upload.default_storage") as storage:
        storage._normalize_name.side_effect = lambda path: f"media/{path}"
        storage.bucket.meta.client.generate_presigned_post.return_value = {
            "url": "https://s3.example.com/test-bucket",
            "fields": {"key": "media/uploads/7/x"},
        }
        yield storage


def _presign_kwargs(storage):
    return storage.bucket.meta.client.generate_presigned_post.call_args.kwargs


class TestGetUploadInstructions:
    def test_returns_none_when_storage_cannot_be_presigned(self, s3):
        del s3.bucket  # a filesystem backend has none
        assert get_upload_instructions(_Stub("raw", "scan.di")) is None

    @pytest.mark.parametrize("exc", [SuspiciousFileOperation, SuspiciousOperation])
    def test_unusable_filename_returns_none(self, s3, exc):
        s3._normalize_name.side_effect = exc("bad path")
        assert get_upload_instructions(_Stub("raw", "../etc/passwd")) is None

    def test_is_a_post_to_the_manifest_key(self, s3):
        result = get_upload_instructions(_Stub("raw", "scan.di"))

        assert result["method"] == "POST"
        assert result["url"] == "https://s3.example.com/test-bucket"
        kwargs = _presign_kwargs(s3)
        assert kwargs["Bucket"] == "test-bucket"
        assert kwargs["Key"] == "media/uploads/7/scan.di"

    @pytest.mark.parametrize("filename", ["scan.di", "scan.png"])
    def test_measurement_policy(self, s3, settings, filename):
        # The opaque setting is for attachments; a measurement ignores it.
        settings.TOPOBANK_OPAQUE_CONTENT_TYPE = "application/x-custom"

        get_upload_instructions(_Stub("raw", filename))

        kwargs = _presign_kwargs(s3)
        assert ["content-length-range", 1, max_upload_bytes("raw")] in kwargs[
            "Conditions"
        ]
        assert {"Content-Type": MEASUREMENT_CONTENT_TYPE} in kwargs["Conditions"]
        assert kwargs["Fields"] == {"Content-Type": MEASUREMENT_CONTENT_TYPE}

    def test_attachment_policy_uses_the_persisted_type(self, s3):
        get_upload_instructions(_Stub("att", "photo.png", content_type="image/png"))

        kwargs = _presign_kwargs(s3)
        assert ["content-length-range", 1, max_upload_bytes("att")] in kwargs[
            "Conditions"
        ]
        assert {"Content-Type": "image/png"} in kwargs["Conditions"]
        assert kwargs["Fields"] == {"Content-Type": "image/png"}

    def test_attachment_without_persisted_type_derives_it(self, s3):
        get_upload_instructions(_Stub("att", "spec.pdf"))
        assert _presign_kwargs(s3)["Fields"] == {"Content-Type": "binary/octet-stream"}

        get_upload_instructions(_Stub("att", "PHOTO.JPG"))
        assert _presign_kwargs(s3)["Fields"] == {"Content-Type": "image/jpeg"}

    def test_ceiling_follows_the_setting(self, s3, settings):
        settings.TOPOBANK_MAX_ATTACHMENT_UPLOAD_BYTES = 1024
        settings.TOPOBANK_MAX_MEASUREMENT_UPLOAD_BYTES = 2048

        get_upload_instructions(_Stub("att", "spec.pdf"))
        assert ["content-length-range", 1, 1024] in _presign_kwargs(s3)["Conditions"]

        get_upload_instructions(_Stub("raw", "scan.di"))
        assert ["content-length-range", 1, 2048] in _presign_kwargs(s3)["Conditions"]

    def test_expiry_follows_the_setting_unless_given(self, s3, settings):
        settings.TOPOBANK_UPLOAD_EXPIRE_SECONDS = 60

        get_upload_instructions(_Stub("raw", "scan.di"))
        assert _presign_kwargs(s3)["ExpiresIn"] == 60

        get_upload_instructions(_Stub("raw", "scan.di"), expire=5)
        assert _presign_kwargs(s3)["ExpiresIn"] == 5

    @pytest.mark.parametrize("kind", ["der", "N/A"])
    def test_system_written_kinds_are_never_presigned(self, s3, kind):
        with pytest.raises(ValueError):
            get_upload_instructions(_Stub(kind, "result.nc"))

    def test_a_system_written_kind_raises_before_the_storage_check(self, s3):
        # Same failure whatever the backend, so the bug cannot hide in tests.
        del s3.bucket
        with pytest.raises(ValueError):
            get_upload_instructions(_Stub("der", "result.nc"))


class TestSettings:
    def test_defaults_apply_when_unset(self):
        # The test settings define none of these, so `defaults` is in play.
        assert max_upload_bytes("raw") == defaults.TOPOBANK_MAX_MEASUREMENT_UPLOAD_BYTES
        assert max_upload_bytes("att") == defaults.TOPOBANK_MAX_ATTACHMENT_UPLOAD_BYTES
        assert (
            storage_content_type("a.png")
            == defaults.TOPOBANK_INLINE_PREVIEW_TYPES[".png"]
        )
        assert storage_content_type("a.pdf") == defaults.TOPOBANK_OPAQUE_CONTENT_TYPE

    def test_the_ceiling_follows_the_kind(self, settings):
        settings.TOPOBANK_MAX_MEASUREMENT_UPLOAD_BYTES = 2048
        settings.TOPOBANK_MAX_ATTACHMENT_UPLOAD_BYTES = 1024
        assert max_upload_bytes("raw") == 2048
        assert max_upload_bytes("att") == 1024

    def test_measurement_ceiling_stays_within_the_s3_object_limit(self):
        assert defaults.TOPOBANK_MAX_MEASUREMENT_UPLOAD_BYTES <= 5 * 1024**3

    def test_unknown_kind_has_no_ceiling(self):
        with pytest.raises(ValueError):
            max_upload_bytes("der")


class TestPreviewAllowlist:
    @pytest.mark.parametrize(
        "name", ["a.png", "a.jpg", "a.jpeg", "a.webp", "a.gif", "A.PNG", "dir/a.Jpg"]
    )
    def test_inline_types_are_previewable(self, name):
        assert is_previewable(name)
        assert storage_content_type(name) != defaults.TOPOBANK_OPAQUE_CONTENT_TYPE

    @pytest.mark.parametrize(
        "name", ["a.svg", "a.html", "a.pdf", "a.txt", "a", "", None, "png"]
    )
    def test_everything_else_is_opaque(self, name):
        assert not is_previewable(name)
        assert storage_content_type(name) == "binary/octet-stream"

    def test_the_allowlist_is_a_setting(self, settings):
        settings.TOPOBANK_INLINE_PREVIEW_TYPES = {".txt": "text/plain"}
        assert is_previewable("notes.txt")
        assert storage_content_type("notes.txt") == "text/plain"
        assert not is_previewable("photo.png")

    def test_the_opaque_type_is_a_setting(self, settings):
        settings.TOPOBANK_OPAQUE_CONTENT_TYPE = "application/x-custom"
        assert storage_content_type("spec.pdf") == "application/x-custom"
        assert storage_content_type("photo.png") == "image/png"


@pytest.mark.parametrize(
    "num_bytes, text",
    [
        (0, "0 B"),
        (10, "10 B"),
        (1023, "1023 B"),
        (1024, "1 KiB"),
        (1536, "1.5 KiB"),
        (100 * 1024**2, "100 MiB"),
        (5 * 1024**3, "5 GiB"),
        (3 * 1024**4, "3 TiB"),
    ],
)
def test_format_bytes_binary(num_bytes, text):
    assert format_bytes_binary(num_bytes) == text
