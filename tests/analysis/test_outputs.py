"""
Tests for workflow output schema infrastructure.
"""

import pydantic
import pytest

from topobank.analysis.outputs import OutputFile, get_outputs_schema
from topobank.analysis.workflows import WorkflowImplementation


class TestOutputFile:
    """Tests for the OutputFile dataclass."""

    def test_output_file_minimal(self):
        """Test creating an OutputFile with minimal parameters."""
        output = OutputFile(file_type="json")
        assert output.file_type == "json"
        assert output.description == ""
        assert output.schema is None
        assert output.optional is False

    def test_output_file_full(self):
        """Test creating an OutputFile with all parameters."""

        class MySchema(pydantic.BaseModel):
            value: float

        output = OutputFile(
            file_type="netcdf",
            description="Model file",
            schema=MySchema,
            optional=True,
        )
        assert output.file_type == "netcdf"
        assert output.description == "Model file"
        assert output.schema == MySchema
        assert output.optional is True

    def test_output_file_types(self):
        """Test all valid file types."""
        for file_type in ["json", "netcdf", "text", "binary"]:
            output = OutputFile(file_type=file_type)
            assert output.file_type == file_type


class TestGetOutputsSchema:
    """Tests for the get_outputs_schema function."""

    def test_none_outputs_class(self):
        """Test with None outputs class."""
        schema = get_outputs_schema(None)
        assert schema == {"result_schema": None, "files": []}

    def test_empty_outputs_class(self):
        """Test with an empty Outputs class."""

        class EmptyOutputs:
            pass

        schema = get_outputs_schema(EmptyOutputs)
        assert schema == {"result_schema": None, "files": []}

    def test_result_schema_only(self):
        """Test Outputs class with only result schema."""

        class ResultModel(pydantic.BaseModel):
            value: float
            error: float

        class OutputsWithResult:
            result = ResultModel

        schema = get_outputs_schema(OutputsWithResult)
        assert schema["result_schema"] is not None
        assert "properties" in schema["result_schema"]
        assert "value" in schema["result_schema"]["properties"]
        assert "error" in schema["result_schema"]["properties"]
        assert schema["files"] == []

    def test_files_only(self):
        """Test Outputs class with only file descriptors."""

        class OutputsWithFiles:
            result = None
            files = {
                "model.nc": OutputFile(
                    file_type="netcdf",
                    description="Trained model",
                ),
            }

        schema = get_outputs_schema(OutputsWithFiles)
        assert schema["result_schema"] is None
        assert len(schema["files"]) == 1
        assert schema["files"][0]["filename"] == "model.nc"
        assert schema["files"][0]["file_type"] == "netcdf"
        assert schema["files"][0]["description"] == "Trained model"
        assert schema["files"][0]["optional"] is False
        assert schema["files"][0]["schema"] is None

    def test_file_with_schema(self):
        """Test file descriptor with JSON schema."""

        class MetadataModel(pydantic.BaseModel):
            name: str
            version: int

        class OutputsWithFileSchema:
            result = None
            files = {
                "metadata.json": OutputFile(
                    file_type="json",
                    description="Metadata file",
                    schema=MetadataModel,
                ),
            }

        schema = get_outputs_schema(OutputsWithFileSchema)
        assert len(schema["files"]) == 1
        file_info = schema["files"][0]
        assert file_info["filename"] == "metadata.json"
        assert file_info["schema"] is not None
        assert "properties" in file_info["schema"]
        assert "name" in file_info["schema"]["properties"]
        assert "version" in file_info["schema"]["properties"]

    def test_full_outputs(self):
        """Test Outputs class with both result and files."""

        class ResultModel(pydantic.BaseModel):
            predicted_value: float
            predicted_error: float

        class MetadataModel(pydantic.BaseModel):
            model_name: str

        class FullOutputs:
            result = ResultModel
            files = {
                "model.nc": OutputFile(
                    file_type="netcdf",
                    description="Trained model",
                ),
                "metadata.json": OutputFile(
                    file_type="json",
                    description="Model metadata",
                    schema=MetadataModel,
                    optional=True,
                ),
            }

        schema = get_outputs_schema(FullOutputs)

        # Check result schema
        assert schema["result_schema"] is not None
        assert "predicted_value" in schema["result_schema"]["properties"]
        assert "predicted_error" in schema["result_schema"]["properties"]

        # Check files
        assert len(schema["files"]) == 2
        filenames = [f["filename"] for f in schema["files"]]
        assert "model.nc" in filenames
        assert "metadata.json" in filenames

        # Check metadata.json has schema and is optional
        metadata_file = next(f for f in schema["files"] if f["filename"] == "metadata.json")
        assert metadata_file["optional"] is True
        assert metadata_file["schema"] is not None


