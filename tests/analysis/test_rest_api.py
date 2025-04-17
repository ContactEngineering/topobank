import pytest
from rest_framework.reverse import reverse

from topobank.analysis.models import Analysis, AnalysisFunction, WorkflowTemplate
from topobank.manager.models import Tag
from topobank.manager.utils import dict_to_base64, subjects_to_base64
from topobank.testing.factories import (
    AnalysisFactory,
    SurfaceFactory,
    Topography1DFactory,
    UserFactory,
    WorkflowTemplateFactory,
)
from topobank.testing.utils import ASSERT_EQUAL_IGNORE_VALUE, assert_dict_equal


@pytest.mark.django_db
def test_statistics(api_client, handle_usage_statistics):
    user = UserFactory()
    surf1 = SurfaceFactory(creator=user)
    surf2 = SurfaceFactory(creator=user)
    topo1a = Topography1DFactory(surface=surf1)
    topo1b = Topography1DFactory(surface=surf1)
    topo2a = Topography1DFactory(surface=surf2)

    func = AnalysisFunction.objects.get(name="topobank.testing.test")

    #
    # Generate analyses for topographies with differing arguments
    #
    kwargs_1a = dict(a=1, b="abc")
    kwargs_1b = dict(a=1, b="def")  # differing from kwargs_1a!
    AnalysisFactory(subject_topography=topo1a, function=func, kwargs=kwargs_1a)
    AnalysisFactory(subject_topography=topo1b, function=func, kwargs=kwargs_1b)
    AnalysisFactory(subject_topography=topo2a, function=func)  # default arguments

    #
    # Generate analyses for surfaces with differing arguments
    #
    kwargs_1 = dict(a=2, b="abc")
    kwargs_2 = dict(a=2, b="def")  # differing from kwargs_1a!
    AnalysisFactory(subject_surface=surf1, function=func, kwargs=kwargs_1)
    AnalysisFactory(subject_surface=surf2, function=func, kwargs=kwargs_2)

    response = api_client.get(reverse("manager:statistics"))
    # assert response.data["nb_users"] == 1
    assert response.data["nb_surfaces"] == 2
    assert response.data["nb_topographies"] == 3

    response = api_client.get(reverse("analysis:statistics"))
    assert response.data["nb_analyses"] == 5


@pytest.mark.django_db
def test_query_with_wrong_kwargs(api_client, one_line_scan, test_analysis_function):
    user = one_line_scan.creator
    one_line_scan.grant_permission(user, "view")
    response = api_client.get(
        f"{reverse('analysis:result-list')}?topography={one_line_scan.id}"
        f"&workflow={test_analysis_function.name}"
    )
    assert response.status_code == 200, response.reason_phrase
    assert len(response.data["analyses"]) == 0

    # Login
    api_client.force_login(user)
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1

    # Get a different set of parameters
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?topography={one_line_scan.id}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(dict(a=2, b='abc'))}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 2

    # Try passing integer parameters as strings
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(dict(a='2', b='abc'))}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 2

    # Try a parameter set that does not validate
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(dict(a=2, c=7))}"
    )
    assert response.status_code == 400
    assert Analysis.objects.count() == 2


@pytest.mark.django_db
def test_function_info(api_client, user_alice, handle_usage_statistics):
    api_client.force_login(user_alice)

    response = api_client.get(
        f"{reverse('analysis:workflow-list')}?subject_type=topography"
    )

    assert response.status_code == 200
    assert len(response.data) > 0

    name = "topobank.testing.test"
    response = api_client.get(
        reverse("analysis:workflow-detail", kwargs=dict(name=name))
    )

    assert response.status_code == 200
    assert_dict_equal(
        response.data,
        {
            "id": ASSERT_EQUAL_IGNORE_VALUE,
            "url": f"http://testserver/analysis/api/workflow/{name}/",
            "name": name,
            "display_name": "Test implementation",
            "visualization_type": "series",
            "kwargs_schema": {
                "a": {"default": 1, "title": "A", "type": "integer"},
                "b": {"default": "foo", "title": "B", "type": "string"},
            },
        },
    )


