"""Tests for DjangoWorkflowContext."""

from unittest.mock import MagicMock

import pytest
import xarray as xr

from topobank.analysis.context import DjangoWorkflowContext, create_workflow_context
from topobank.analysis.models import Workflow
from topobank.authorization import get_permission_model
from topobank.files.models import ManifestSet
from topobank.testing.factories import (
    Topography1DFactory,
    TopographyAnalysisFactory,
    UserFactory,
)


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def permissions(db):
    return get_permission_model().objects.create()


@pytest.fixture
def analysis_with_folder(settings, user, permissions, sync_analysis_functions):
    """Create an analysis with a folder for testing."""
    settings.DELETE_EXISTING_FILES = True

    topo = Topography1DFactory()
    func = Workflow.objects.get(name="topobank.testing.test")

    # Create ManifestSet with storage_prefix
    folder = ManifestSet.objects.create(
        permissions=permissions,
        storage_prefix="data-lake/test/context",
    )

    analysis = TopographyAnalysisFactory(
        subject_topography=topo,
        function=func,
        kwargs={"a": 42, "b": "test_value"},
    )
    analysis.folder = folder
    analysis.save()

    return analysis


@pytest.mark.django_db
class TestDjangoWorkflowContext:
    """Tests for DjangoWorkflowContext class."""

    def test_context_creation(self, analysis_with_folder):
        """Test creating a context from an analysis."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        assert ctx.analysis == analysis_with_folder
        assert ctx.folder == analysis_with_folder.folder

    def test_storage_prefix_property(self, analysis_with_folder):
        """Test storage_prefix property."""
        ctx = DjangoWorkflowContext(analysis_with_folder)
        assert ctx.storage_prefix == "data-lake/test/context"

    def test_storage_prefix_empty_when_none(self, settings, user, permissions, sync_analysis_functions):
        """Test storage_prefix returns empty string when folder has no prefix."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        folder = ManifestSet.objects.create(
            permissions=permissions,
            storage_prefix=None,  # No prefix
        )

        analysis = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )
        analysis.folder = folder
        analysis.save()

        ctx = DjangoWorkflowContext(analysis)
        assert ctx.storage_prefix == ""

    def test_kwargs_property(self, analysis_with_folder):
        """Test kwargs property."""
        ctx = DjangoWorkflowContext(analysis_with_folder)
        assert ctx.kwargs == {"a": 42, "b": "test_value"}

    def test_save_and_read_json(self, analysis_with_folder):
        """Test saving and reading JSON data."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        test_data = {"key": "value", "number": 42, "nested": {"a": 1}}
        ctx.save_json("test.json", test_data)

        # Read it back
        loaded = ctx.read_json("test.json")
        assert loaded == test_data

    def test_save_file(self, analysis_with_folder):
        """Test saving raw bytes."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        test_bytes = b"Hello, World!"
        ctx.save_file("test.bin", test_bytes)

        # Read it back
        loaded = ctx.read_file("test.bin")
        assert loaded == test_bytes

    def test_open_file(self, analysis_with_folder):
        """Test opening a file for reading."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        # Save some data first
        ctx.save_json("open_test.json", {"data": "test"})

        # Open and read
        with ctx.open_file("open_test.json") as f:
            content = f.read()
            assert "data" in content

    def test_exists(self, analysis_with_folder):
        """Test checking if a file exists."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        assert not ctx.exists("nonexistent.json")

        ctx.save_json("exists_test.json", {"test": True})
        assert ctx.exists("exists_test.json")

    def test_save_and_read_xarray(self, analysis_with_folder):
        """Test saving and reading xarray Dataset."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        # Create a simple dataset
        ds = xr.Dataset(
            {"temperature": (["x", "y"], [[1.0, 2.0], [3.0, 4.0]])},
            coords={"x": [0, 1], "y": [0, 1]},
        )

        ctx.save_xarray("test.nc", ds)

        # Read it back
        loaded = ctx.read_xarray("test.nc")
        assert "temperature" in loaded
        xr.testing.assert_equal(loaded, ds)

    def test_dependency_access(self, settings, user, permissions, sync_analysis_functions):
        """Test accessing dependency context."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        # Create dependency analysis
        dep_folder = ManifestSet.objects.create(
            permissions=permissions,
            storage_prefix="data-lake/test/dependency",
        )
        dep_analysis = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            kwargs={"a": 1, "b": "dependency"},
        )
        dep_analysis.folder = dep_folder
        dep_analysis.save()

        # Create main analysis
        main_folder = ManifestSet.objects.create(
            permissions=permissions,
            storage_prefix="data-lake/test/main",
        )
        main_analysis = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            kwargs={"a": 2, "b": "main"},
        )
        main_analysis.folder = main_folder
        main_analysis.save()

        # Create context with dependency
        ctx = DjangoWorkflowContext(
            main_analysis,
            dependencies={"my_dep": dep_analysis},
        )

        # Access dependency
        dep_ctx = ctx.dependency("my_dep")
        assert dep_ctx.kwargs == {"a": 1, "b": "dependency"}
        assert dep_ctx.storage_prefix == "data-lake/test/dependency"

    def test_dependency_not_found_raises(self, analysis_with_folder):
        """Test that accessing unknown dependency raises KeyError."""
        ctx = DjangoWorkflowContext(analysis_with_folder, dependencies={})

        with pytest.raises(KeyError, match="Unknown dependency"):
            ctx.dependency("nonexistent")

    def test_has_dependency(self, settings, user, permissions, sync_analysis_functions):
        """Test has_dependency method."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        dep_analysis = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )

        main_analysis = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )

        ctx = DjangoWorkflowContext(
            main_analysis,
            dependencies={"exists": dep_analysis},
        )

        assert ctx.has_dependency("exists")
        assert not ctx.has_dependency("not_exists")

    def test_dependency_keys(self, settings, user, permissions, sync_analysis_functions):
        """Test dependency_keys method."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        dep1 = TopographyAnalysisFactory(subject_topography=topo, function=func)
        dep2 = TopographyAnalysisFactory(subject_topography=topo, function=func)

        main = TopographyAnalysisFactory(subject_topography=topo, function=func)

        ctx = DjangoWorkflowContext(
            main,
            dependencies={"dep_a": dep1, "dep_b": dep2},
        )

        keys = ctx.dependency_keys()
        assert set(keys) == {"dep_a", "dep_b"}

    def test_report_progress(self, analysis_with_folder):
        """Test progress reporting."""
        mock_recorder = MagicMock()
        ctx = DjangoWorkflowContext(
            analysis_with_folder,
            progress_recorder=mock_recorder,
        )

        ctx.report_progress(50, 100, "Halfway there")

        mock_recorder.set_progress.assert_called_once_with(50, 100, "Halfway there")

    def test_report_progress_no_recorder(self, analysis_with_folder):
        """Test that report_progress works without recorder."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        # Should not raise
        ctx.report_progress(50, 100, "Test")

    def test_subject_property(self, analysis_with_folder):
        """Test subject property returns resolved SurfaceTopography."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        # Subject should be resolved to native SurfaceTopography
        subject = ctx.subject
        assert subject is not None
        # SurfaceTopography objects have heights() method
        assert hasattr(subject, 'heights')

    def test_subject_name_property(self, analysis_with_folder):
        """Test subject_name property returns the subject's name."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        # Subject name should match the Django model's name
        expected_name = analysis_with_folder.subject.name
        assert ctx.subject_name == expected_name

    def test_subject_url_property(self, analysis_with_folder):
        """Test subject_url property."""
        ctx = DjangoWorkflowContext(analysis_with_folder)

        # subject_url should be a string (may be empty if get_absolute_url not available)
        assert isinstance(ctx.subject_url, str)

    def test_implements_topobank_workflow_context(self, analysis_with_folder):
        """Test that DjangoWorkflowContext implements TopobankWorkflowContext."""
        from topobank.analysis.context import TopobankWorkflowContext

        ctx = DjangoWorkflowContext(analysis_with_folder)

        # Check it's recognized as implementing the protocol
        assert isinstance(ctx, TopobankWorkflowContext)


@pytest.mark.django_db
class TestCreateWorkflowContext:
    """Tests for create_workflow_context factory function."""

    def test_create_workflow_context(self, analysis_with_folder):
        """Test factory function creates valid context."""
        ctx = create_workflow_context(analysis_with_folder)

        # Should return a WorkflowContext-compatible object
        assert hasattr(ctx, "storage_prefix")
        assert hasattr(ctx, "kwargs")
        assert hasattr(ctx, "save_json")
        assert hasattr(ctx, "read_json")
        assert hasattr(ctx, "dependency")

    def test_create_workflow_context_with_dependencies(self, settings, user, permissions, sync_analysis_functions):
        """Test factory function with dependencies."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        dep = TopographyAnalysisFactory(subject_topography=topo, function=func)
        main = TopographyAnalysisFactory(subject_topography=topo, function=func)

        ctx = create_workflow_context(main, dependencies={"dep": dep})

        assert ctx.has_dependency("dep")
