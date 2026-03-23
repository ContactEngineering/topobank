"""Tests for manifest preparation and reconciliation."""

from unittest.mock import patch

import pytest
from muflow import WorkflowNode, WorkflowPlan

from topobank.analysis.models import PlanRecord, Workflow, WorkflowResult
from topobank.analysis.preparation import (
    get_subject_from_key,
    prepare_plan_records,
    reconcile_manifest_set,
)
from topobank.authorization import get_permission_model
from topobank.files.models import Manifest, ManifestSet
from topobank.testing.factories import (
    SurfaceFactory,
    TagFactory,
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


def create_simple_plan(subject_key: str, output_files: list = None):
    """Create a simple single-node WorkflowPlan."""
    if output_files is None:
        output_files = ["result.json"]

    node = WorkflowNode(
        key="data-lake/results/test/abc123",
        function="topobank.testing.test",
        subject_key=subject_key,
        kwargs={"param": "value"},
        storage_prefix="data-lake/results/test/abc123",
        depends_on=[],
        depended_on_by=[],
        output_files=output_files,
        cached=False,
        analysis_id=None,
    )
    return WorkflowPlan(
        nodes={"data-lake/results/test/abc123": node},
        root_key="data-lake/results/test/abc123",
    )


@pytest.mark.django_db
class TestGetSubjectFromKey:
    """Tests for get_subject_from_key function."""

    def test_topography_key(self, settings):
        """Test resolving topography from key."""
        settings.DELETE_EXISTING_FILES = True
        topo = Topography1DFactory()
        resolved = get_subject_from_key(f"topography:{topo.id}")
        assert resolved == topo

    def test_surface_key(self):
        """Test resolving surface from key."""
        surface = SurfaceFactory()
        resolved = get_subject_from_key(f"surface:{surface.id}")
        assert resolved == surface

    def test_tag_key(self):
        """Test resolving tag from key."""
        tag = TagFactory()
        resolved = get_subject_from_key(f"tag:{tag.id}")
        assert resolved == tag

    def test_invalid_format_raises(self):
        """Test that invalid key format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid subject key format"):
            get_subject_from_key("invalid-key")

    def test_unknown_type_raises(self):
        """Test that unknown subject type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown subject type"):
            get_subject_from_key("unknown:123")

    def test_nonexistent_id_raises(self):
        """Test that nonexistent ID raises DoesNotExist."""
        from topobank.manager.models import Topography

        with pytest.raises(Topography.DoesNotExist):
            get_subject_from_key("topography:999999")


@pytest.mark.django_db
class TestPrepareplanRecords:
    """Tests for prepare_plan_records function."""

    def test_creates_plan_record(self, settings, user, sync_analysis_functions):
        """Test that prepare_plan_records creates a PlanRecord."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        plan = create_simple_plan(f"topography:{topo.id}")

        plan_record = prepare_plan_records(plan, user)

        assert plan_record.id is not None
        assert plan_record.state == PlanRecord.PENDING
        assert plan_record.created_by == user
        assert plan_record.root_function.name == "topobank.testing.test"
        assert plan_record.root_kwargs == {"param": "value"}

    def test_creates_workflow_results(self, settings, user, sync_analysis_functions):
        """Test that prepare_plan_records creates WorkflowResults for each node."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        plan = create_simple_plan(f"topography:{topo.id}")

        plan_record = prepare_plan_records(plan, user)

        # Should have one result linked to the plan
        assert plan_record.results.count() == 1

        result = plan_record.results.first()
        assert result.node_key == "data-lake/results/test/abc123"
        assert result.function.name == "topobank.testing.test"
        assert result.kwargs == {"param": "value"}
        assert result.task_state == WorkflowResult.PENDING
        assert result.subject == topo

    def test_creates_manifest_set_with_prefix(self, settings, user, sync_analysis_functions):
        """Test that ManifestSet is created with storage_prefix."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        plan = create_simple_plan(f"topography:{topo.id}")

        plan_record = prepare_plan_records(plan, user)
        result = plan_record.results.first()

        assert result.folder is not None
        assert result.folder.storage_prefix == "data-lake/results/test/abc123"

    def test_creates_write_ahead_manifests(self, settings, user, sync_analysis_functions):
        """Test that write-ahead manifests are created (confirmed_at=None)."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        plan = create_simple_plan(
            f"topography:{topo.id}",
            output_files=["result.json", "model.nc"],
        )

        plan_record = prepare_plan_records(plan, user)
        result = plan_record.results.first()

        # Should have two manifests
        manifests = result.folder.files.all()
        assert manifests.count() == 2

        filenames = set(m.filename for m in manifests)
        assert filenames == {"result.json", "model.nc"}

        # All should be unconfirmed (write-ahead)
        for manifest in manifests:
            assert manifest.confirmed_at is None
            assert manifest.kind == "der"

    def test_updates_plan_json_with_analysis_ids(self, settings, user, sync_analysis_functions):
        """Test that plan_json is updated with analysis IDs."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        plan = create_simple_plan(f"topography:{topo.id}")

        plan_record = prepare_plan_records(plan, user)

        # Check plan_json was updated
        updated_plan = plan_record.plan_json
        node = updated_plan["nodes"]["data-lake/results/test/abc123"]
        assert node["analysis_id"] is not None
        assert node["analysis_id"] == plan_record.results.first().id

    def test_skips_cached_nodes(self, settings, user, sync_analysis_functions):
        """Test that cached nodes don't get new WorkflowResults."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        plan = create_simple_plan(f"topography:{topo.id}")

        # Mark node as cached
        plan.nodes["data-lake/results/test/abc123"].cached = True
        plan.nodes["data-lake/results/test/abc123"].analysis_id = 999

        plan_record = prepare_plan_records(plan, user)

        # No results should be created (node is cached)
        assert plan_record.results.count() == 0

    def test_unknown_workflow_raises(self, settings, user, sync_analysis_functions):
        """Test that unknown workflow raises ValueError."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()

        # Create plan with unknown workflow
        node = WorkflowNode(
            key="node-1",
            function="nonexistent.workflow",
            subject_key=f"topography:{topo.id}",
            kwargs={},
            storage_prefix="data-lake/results/test/abc123",
            depends_on=[],
            depended_on_by=[],
            output_files=[],
            cached=False,
            analysis_id=None,
        )
        plan = WorkflowPlan(nodes={"node-1": node}, root_key="node-1")

        with pytest.raises(ValueError, match="Unknown workflow"):
            prepare_plan_records(plan, user)


@pytest.mark.django_db
class TestReconcileManifestSet:
    """Tests for reconcile_manifest_set function."""

    def test_confirms_existing_files(self, settings, user, permissions, sync_analysis_functions):
        """Test that existing files are confirmed."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        # Create ManifestSet with storage_prefix
        folder = ManifestSet.objects.create(
            permissions=permissions,
            storage_prefix="data-lake/results/test/reconcile",
        )

        # Create unconfirmed manifest
        manifest = Manifest.objects.create(
            folder=folder,
            filename="result.json",
            kind="der",
            permissions=permissions,
            confirmed_at=None,
        )

        # Create analysis
        result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )
        result.folder = folder
        result.save()

        # Mock storage to say file exists
        with patch.object(
            result.folder.__class__,
            "files",
            result.folder.files,
        ):
            with patch("topobank.analysis.preparation.default_storage") as mock_storage:
                mock_storage.exists.return_value = True
                mock_storage.listdir.return_value = ([], ["result.json"])

                reconcile_manifest_set(result)

        # Manifest should now be confirmed
        manifest.refresh_from_db()
        assert manifest.confirmed_at is not None
        assert manifest.file.name == "data-lake/results/test/reconcile/result.json"

    def test_raises_on_missing_required_file(self, settings, user, permissions, sync_analysis_functions):
        """Test that missing required file raises RuntimeError."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        folder = ManifestSet.objects.create(
            permissions=permissions,
            storage_prefix="data-lake/results/test/missing",
        )

        # Create unconfirmed manifest
        Manifest.objects.create(
            folder=folder,
            filename="required.json",
            kind="der",
            permissions=permissions,
            confirmed_at=None,
        )

        result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )
        result.folder = folder
        result.save()

        # Mock storage to say file does NOT exist
        with patch("topobank.analysis.preparation.default_storage") as mock_storage:
            mock_storage.exists.return_value = False

            with pytest.raises(RuntimeError, match="Required file.*missing"):
                reconcile_manifest_set(result)

    def test_skips_legacy_storage(self, settings, user, permissions, sync_analysis_functions):
        """Test that reconciliation skips results without storage_prefix."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        # Create folder WITHOUT storage_prefix (legacy mode)
        folder = ManifestSet.objects.create(
            permissions=permissions,
            storage_prefix=None,  # Legacy mode
        )

        result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )
        result.folder = folder
        result.save()

        # Should not raise - just skip
        with patch("topobank.analysis.preparation.default_storage") as mock_storage:
            reconcile_manifest_set(result)
            # Storage should not be queried
            mock_storage.exists.assert_not_called()

    def test_skips_no_folder(self, settings, user, permissions, sync_analysis_functions):
        """Test that reconciliation handles results without folder."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        result = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
        )
        result.folder = None
        result.save()

        # Should not raise - just skip
        with patch("topobank.analysis.preparation.default_storage") as mock_storage:
            reconcile_manifest_set(result)
            mock_storage.exists.assert_not_called()
