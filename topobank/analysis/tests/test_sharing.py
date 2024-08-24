import pytest

from topobank.analysis.controller import AnalysisController
from topobank.manager.models import Surface, Topography
from topobank.manager.tests.utils import TagFactory


@pytest.mark.django_db
def test_topography_analysis(mocker, two_users, test_analysis_function):
    user1, user2 = two_users

    surface1, surface2, surface3 = Surface.objects.all()
    topography1, topography2, topography3 = Topography.objects.all()

    controller = AnalysisController(
        user1, subjects=[topography1], function=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 1  # analysis of topography

    results = controller.get()

    for r in results:
        r.task_state = "su"

    # Controller should not trigger analyses again
    controller.trigger_missing_analyses()
    assert [r.task_state for r in controller.get()] == ["su"]

    controller = AnalysisController(
        user2, subjects=[topography1], function=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 0  # user2 has no access to surface1

    surface1.share(user2)

    controller = AnalysisController(
        user2, subjects=[topography1], function=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 1  # user2 now has access to topography1

    # Controller triggered analyses because they are tied to a specific user
    assert [r.task_state for r in controller.get()] == ["pe"]


@pytest.mark.django_db
def test_surface_analysis(mocker, two_users, test_analysis_function):
    user1, user2 = two_users

    surface1, surface2, surface3 = Surface.objects.all()

    controller = AnalysisController(
        user1, subjects=[surface1], function=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 2  # analysis of topography and surface

    results = controller.get()

    for r in results:
        r.task_state = "su"

    # Controller should not trigger analyses again
    controller.trigger_missing_analyses()
    assert [r.task_state for r in controller.get()] == ["su", "su"]

    controller = AnalysisController(
        user2, subjects=[surface1], function=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 0  # user2 has no access to surface1

    surface1.share(user2)

    controller = AnalysisController(
        user2, subjects=[surface1], function=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 2  # user2 now has access to surface1

    # Controller triggered analyses because they are tied to a specific user
    assert [r.task_state for r in controller.get()] == ["pe", "pe"]


@pytest.mark.django_db
def test_tag_analysis(mocker, two_users, test_analysis_function):
    user1, user2 = two_users

    surface1, surface2, surface3 = Surface.objects.all()

    tag = TagFactory(name="test_tag")
    surface2.tags.add(tag)
    surface3.tags.add(tag)

    controller = AnalysisController(
        user2, subjects=[tag], function=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 1  # analysis of tag

    results = controller.get()

    for r in results:
        r.task_state = "su"

    # Controller should not trigger analyses again
    controller.trigger_missing_analyses()
    assert [r.task_state for r in controller.get()] == ["su"]

    controller = AnalysisController(
        user1, subjects=[tag], function=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 1  # user1 has no access to surface1

    # Controller triggered analyses because they are tied to a specific user
    assert [r.task_state for r in controller.get()] == ["pe"]

    for r in results:
        r.task_state = "su"

    surface2.share(user1)
    surface3.share(user2)

    controller = AnalysisController(
        user1, subjects=[tag], function=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 1  # user2 now has access to surface1

    # Controller triggered analyses because they are tied to a specific user
    assert [r.task_state for r in controller.get()] == ["pe"]
