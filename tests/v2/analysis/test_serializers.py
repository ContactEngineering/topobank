import pytest
from rest_framework.exceptions import ValidationError

from topobank.analysis.models import WorkflowResult
from topobank.analysis.serializers import WorkflowListSerializer
from topobank.analysis.v2.serializers import (
    ConfigurationV2Serializer,
    DependencyV2ListSerializer,
    ResultV2CreateSerializer,
    ResultV2DetailSerializer,
    ResultV2ListSerializer,
)
from topobank.manager.models import Tag
from topobank.taskapp.models import Configuration, Dependency, Version
from topobank.testing.factories import SurfaceFactory, TagFactory, Topography1DFactory


@pytest.mark.django_db
def test_configuration_v2_serializer(api_rf):
    """Test ConfigurationV2Serializer serializes versions correctly"""
    request = api_rf.get("/")

    # Create a configuration with versions
    config = Configuration.objects.create()

    # Create dependencies and versions
    dep1 = Dependency.objects.create(import_name="numpy")
    dep2 = Dependency.objects.create(import_name="scipy")

    version1 = Version.objects.create(dependency=dep1, major=1, minor=24, micro=3)
    version2 = Version.objects.create(dependency=dep2, major=1, minor=10, micro=1)

    config.versions.add(version1, version2)

    # Serialize
    serializer = ConfigurationV2Serializer(config, context={"request": request})
    data = serializer.data

    # Verify the structure
    assert "valid_since" in data
    assert "versions" in data
    assert isinstance(data["versions"], dict)
    assert data["versions"]["numpy"] == "1.24.3"
    assert data["versions"]["scipy"] == "1.10.1"


@pytest.mark.django_db
def test_configuration_v2_serializer_empty_versions(api_rf):
    """Test ConfigurationV2Serializer with no versions"""
    request = api_rf.get("/")
    config = Configuration.objects.create()

    serializer = ConfigurationV2Serializer(config, context={"request": request})
    data = serializer.data

    assert data["versions"] == {}


