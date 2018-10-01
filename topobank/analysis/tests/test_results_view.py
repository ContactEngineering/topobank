"""
Test for results view.
"""

import pytest
import datetime
import pickle

from django.urls import reverse

from ..models import Analysis, AnalysisFunction
from topobank.manager.tests.utils import two_topos
from topobank.manager.models import Topography
from topobank.manager.tests.utils import export_reponse_as_html

@pytest.mark.django_db
def test_analysis_times(client, two_topos):

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    topo = Topography.objects.first()
    af = AnalysisFunction.objects.first()

    analysis = Analysis.objects.create(
        topography=topo,
        function=af,
        task_state=Analysis.SUCCESS,
        args=pickle.dumps(()),
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13, 1, 1), # duration: 1 hour, 1 minute, 1 sec
    )
    analysis.save()

    response = client.post(reverse("analysis:list"),
                           data={
                               'topographies': [topo.id],
                               'functions': [af.id],
                           }, follow=True)

    assert response.status_code == 200

    export_reponse_as_html(response)

    assert b"State: success" in response.content
    assert b"Started: 2018-01-01 12:00:00" in response.content
    assert b"Ended: 2018-01-01 13:01:01" in response.content
    assert b"Duration: 1:01:01" in response.content