class TestWorkflowImplementationOutputs:
    """Tests for WorkflowImplementation.get_outputs_schema()."""

    def test_default_outputs_schema(self):
        """Test that default implementation returns empty schema."""
        schema = WorkflowImplementation.get_outputs_schema()
        assert schema == {"result_schema": None, "files": []}

    def test_implementation_with_outputs(self):
        """Test implementation with Outputs class."""

        class ResultModel(pydantic.BaseModel):
            value: float

        class MyWorkflow(WorkflowImplementation):
            class Outputs:
                result = ResultModel
                files = {
                    "data.txt": OutputFile(file_type="text", description="Output data"),
                }

        schema = MyWorkflow.get_outputs_schema()
        assert schema["result_schema"] is not None
        assert len(schema["files"]) == 1
        assert schema["files"][0]["filename"] == "data.txt"

    def test_implementation_without_outputs(self):
        """Test implementation without Outputs class (legacy)."""

        class LegacyWorkflow(WorkflowImplementation):
            pass

        schema = LegacyWorkflow.get_outputs_schema()
        assert schema == {"result_schema": None, "files": []}


@pytest.mark.django_db
class TestWorkflowModelOutputsSchema:
    """Tests for Workflow.get_outputs_schema() method."""

    def test_workflow_outputs_schema(self, test_analysis_function):
        """Test that Workflow model returns outputs schema."""
        schema = test_analysis_function.get_outputs_schema()
        # TestImplementation doesn't have Outputs, so should return empty
        assert schema == {"result_schema": None, "files": []}

    def test_workflow_with_outputs_schema(self):
        """Test Workflow with declared Outputs returns proper schema."""
        from topobank.analysis.models import Workflow

        workflow = Workflow.objects.get(name="topobank.testing.test_with_outputs")
        schema = workflow.get_outputs_schema()

        # Check result schema
        assert schema["result_schema"] is not None
        props = schema["result_schema"]["properties"]
        assert "predicted_value" in props
        assert "predicted_error" in props
        assert "confidence" in props

        # Check files
        assert len(schema["files"]) == 2
        filenames = [f["filename"] for f in schema["files"]]
        assert "model.nc" in filenames
        assert "metadata.json" in filenames

        # Check model.nc
        model_file = next(f for f in schema["files"] if f["filename"] == "model.nc")
        assert model_file["file_type"] == "netcdf"
        assert model_file["description"] == "Trained model in NetCDF format"
        assert model_file["optional"] is False
        assert model_file["schema"] is None

        # Check metadata.json
        metadata_file = next(f for f in schema["files"] if f["filename"] == "metadata.json")
        assert metadata_file["file_type"] == "json"
        assert metadata_file["description"] == "Model metadata"
        assert metadata_file["optional"] is True
        assert metadata_file["schema"] is not None
        assert "model_name" in metadata_file["schema"]["properties"]
        assert "version" in metadata_file["schema"]["properties"]


@pytest.mark.django_db
class TestWorkflowSerializerOutputsSchema:
    """Tests for WorkflowSerializer outputs_schema field."""

    def test_serializer_includes_outputs_schema(self, api_rf):
        """Test that WorkflowSerializer includes outputs_schema field."""
        from rest_framework.request import Request

        from topobank.analysis.models import Workflow
        from topobank.analysis.serializers import WorkflowSerializer

        workflow = Workflow.objects.get(name="topobank.testing.test_with_outputs")

        # Create a mock request
        request = api_rf.get("/")
        serializer = WorkflowSerializer(workflow, context={"request": Request(request)})
        data = serializer.data

        assert "outputs_schema" in data
        assert data["outputs_schema"]["result_schema"] is not None
        assert len(data["outputs_schema"]["files"]) == 2

    def test_serializer_empty_outputs_schema(self, api_rf, test_analysis_function):
        """Test that WorkflowSerializer returns empty schema for legacy workflows."""
        from rest_framework.request import Request

        from topobank.analysis.serializers import WorkflowSerializer

        request = api_rf.get("/")
        serializer = WorkflowSerializer(
            test_analysis_function, context={"request": Request(request)}
        )
        data = serializer.data

        assert "outputs_schema" in data
        assert data["outputs_schema"] == {"result_schema": None, "files": []}


class TestTestImplementationWithOutputs:
    """Verify TestImplementationWithOutputs has correct Outputs class."""

    def test_outputs_class_exists(self):
        """Test that TestImplementationWithOutputs has Outputs class."""
        from topobank.testing.workflows import TestImplementationWithOutputs

        assert hasattr(TestImplementationWithOutputs, "Outputs")
        assert TestImplementationWithOutputs.Outputs is not None

    def test_outputs_schema_generation(self):
        """Test that get_outputs_schema works for TestImplementationWithOutputs."""
        from topobank.testing.workflows import TestImplementationWithOutputs

        schema = TestImplementationWithOutputs.get_outputs_schema()

        # Check result schema
        assert schema["result_schema"] is not None
        props = schema["result_schema"]["properties"]
        assert "predicted_value" in props
        assert "predicted_error" in props
        assert "confidence" in props

        # Check files
        assert len(schema["files"]) == 2
        filenames = [f["filename"] for f in schema["files"]]
        assert "model.nc" in filenames
        assert "metadata.json" in filenames
