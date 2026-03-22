"""Tests for WorkflowPlanner and related functions."""

import pytest

from topobank.analysis.models import Workflow, WorkflowResult
from topobank.analysis.planner import WorkflowPlanner, get_subject_key
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


@pytest.mark.django_db
class TestGetSubjectKey:
    """Tests for get_subject_key function."""

    def test_topography_subject_key(self, settings):
        """Test subject key for Topography."""
        settings.DELETE_EXISTING_FILES = True
        topo = Topography1DFactory()
        key = get_subject_key(topo)
        assert key == f"topography:{topo.id}"

    def test_surface_subject_key(self):
        """Test subject key for Surface."""
        surface = SurfaceFactory()
        key = get_subject_key(surface)
        assert key == f"surface:{surface.id}"

    def test_tag_subject_key(self):
        """Test subject key for Tag."""
        tag = TagFactory()
        key = get_subject_key(tag)
        assert key == f"tag:{tag.id}"

    def test_invalid_subject_raises(self):
        """Test that invalid subject type raises TypeError."""
        with pytest.raises(TypeError, match="Unknown subject type"):
            get_subject_key("not a subject")


@pytest.mark.django_db
class TestWorkflowPlanner:
    """Tests for WorkflowPlanner class."""

    def test_build_plan_simple_workflow(self, settings, user, sync_analysis_functions):
        """Test building a plan for a simple workflow with no dependencies."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        planner = WorkflowPlanner(check_cache=False)

        plan = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={},
            user=user,
        )

        # Should have one node
        assert len(plan.nodes) == 1
        assert plan.root_key in plan.nodes

        # Check node properties
        node = plan.nodes[plan.root_key]
        assert node.function == "topobank.testing.test"
        assert node.subject_key == f"topography:{topo.id}"
        assert node.kwargs == {}
        assert node.depends_on == []
        assert node.cached is False
        assert "muflows/" in node.storage_prefix

    def test_build_plan_with_kwargs(self, settings, user, sync_analysis_functions):
        """Test that kwargs affect the storage prefix."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        planner = WorkflowPlanner(check_cache=False)

        plan1 = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={"param": "value1"},
            user=user,
        )

        plan2 = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={"param": "value2"},
            user=user,
        )

        # Different kwargs should produce different storage prefixes
        assert plan1.root_key != plan2.root_key

    def test_build_plan_same_inputs_same_key(self, settings, user, sync_analysis_functions):
        """Test that same inputs produce same storage prefix (content-addressed)."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        planner = WorkflowPlanner(check_cache=False)

        plan1 = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={"param": "value"},
            user=user,
        )

        plan2 = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={"param": "value"},
            user=user,
        )

        # Same inputs should produce same key
        assert plan1.root_key == plan2.root_key

    def test_build_plan_detects_cached_result(self, settings, user, sync_analysis_functions):
        """Test that planner detects cached (existing successful) results."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        # Create an existing successful result
        existing = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            kwargs={},
            task_state=WorkflowResult.SUCCESS,
        )
        # Grant user access
        existing.permissions.grant(user, "view")

        # Build plan with cache checking enabled
        planner = WorkflowPlanner(check_cache=True)
        plan = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={},
            user=user,
        )

        # Node should be marked as cached
        node = plan.nodes[plan.root_key]
        assert node.cached is True
        assert node.analysis_id == existing.id

    def test_build_plan_ignores_failed_results(self, settings, user, sync_analysis_functions):
        """Test that planner ignores failed results when checking cache."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        func = Workflow.objects.get(name="topobank.testing.test")

        # Create a failed result
        failed = TopographyAnalysisFactory(
            subject_topography=topo,
            function=func,
            kwargs={},
            task_state=WorkflowResult.FAILURE,
        )
        failed.permissions.grant(user, "view")

        # Build plan
        planner = WorkflowPlanner(check_cache=True)
        plan = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={},
            user=user,
        )

        # Node should NOT be cached (failed results don't count)
        node = plan.nodes[plan.root_key]
        assert node.cached is False

    def test_build_plan_different_subjects(self, settings, user, sync_analysis_functions):
        """Test building plans for different subject types."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        surface = SurfaceFactory()

        planner = WorkflowPlanner(check_cache=False)

        plan_topo = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={},
            user=user,
        )

        plan_surface = planner.build_plan(
            function_name="topobank.testing.test",
            subject=surface,
            kwargs={},
            user=user,
        )

        # Different subjects should produce different keys
        assert plan_topo.root_key != plan_surface.root_key

        # Check subject keys are correct
        topo_node = plan_topo.nodes[plan_topo.root_key]
        surface_node = plan_surface.nodes[plan_surface.root_key]

        assert topo_node.subject_key == f"topography:{topo.id}"
        assert surface_node.subject_key == f"surface:{surface.id}"

    def test_build_plan_unknown_workflow_raises(self, settings, user, sync_analysis_functions):
        """Test that unknown workflow name raises ValueError."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        planner = WorkflowPlanner(check_cache=False)

        with pytest.raises(ValueError, match="Unknown workflow"):
            planner.build_plan(
                function_name="nonexistent.workflow",
                subject=topo,
                kwargs={},
                user=user,
            )

    def test_plan_ready_nodes(self, settings, user, sync_analysis_functions):
        """Test WorkflowPlan.ready_nodes() method."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        planner = WorkflowPlanner(check_cache=False)

        plan = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={},
            user=user,
        )

        # With no completed nodes, the leaf node should be ready
        ready = plan.ready_nodes(completed=set())
        assert len(ready) == 1
        assert ready[0].key == plan.root_key

        # After completing the root, nothing should be ready
        ready = plan.ready_nodes(completed={plan.root_key})
        assert len(ready) == 0

    def test_plan_leaf_nodes(self, settings, user, sync_analysis_functions):
        """Test WorkflowPlan.leaf_nodes() method."""
        settings.DELETE_EXISTING_FILES = True

        topo = Topography1DFactory()
        planner = WorkflowPlanner(check_cache=False)

        plan = planner.build_plan(
            function_name="topobank.testing.test",
            subject=topo,
            kwargs={},
            user=user,
        )

        # Simple workflow with no dependencies - root is the only leaf
        leaves = plan.leaf_nodes()
        assert len(leaves) == 1
        assert leaves[0].key == plan.root_key
