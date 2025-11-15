import pytest
from django.utils.duration import duration_string

from topobank.analysis.serializers import ResultSerializer
from topobank.manager.models import Tag
from topobank.testing.factories import AnalysisFactory
from topobank.testing.utils import ASSERT_EQUAL_IGNORE_VALUE, assert_dict_equal


@pytest.mark.django_db
def test_serializer_subject_topography(api_rf, one_line_scan, test_analysis_function):
    topo = one_line_scan
    request = api_rf.get("/")
    analysis = AnalysisFactory(
        subject_topography=topo, user=topo.created_by, function=test_analysis_function
    )
    data = ResultSerializer(analysis, context={"request": request}).data
    assert_dict_equal(
        data,
        {
            "id": analysis.id,
            "api": ASSERT_EQUAL_IGNORE_VALUE,
            "url": f"http://testserver/analysis/api/result/{analysis.id}/",
            "function": f"http://testserver/analysis/api/workflow/{test_analysis_function.name}/",
            "subject": {
                "id": analysis.subject_dispatch.id,
                "tag": None,
                "topography": f"http://testserver/manager/api/topography/{topo.id}/",
                "surface": None,
            },
            "dependencies_url": ASSERT_EQUAL_IGNORE_VALUE,
            "kwargs": {"a": 1, "b": "foo"},
            "task_progress": 0.0,
            "task_state": "su",
            "task_messages": ASSERT_EQUAL_IGNORE_VALUE,
            "task_memory": None,
            "creation_time": analysis.created_at.astimezone().isoformat(),
            "task_submission_time": analysis.task_submission_time.astimezone().isoformat(),
            "task_start_time": analysis.task_start_time.astimezone().isoformat(),
            "task_end_time": analysis.task_end_time.astimezone().isoformat(),
            "dois": [],
            "configuration": None,
            "task_duration": duration_string(analysis.task_duration),
            "task_error": None,
            "task_traceback": None,
            "folder": f"http://testserver/files/folder/{analysis.folder.id}/",
            "name": None,
            "task_id": ASSERT_EQUAL_IGNORE_VALUE,
            "launcher_task_id": ASSERT_EQUAL_IGNORE_VALUE,
            "creator": ASSERT_EQUAL_IGNORE_VALUE
        },
    )


@pytest.mark.django_db
def test_serializer_subject_tag(api_rf, one_line_scan, test_analysis_function):
    topo = one_line_scan
    topo.tags = ["my-tag"]
    topo.save()
    assert Tag.objects.count() == 1
    tag = Tag.objects.all().first()
    tag.authorize_user(topo.created_by)
    request = api_rf.get("/")
    analysis = AnalysisFactory(
        subject_tag=tag, user=topo.created_by, function=test_analysis_function
    )
    data = ResultSerializer(analysis, context={"request": request}).data
    assert_dict_equal(
        data,
        {
            "id": analysis.id,
            "api": ASSERT_EQUAL_IGNORE_VALUE,
            "url": f"http://testserver/analysis/api/result/{analysis.id}/",
            "function": f"http://testserver/analysis/api/workflow/{test_analysis_function.name}/",
            "subject": {
                "id": analysis.subject_dispatch.id,
                "tag": f"http://testserver/manager/api/tag/{tag.name}/",
                "topography": None,
                "surface": None,
            },
            "dependencies_url": ASSERT_EQUAL_IGNORE_VALUE,
            "kwargs": {"a": 1, "b": "foo"},
            "task_progress": 0.0,
            "task_state": "su",
            "task_messages": ASSERT_EQUAL_IGNORE_VALUE,
            "task_memory": None,
            "creation_time": analysis.created_at.astimezone().isoformat(),
            "task_submission_time": analysis.task_submission_time.astimezone().isoformat(),
            "task_start_time": analysis.task_start_time.astimezone().isoformat(),
            "task_end_time": analysis.task_end_time.astimezone().isoformat(),
            "dois": [],
            "configuration": None,
            "task_duration": duration_string(analysis.task_duration),
            "task_error": None,
            "task_traceback": None,
            "folder": f"http://testserver/files/folder/{analysis.folder.id}/",
            "name": None,
            "task_id": ASSERT_EQUAL_IGNORE_VALUE,
            "launcher_task_id": ASSERT_EQUAL_IGNORE_VALUE,
            "creator": ASSERT_EQUAL_IGNORE_VALUE
        },
    )
