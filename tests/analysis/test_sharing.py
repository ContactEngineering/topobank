import pytest

from topobank.analysis.v1.controller import AnalysisController
from topobank.manager.models import Topography
from topobank.testing.factories import TagFactory


@pytest.mark.django_db
def test_topography_analysis(two_users, test_analysis_function):
    (user1, user2), (surface1, surface2, surface3) = two_users

    topography1, topography2, topography3 = Topography.objects.all()

    controller = AnalysisController(
        user1, subjects=[topography1], workflow=test_analysis_function
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
        user2, subjects=[topography1], workflow=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 0  # user2 has no access to surface1

    surface1.grant_permission(user2)

    controller = AnalysisController(
        user2, subjects=[topography1], workflow=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 1  # user2 now has access to topography1

    # Controller triggered analyses because they are tied to a specific user
    assert [r.task_state for r in controller.get()] == ["pe"]


@pytest.mark.django_db
def test_surface_analysis(two_users, test_analysis_function):
    (user1, user2), (surface1, surface2, surface3) = two_users

    controller = AnalysisController(
        user1, subjects=[surface1], workflow=test_analysis_function
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
        user2, subjects=[surface1], workflow=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 0  # user2 has no access to surface1

    surface1.grant_permission(user2)

    controller = AnalysisController(
        user2, subjects=[surface1], workflow=test_analysis_function
    )
    controller.trigger_missing_analyses()
    assert len(controller) == 2  # user2 now has access to surface1

    # Controller triggered analyses because they are tied to a specific user
    assert [r.task_state for r in controller.get()] == ["pe", "pe"]


@pytest.mark.django_db
def test_tag_analysis(two_users, django_capture_on_commit_callbacks, test_analysis_function):
    (user1, user2), (surface1, surface2, surface3) = two_users

    tag = TagFactory(name="test_tag")
    surface2.tags.add(tag)
    surface3.tags.add(tag)

    # Trigger analysis for the first time
    controller = AnalysisController(
        user2, subjects=[tag], workflow=test_analysis_function
    )
    assert len(controller) == 0  # no analysis yet
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        controller.trigger_missing_analyses()
    assert len(callbacks) == 1  # triggered analysis task
    assert len(controller) == 1  # analysis of tag

    r, = controller.get()
    assert r.task_state == "su"
    assert r.result["surfaces"] == [surface2.name, surface3.name]

    # Trigger for a second time; controller should not trigger analyses again
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        controller.trigger_missing_analyses()
    assert len(callbacks) == 0  # no analysis was triggered
    assert [r.task_state for r in controller.get()] == ["su"]

    # Switch user
    if False:
        # FIXME!!! We need to implement invalidation of tag analyses when tags change
        # See: https://github.com/ContactEngineering/topobank/issues/1125
        controller = AnalysisController(
            user1, subjects=[tag], workflow=test_analysis_function
        )
        assert len(controller) == 0  # there are no tag analyses for this user
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            controller.trigger_missing_analyses()
        # user1 has no access to any surfaces inside this tag, but analysis is triggered nevertheless
        assert len(callbacks) == 1
        r, = controller.get()
        assert r.task_state == "su"
        assert len(r.result["surfaces"]) == 0  # user1 has no access to any surface inside this tag

    surface2.grant_permission(user1)

    # User1 again, but now (one of the) surfaces is shared
    controller = AnalysisController(
        user1, subjects=[tag], workflow=test_analysis_function
    )
    assert len(controller) == 0  # no analysis yet
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        controller.trigger_missing_analyses()
    assert len(callbacks) == 1  # Controller triggered new analyses because surface2 was just shared
    r, = controller.get()
    assert r.task_state == "su"
    assert r.result["surfaces"] == [surface2.name]  # user1 has access to only surface2
