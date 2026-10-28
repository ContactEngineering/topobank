"""Tests for the managers every task model has (see `TaskStateModel`)."""

import pytest

from topobank.manager.models import Topography
from topobank.taskapp.custodian import task_state_models
from topobank.testing.factories import Topography1DFactory


def test_there_are_task_models():
    assert Topography in task_state_models()


@pytest.mark.parametrize("model", task_state_models(), ids=lambda m: m.__name__)
def test_objects_stays_the_default_manager(model):
    assert model._meta.default_manager.name == "objects"


@pytest.mark.django_db
def test_all_objects_holds_the_rows_objects_hides():
    topo = Topography1DFactory()
    topo.lazy_delete()

    assert not Topography.objects.filter(pk=topo.pk).exists()
    assert Topography.all_objects.filter(pk=topo.pk).exists()