@pytest.mark.django_db
def test_workflow_v2_serializer(api_rf, test_analysis_function):
    """Test WorkflowListSerializer serializes workflow correctly"""
    request = api_rf.get("/")
    workflow = test_analysis_function

    serializer = WorkflowListSerializer(workflow, context={"request": request})
    data = serializer.data

    assert data["name"] == workflow.name
    assert data["display_name"] == workflow.display_name
    assert "url" in data
    assert data["url"] == f"http://testserver/analysis/api/workflow/{workflow.name}/"


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_function_by_id(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer validates function by ID"""
    request = api_rf.get("/")
    request.user = user_alice

    serializer = ResultV2CreateSerializer(context={"request": request})
    workflow = serializer.validate_function(test_analysis_function.id)

    assert workflow == test_analysis_function


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_function_by_name(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer validates function by name"""
    request = api_rf.get("/")
    request.user = user_alice

    serializer = ResultV2CreateSerializer(context={"request": request})
    workflow = serializer.validate_function(test_analysis_function.name)

    assert workflow == test_analysis_function


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_function_invalid(api_rf, user_alice):
    """Test ResultV2CreateSerializer rejects invalid function"""
    request = api_rf.get("/")
    request.user = user_alice

    serializer = ResultV2CreateSerializer(context={"request": request})

    with pytest.raises(ValidationError) as exc_info:
        serializer.validate_function("nonexistent-workflow")

    assert "function" in str(exc_info.value)


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_subject_type_valid(api_rf, user_alice):
    """Test ResultV2CreateSerializer validates subject_type correctly"""
    request = api_rf.get("/")
    request.user = user_alice
    serializer = ResultV2CreateSerializer(context={"request": request})

    # Test lowercase normalization
    assert serializer.validate_subject_type("surface") == "surface"
    assert serializer.validate_subject_type("Surface") == "surface"
    assert serializer.validate_subject_type("TOPOGRAPHY") == "topography"
    assert serializer.validate_subject_type("Tag") == "tag"


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_subject_type_invalid(api_rf, user_alice):
    """Test ResultV2CreateSerializer rejects invalid subject_type"""
    request = api_rf.get("/")
    request.user = user_alice
    serializer = ResultV2CreateSerializer(context={"request": request})

    with pytest.raises(ValidationError) as exc_info:
        serializer.validate_subject_type("invalid_type")

    assert "subject_type" in str(exc_info.value)


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_surface_subject(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer validates surface subject"""
    request = api_rf.get("/")
    request.user = user_alice

    surface = SurfaceFactory(created_by=user_alice)

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": surface.id,
        "subject_type": "surface",
    }

    validated_data = serializer.validate(data)
    assert validated_data["subject"] == surface


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_surface_subject_no_permission(
    api_rf, user_alice, user_bob, test_analysis_function
):
    """Test ResultV2CreateSerializer rejects surface without permission"""
    request = api_rf.get("/")
    request.user = user_alice

    # Surface owned by user_bob, not shared with user_alice
    surface = SurfaceFactory(created_by=user_bob)

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": surface.id,
        "subject_type": "surface",
    }

    with pytest.raises(ValidationError) as exc_info:
        serializer.validate(data)

    assert "subject" in str(exc_info.value)


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_surface_subject_string_invalid(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer rejects non-integer surface ID"""
    request = api_rf.get("/")
    request.user = user_alice

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": "not-an-integer",
        "subject_type": "surface",
    }

    with pytest.raises(ValidationError) as exc_info:
        serializer.validate(data)

    assert "subject" in str(exc_info.value)
    assert "integer" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_topography_subject(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer validates topography subject"""
    request = api_rf.get("/")
    request.user = user_alice

    surface = SurfaceFactory(created_by=user_alice)
    topo = Topography1DFactory(surface=surface)

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": topo.id,
        "subject_type": "topography",
    }

    validated_data = serializer.validate(data)
    assert validated_data["subject"] == topo


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_topography_subject_no_permission(
    api_rf, user_alice, user_bob, test_analysis_function
):
    """Test ResultV2CreateSerializer rejects topography without permission"""
    request = api_rf.get("/")
    request.user = user_alice

    surface = SurfaceFactory(created_by=user_bob)
    topo = Topography1DFactory(surface=surface)

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": topo.id,
        "subject_type": "topography",
    }

    with pytest.raises(ValidationError) as exc_info:
        serializer.validate(data)

    assert "subject" in str(exc_info.value)


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_tag_subject_by_id(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer validates tag subject by ID"""
    request = api_rf.get("/")
    request.user = user_alice

    _ = SurfaceFactory(created_by=user_alice, tags=["test-tag"])
    tag = Tag.objects.get(name="test-tag")
    tag.authorize_user(user_alice, "view")

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": tag.id,
        "subject_type": "tag",
    }

    validated_data = serializer.validate(data)
    assert validated_data["subject"] == tag


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_tag_subject_by_name(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer validates tag subject by name"""
    request = api_rf.get("/")
    request.user = user_alice

    _ = SurfaceFactory(created_by=user_alice, tags=["test-tag"])
    tag = Tag.objects.get(name="test-tag")
    tag.authorize_user(user_alice, "view")

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": "test-tag",
        "subject_type": "tag",
    }

    validated_data = serializer.validate(data)
    assert validated_data["subject"] == tag


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_tag_subject_no_permission(
    api_rf, user_alice, user_bob, test_analysis_function
):
    """Test ResultV2CreateSerializer rejects tag without permission"""
    request = api_rf.get("/")
    request.user = user_alice

    _ = SurfaceFactory(created_by=user_bob, tags=["test-tag"])
    tag = Tag.objects.get(name="test-tag")
    # Don't authorize user_alice

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": tag.id,
        "subject_type": "tag",
    }

    with pytest.raises(ValidationError) as exc_info:
        serializer.validate(data)

    assert "subject" in str(exc_info.value)


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_tag_subject_no_surfaces(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer rejects tag with no accessible surfaces"""
    request = api_rf.get("/")
    request.user = user_alice

    # Create a tag without any surfaces
    tag = TagFactory()
    tag.authorize_user(user_alice, "view")

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": tag.id,
        "subject_type": "tag",
    }

    with pytest.raises(ValidationError) as exc_info:
        serializer.validate(data)

    assert "subject" in str(exc_info.value)
    assert "no accessible surfaces" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_result_v2_create_serializer_validate_tag_subject_not_found(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer rejects nonexistent tag"""
    request = api_rf.get("/")
    request.user = user_alice

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": "nonexistent-tag",
        "subject_type": "tag",
    }

    with pytest.raises(ValidationError) as exc_info:
        serializer.validate(data)

    assert "subject" in str(exc_info.value)


@pytest.mark.django_db
def test_result_v2_create_serializer_create(api_rf, user_alice, test_analysis_function):
    """Test ResultV2CreateSerializer creates WorkflowResult correctly"""
    request = api_rf.get("/")
    request.user = user_alice

    surface = SurfaceFactory(created_by=user_alice)
    topo = Topography1DFactory(surface=surface)

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": topo.id,
        "subject_type": "topography",
        "kwargs": {"param1": "value1"},
    }

    validated_data = serializer.validate(data)
    validated_data["created_by"] = user_alice
    validated_data["updated_by"] = user_alice

    result = serializer.create(validated_data)

    assert isinstance(result, WorkflowResult)
    assert result.function == test_analysis_function
    assert result.subject_dispatch.topography == topo
    assert result.kwargs == {"param1": "value1"}
    assert result.task_state == WorkflowResult.NOTRUN
    assert result.created_by == user_alice
    assert result.updated_by == user_alice


@pytest.mark.django_db
def test_result_v2_create_serializer_create_with_surface(
    api_rf, user_alice, test_analysis_function
):
    """Test ResultV2CreateSerializer creates WorkflowResult with surface subject"""
    request = api_rf.get("/")
    request.user = user_alice

    surface = SurfaceFactory(created_by=user_alice)

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": surface.id,
        "subject_type": "surface",
    }

    validated_data = serializer.validate(data)
    validated_data["created_by"] = user_alice
    validated_data["updated_by"] = user_alice

    result = serializer.create(validated_data)

    assert result.subject_dispatch.surface == surface


@pytest.mark.django_db
def test_result_v2_create_serializer_create_with_tag(api_rf, user_alice, test_analysis_function):
    """Test ResultV2CreateSerializer creates WorkflowResult with tag subject"""
    request = api_rf.get("/")
    request.user = user_alice

    _ = SurfaceFactory(created_by=user_alice, tags=["test-tag"])
    tag = Tag.objects.get(name="test-tag")
    tag.authorize_user(user_alice, "view")

    serializer = ResultV2CreateSerializer(context={"request": request})
    data = {
        "function": test_analysis_function,
        "subject": tag.id,
        "subject_type": "tag",
    }

    validated_data = serializer.validate(data)
    validated_data["created_by"] = user_alice
    validated_data["updated_by"] = user_alice

    result = serializer.create(validated_data)

    assert result.subject_dispatch.tag == tag


@pytest.mark.django_db
def test_result_v2_list_serializer(api_rf, one_line_scan, test_analysis_function):
    """Test ResultV2ListSerializer serializes WorkflowResult correctly"""
    from topobank.testing.factories import AnalysisFactory

    request = api_rf.get("/")
    topo = one_line_scan
    request.user = topo.created_by

    analysis = AnalysisFactory(
        subject_topography=topo, user=topo.created_by, function=test_analysis_function
    )

    serializer = ResultV2ListSerializer(analysis, context={"request": request})
    data = serializer.data

    assert data["id"] == analysis.id
    assert "url" in data
    assert data["url"] == f"http://testserver/analysis/v2/results/{analysis.id}/"
    assert "function" in data
    assert data["function"]["name"] == test_analysis_function.name
    assert "subject" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert "task_state" in data
    assert "task_progress" in data
    assert "permissions" in data
    assert "created_by" in data
    assert "updated_by" in data


@pytest.mark.django_db
def test_result_v2_detail_serializer(api_rf, one_line_scan, test_analysis_function):
    """Test ResultV2DetailSerializer serializes WorkflowResult with full details"""
    from topobank.testing.factories import AnalysisFactory

    request = api_rf.get("/")
    topo = one_line_scan
    request.user = topo.created_by

    analysis = AnalysisFactory(
        subject_topography=topo, user=topo.created_by, function=test_analysis_function
    )

    serializer = ResultV2DetailSerializer(analysis, context={"request": request})
    data = serializer.data

    # Check all expected fields are present
    assert data["id"] == analysis.id
    assert "url" in data
    assert "function" in data
    assert "subject" in data
    assert "kwargs" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert "configuration" in data
    assert "folder" in data
    assert "created_by" in data
    assert "updated_by" in data
    assert "owned_by" in data
    assert "permissions" in data
    assert "metadata" in data

    # Task state fields
    assert "task_state" in data
    assert "task_progress" in data
    assert "task_messages" in data
    assert "task_memory" in data
    assert "task_error" in data
    assert "task_traceback" in data
    assert "task_submission_time" in data
    assert "task_start_time" in data
    assert "task_end_time" in data
    assert "task_duration" in data
    assert "task_id" in data
    assert "launcher_task_id" in data

    # Dependencies
    assert "dependencies" in data
    assert isinstance(data["dependencies"], dict)
    assert "count" in data["dependencies"]
    assert "url" in data["dependencies"]


@pytest.mark.django_db
def test_result_v2_detail_serializer_name_description_writable(
    api_rf, one_line_scan, test_analysis_function
):
    """Test ResultV2DetailSerializer allows updating name and description"""
    from topobank.testing.factories import AnalysisFactory

    request = api_rf.get("/")
    topo = one_line_scan

    analysis = AnalysisFactory(
        subject_topography=topo, user=topo.created_by, function=test_analysis_function
    )

    serializer = ResultV2DetailSerializer(
        analysis,
        data={"name": "New Name", "description": "New Description"},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid()
    updated_analysis = serializer.save()

    assert updated_analysis.name == "New Name"
    assert updated_analysis.description == "New Description"


@pytest.mark.django_db
def test_dependency_v2_list_serializer_empty(api_rf):
    """Test DependencyV2ListSerializer with empty dependencies"""
    request = api_rf.get("/")
    serializer = DependencyV2ListSerializer(context={"request": request})

    result = serializer.to_representation({})
    assert result == []


@pytest.mark.django_db
def test_dependency_v2_list_serializer_with_dependencies(
    api_rf, one_line_scan, test_analysis_function
):
    """Test DependencyV2ListSerializer serializes dependencies correctly"""
    from topobank.testing.factories import AnalysisFactory

    request = api_rf.get("/")
    topo = one_line_scan

    # Create a workflow result
    analysis1 = AnalysisFactory(
        subject_topography=topo, user=topo.created_by, function=test_analysis_function
    )
    analysis2 = AnalysisFactory(
        subject_topography=topo, user=topo.created_by, function=test_analysis_function
    )

    # Create dependencies dict
    dependencies = {
        topo.id: analysis1.id,
        topo.id + 1: analysis2.id,
    }

    serializer = DependencyV2ListSerializer(context={"request": request})
    result = serializer.to_representation(dependencies)

    assert len(result) == 2
    assert all("id" in item for item in result)
    assert all("url" in item for item in result)
    assert all("task_state" in item for item in result)

    # Check that the IDs match
    result_ids = {item["id"] for item in result}
    assert result_ids == {analysis1.id, analysis2.id}


@pytest.mark.django_db
def test_dependency_v2_list_serializer_missing_workflow_result(api_rf):
    """Test DependencyV2ListSerializer handles missing WorkflowResults gracefully"""
    request = api_rf.get("/")

    # Create dependencies with non-existent workflow result IDs
    # NOTE: should dependencies ignore missing ones? Or raise error?
    dependencies = {
        1: 99999,  # Non-existent WorkflowResult
        2: 99998,  # Non-existent WorkflowResult
    }

    serializer = DependencyV2ListSerializer(context={"request": request})
    result = serializer.to_representation(dependencies)

    # Missing workflow results should be silently excluded
    assert result == []


@pytest.mark.django_db
def test_dependency_v2_list_serializer_partial_missing(
    api_rf, one_line_scan, test_analysis_function
):
    """Test DependencyV2ListSerializer with some missing WorkflowResults"""
    from topobank.testing.factories import AnalysisFactory

    request = api_rf.get("/")
    topo = one_line_scan

    analysis1 = AnalysisFactory(
        subject_topography=topo, user=topo.created_by, function=test_analysis_function
    )

    # Mix of existing and non-existing workflow results
    # NOTE: should dependencies ignore missing ones?
    dependencies = {
        topo.id: analysis1.id,
        topo.id + 1: 99999,  # Non-existent
    }

    serializer = DependencyV2ListSerializer(context={"request": request})
    result = serializer.to_representation(dependencies)

    # Should only include the existing one
    assert len(result) == 1
    assert result[0]["id"] == analysis1.id
