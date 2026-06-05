"""Tests for topobank.analysis.exceptions."""

from topobank.analysis.exceptions import SubjectNotReadyException


def test_subject_not_ready_exception_message():
    exc = SubjectNotReadyException("my-subject")
    assert isinstance(exc, Exception)
    message = str(exc)
    assert "my-subject" in message
    assert "not in SUCCESS state" in message


def test_subject_not_ready_exception_is_raisable():
    import pytest

    with pytest.raises(SubjectNotReadyException):
        raise SubjectNotReadyException(42)
