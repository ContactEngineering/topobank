"""
Test management commands related to users.
"""
import pytest

from django.core.management import call_command


@pytest.mark.django_db
def test_notify():
    # just a regression test so far, can notify be called successfully?
    call_command("notify_users", "Hey there")
