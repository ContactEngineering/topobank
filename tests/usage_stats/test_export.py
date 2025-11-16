"""Tests for output file for usage statistics."""
import pandas as pd
import pytest
from django.core.management import call_command
from django.shortcuts import reverse

from topobank.taskapp.tasks import save_landing_page_statistics
from topobank.testing.factories import SurfaceFactory, Topography2DFactory, UserFactory


@pytest.mark.django_db
def test_export_with_empty_statistics():
    call_command('export_usage_statistics')


@pytest.mark.skip('Fix usage statistics')
@pytest.mark.django_db
def test_sheets(api_client, handle_usage_statistics):

    user = UserFactory()
    surface = SurfaceFactory(created_by=user)
    Topography2DFactory(surface=surface)
    Topography2DFactory(surface=surface)

    save_landing_page_statistics()  # save current state for users, surfaces, ..

    api_client.force_login(user)  # not counted as login here

    api_client.get(reverse('manager:surface-api-detail', kwargs=dict(pk=surface.pk)))
    # Now there is one surface view

    # tried to use freezegun.freeze_time here,
    # but openpyxl had problems with FakeDate class
    call_command('export_usage_statistics')

    df = pd.read_excel("usage_statistics.xlsx", sheet_name="summary", engine='openpyxl')
    assert df.columns[0] == 'month'
    assert df.iloc[0, 1:].tolist() == [0, 1, 0, 0, 1, 1, 2, 0]
    # excluding month here, because it varies and freezegun does not work