@pytest.mark.django_db
def test_query_tag_analysis(
    api_client,
    one_line_scan,
    test_analysis_function,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    user = one_line_scan.creator
    # Add tag to surface
    one_line_scan.surface.tags.add("my-tag")
    tag = Tag.objects.get(name="my-tag")

    assert Analysis.objects.count() == 0

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}?subjects="
            f"{subjects_to_base64([tag])}&workflow={test_analysis_function.name}"
        )
    assert len(callbacks) == 1
    assert Analysis.objects.count() == 1
    # Tag analyses always succeed...
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    analysis_id = response.data["analyses"][0]["id"]
    # ...but they may have run on no data
    folder_url = response.data["analyses"][0]["folder"]
    response = api_client.get(folder_url)
    assert response.status_code == 200
    assert len(response.data) == 1
    assert "result.json" in response.data
    # Check that result file actually has no data
    # response = api_client.get(response.data["result.json"]["file"])
    # assert response.status_code == 200
    # assert len(response.data["analyses"]) == 1
    # file = response.data["result.json"]["file"][23:]
    analysis = Analysis.objects.get(id=analysis_id)
    assert len(analysis.result["surfaces"]) == 0

    # Login
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?subjects={subjects_to_base64([tag])}"
            f"&workflow={test_analysis_function.name}"
        )
    assert len(callbacks) == 1
    assert Analysis.objects.count() == 2
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    analysis_id = response.data["analyses"][0]["id"]
    unique_kwargs = response.data["unique_kwargs"]

    # ...but they may have run on no data
    folder_url = response.data["analyses"][0]["folder"]
    response = api_client.get(folder_url)
    assert response.status_code == 200
    assert len(response.data) == 1
    assert "result.json" in response.data
    # Check that result file actually has data now
    # response = api_client.get(response.data["result.json"]["file"])
    # assert response.status_code == 200
    # assert len(response.data["analyses"]) == 1
    # file = response.data["result.json"]["file"][23:]
    # data = json.load(default_storage.open(file))
    # assert len(data["surfaces"] == 1)
    analysis = Analysis.objects.get(id=analysis_id)
    assert len(analysis.result["surfaces"]) == 1

    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([tag])}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(unique_kwargs)}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert response.data["analyses"][0]["id"] == analysis_id  # Should yield the same


@pytest.mark.django_db
def test_query_with_unique_kwargs(
    api_client, one_line_scan, test_analysis_function, handle_usage_statistics
):
    user = one_line_scan.creator
    one_line_scan.grant_permission(user, "view")
    response = api_client.get(
        f"{reverse('analysis:result-list')}?subjects="
        f"{subjects_to_base64([one_line_scan])}&workflow={test_analysis_function.name}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 0

    # Login
    api_client.force_login(user)
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 1

    analysis_id = response.data["analyses"][0]["id"]
    unique_kwargs = response.data["unique_kwargs"]

    # Query again, but now with unique kwargs
    response = api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([one_line_scan])}"
        f"&workflow={test_analysis_function.name}"
        f"&kwargs={dict_to_base64(unique_kwargs)}"
    )
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 1
    assert response.data["analyses"][0]["id"] == analysis_id  # Should yield the same


@pytest.mark.django_db
def test_query_with_error(
    api_client,
    one_line_scan,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    user = one_line_scan.creator
    function = AnalysisFunction.objects.get(name="topobank.testing.test_error")

    # Login
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?topography={one_line_scan.id}"
            f"&workflow={function.name}"
        )
    assert len(callbacks) == 1
    assert response.status_code == 200
    assert response.data["analyses"][0]["task_state"] == "pe"
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 1

    # Second request is required to retrieve error (first is always pending)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?topography={one_line_scan.id}"
            f"&workflow={function.name}"
        )
    assert len(callbacks) == 0  # This just return the error
    assert response.status_code == 200
    assert response.data["analyses"][0]["task_state"] == "fa"
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 1

    assert response.data["analyses"][0]["error"] == "An error occurred!"
    assert "return runner.eval" in response.data["analyses"][0]["task_traceback"]


@pytest.mark.django_db
def test_query_with_error_in_dependency(
    api_client,
    one_line_scan,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    user = one_line_scan.creator
    function = AnalysisFunction.objects.get(
        name="topobank.testing.test_error_in_dependency"
    )

    # Login
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?topography={one_line_scan.id}"
            f"&workflow={function.name}"
        )
    assert len(callbacks) == 1
    assert response.status_code == 200
    assert response.data["analyses"][0]["task_state"] == "pe"
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 2

    # Second request is required to retrieve error (first is always pending)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?topography={one_line_scan.id}"
            f"&workflow={function.name}"
        )
    assert len(callbacks) == 0  # This just return the error
    assert response.status_code == 200
    assert response.data["analyses"][0]["task_state"] == "fa"
    assert len(response.data["analyses"]) == 1
    assert Analysis.objects.count() == 2

    assert response.data["analyses"][0]["error"] == "An error occurred!"
    # We currently do not get a traceback from dependencies
    assert response.data["analyses"][0]["task_traceback"] is None


@pytest.mark.django_db
def test_save_tag_analysis(
    api_client,
    one_line_scan,
    test_analysis_function,
    django_capture_on_commit_callbacks,
    handle_usage_statistics,
):
    user = one_line_scan.creator
    # Add tag to surface
    one_line_scan.surface.tags.add("my-tag")
    tag = Tag.objects.get(name="my-tag")

    assert Analysis.objects.count() == 0

    # Login
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?subjects={subjects_to_base64([tag])}"
            f"&workflow={test_analysis_function.name}"
        )
    assert len(callbacks) == 1
    assert Analysis.objects.count() == 1
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1
    set_name_url = response.data["analyses"][0]["api"]["set_name"]

    # Check that named result does not return unnamed results
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(reverse("analysis:named-result-list"))
    assert len(callbacks) == 0
    assert Analysis.objects.count() == 1  # We still have one (the saved analysis)
    assert response.status_code == 200
    assert len(response.data) == 0

    # Set analysis name and description
    response = api_client.post(set_name_url, {"name": "my-name", "description": "my-description"})
    assert response.status_code == 200
    assert Analysis.objects.count() == 1  # This does not make a copy
    assert Analysis.objects.get(name="my-name").description == "my-description"

    # Check that query the analysis again triggers a new one
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:result-list')}"
            f"?subjects={subjects_to_base64([tag])}"
            f"&workflow={test_analysis_function.name}"
        )
    assert len(callbacks) == 1
    assert Analysis.objects.count() == 2  # We now have two
    assert response.status_code == 200
    assert len(response.data["analyses"]) == 1

    # Delete tag
    tag.delete()
    assert Analysis.objects.count() == 1

    # Check that we can query saved analysis
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = api_client.get(
            f"{reverse('analysis:named-result-list')}" f"?name=my-name"
        )
    assert len(callbacks) == 0
    assert Analysis.objects.count() == 1  # We still have one (the saved analysis)
    assert response.status_code == 200
    assert len(response.data) == 1


@pytest.mark.django_db
def test_query_pending(
    api_client,
    one_line_scan,
    test_analysis_function,
    handle_usage_statistics,
):
    user = one_line_scan.creator
    # Add tag to surface
    one_line_scan.surface.tags.add("my-tag")
    tag = Tag.objects.get(name="my-tag")

    assert Analysis.objects.count() == 0

    # Login
    api_client.force_login(user)
    api_client.get(
        f"{reverse('analysis:result-list')}"
        f"?subjects={subjects_to_base64([tag])}"
        f"&workflow={test_analysis_function.name}"
    )
    response = api_client.get(reverse("analysis:pending"))
    assert len(response.data) == 1
    assert response.data[0]["task_state"] == "pe"


@pytest.mark.django_db
def test_query_with_not_implemented_subject(api_client, one_line_scan, test_analysis_function):
    user = one_line_scan.creator
    one_line_scan.grant_permission(user, "view")
    surface = one_line_scan.surface
    response = api_client.get(
        f"{reverse('analysis:result-list')}?surface={surface.id}"
        f"&workflow=topobank.testing.topography_only_test"
    )
    assert response.status_code == 200
    assert response.data['analyses'] == []


@pytest.mark.django_db
def test_workflow_template_api(
        api_client,
        one_line_scan,
        test_analysis_function):

    user = one_line_scan.creator
    one_line_scan.grant_permission(user, "view")

    kwargs = dict(a=1, b="foo")
    url = f"http://testserver/analysis/api/workflow/{test_analysis_function.name}/"

    expected_template = {
        "name": "my-template",
        "kwargs": kwargs,
        "implementation": url,
    }

    api_client.force_authenticate(user)

    response = api_client.post(
        reverse("analysis:workflow-template-list"),
        data=expected_template,
        format="json"
    )

    assert response.status_code == 201
    assert response.data["name"] == "my-template"

    template = WorkflowTemplate.objects.get(name=expected_template['name'])
    assert response.data["kwargs"] == kwargs, \
        f"Expected same name, got {template.name} != {expected_template['name']}"
    assert template.name == expected_template['name'], \
        f"Expected same name, got {template.name} != {expected_template['name']}"
    assert template.kwargs == expected_template['kwargs'], \
        f"Expected same kwargs, got {template.kwargs} != {expected_template['kwargs']}"
    assert template.implementation == test_analysis_function, \
        f"Expected same analysis function, got {template.implementation} \
            != {test_analysis_function.name}"

    # test retrieving the template
    response = api_client.get(
        reverse("analysis:workflow-template-detail", kwargs=dict(pk=template.id))
    )

    assert response.status_code == 200
    assert response.data["name"] == expected_template['name']
    assert response.data["kwargs"] == expected_template['kwargs']

    # test update template
    expected_template["kwargs"]
    updated_kwargs = expected_template["kwargs"]
    updated_kwargs["a"] = 2

    response = api_client.patch(
        reverse("analysis:workflow-template-detail", kwargs={"pk": template.id}),
        {'kwargs': updated_kwargs},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["name"] == expected_template['name']
    assert response.data["kwargs"] == updated_kwargs

    # template list
    template2 = WorkflowTemplateFactory(
        name="my-template-2",
        kwargs=dict(a=2, b="foo2"),
        implementation=test_analysis_function,
        creator=user,
    )

    response = api_client.get(reverse("analysis:workflow-template-list"))
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert len(response.data) == 2, f"Expected 2 template, got {len(response.data)}"

    # test deleting the template
    api_client.force_authenticate(user)
    response = api_client.delete(
        reverse("analysis:workflow-template-detail", kwargs=dict(pk=template2.id))
    )
    templates = WorkflowTemplate.objects.all()

    assert response.status_code == 204
    assert len(templates) == 1, f"Expected 1 template, got {len(templates)}"


@pytest.mark.django_db
def test_workflow_template_query(api_client, one_line_scan):
    user = one_line_scan.creator

    # Create a new workflow template
    func = AnalysisFunction.objects.get(name="topobank.testing.test")
    func2 = AnalysisFunction.objects.get(name="topobank.testing.test2")

    # create different workflow template with from analysis
    WorkflowTemplateFactory(
        name="my-template-1",
        kwargs=dict(a=2, b="foo2"),
        implementation=func,
        creator=user,
    )
    WorkflowTemplateFactory(
        name="my-template-2",
        kwargs=dict(a=2, b="foo2"),
        implementation=func2,
        creator=user,
    )
    url = (
        f'{reverse("analysis:workflow-template-list")}'
        f'?implementation={func.name}'
    )

    api_client.force_authenticate(user)
    response = api_client.get(url)

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert len(response.data) == 1, f"Expected 1 template, got {len(response.data)}"
    url = f"http://testserver/analysis/api/workflow/{func.name}/"
    assert response.data[0]['implementation'] == url, \
        f"Expected matching AnalysisFunction, got {response.data['implementation']}"
