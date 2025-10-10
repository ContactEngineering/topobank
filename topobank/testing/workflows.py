import json
from typing import Dict

import numpy as np
from django.core.files.base import ContentFile

from ..analysis.models import Workflow
from ..analysis.workflows import VIZ_SERIES, WorkflowDefinition, WorkflowImplementation
from ..manager.models import Surface, Tag, Topography
from ..supplib.json import ExtendedJSONEncoder


class TestImplementation(WorkflowImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.testing.test"
        display_name = "Test implementation"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
            Surface: "surface_implementation",
            Tag: "tag_implementation",
        }

    class Parameters(WorkflowImplementation.Parameters):
        a: int = 1
        b: str = "foo"

    def topography_implementation(self, analysis, progress_recorder=None):
        topography = analysis.subject
        if progress_recorder:
            progress_recorder.set_progress(1, 2, "Hello from the test topography workflow!")
        analysis.folder.save_file("test.txt", "der", ContentFile("Test!!!"))
        fib = dict(
            name="Fibonacci series",
            x=np.array((1, 2, 3, 4, 5, 6, 7, 8)),
            y=np.array((0, 1, 1, 2, 3, 5, 8, 13)),
            std_err_y=np.zeros(8),
        )
        geo = dict(
            name="Geometric series",
            x=np.array((1, 2, 3, 4, 5, 6, 7, 8)),
            y=0.5 ** np.array((1, 2, 3, 4, 5, 6, 7, 8)),
            std_err_y=np.zeros(8),
        )
        analysis.folder.save_file(
            "series-0.json",
            "der",
            ContentFile(json.dumps(fib, cls=ExtendedJSONEncoder)),
        )
        analysis.folder.save_file(
            "series-1.json",
            "der",
            ContentFile(json.dumps(geo, cls=ExtendedJSONEncoder)),
        )
        return {
            "name": "Test result for test function called for topography "
            f"{topography}.",
            "xunit": "m",
            "yunit": "m",
            "xlabel": "x",
            "ylabel": "y",
            "series": [fib, geo],
            "alerts": [
                dict(
                    alert_class="alert-info",
                    message="This is a test for a measurement alert.",
                ),
            ],
            "comment": f"Arguments: a is {self._kwargs.a} and b is "
            f"{self._kwargs.b}",
        }

    def surface_implementation(self, analysis, progress_recorder=None):
        surface = analysis.subject
        if progress_recorder:
            progress_recorder.set_progress(1, 2, "Hello from the test surface workflow!")
        return {
            "name": "Test result for test function called for surface {}.".format(
                surface
            ),
            "xunit": "m",
            "yunit": "m",
            "xlabel": "x",
            "ylabel": "y",
            "series": [],
            "alerts": [
                dict(
                    alert_class="alert-info",
                    message="This is a test for a surface alert.",
                )
            ],
            "comment": f"a is {self._kwargs.a} and b is {self._kwargs.b}",
        }

    def tag_implementation(self, analysis, progress_recorder=None):
        tag = analysis.subject
        tag.authorize_user(permissions=analysis.permissions)
        name = (
            f"Test result for test function called for tag {tag}, "
            ", which is built from surfaces {}".format(
                [s.name for s in tag.surface_set.all()]
            )
        )

        return {
            "name": name,
            "xunit": "m",
            "yunit": "m",
            "xlabel": "x",
            "ylabel": "y",
            "series": [],
            "alerts": [
                dict(alert_class="alert-info", message="This is a test for an alert.")
            ],
            "surfaces": [surface.name for surface in tag.get_related_surfaces()],
            "comment": f"a is {self._kwargs.a} and b is {self._kwargs.b}",
        }


class TopographyOnlyTestImplementation(TestImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.testing.topography_only_test"
        display_name = "Topography-only test implementation"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
        }


class SecondTestImplementation(WorkflowImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.testing.test2"
        display_name = "Second test implementation"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
        }

        dependencies = {Topography: "topography_dependencies"}

    class Parameters(WorkflowImplementation.Parameters):
        c: int = 1
        d: float = 1.3

    def topography_dependencies(self, analysis) -> Dict[str, WorkflowDefinition]:
        topography = analysis.subject
        return {
            "dep1": WorkflowDefinition(
                subject=topography,
                function=Workflow.objects.get(name="topobank.testing.test"),
                kwargs=dict(a=self._kwargs.c),
            ),
            "dep2": WorkflowDefinition(
                subject=topography,
                function=Workflow.objects.get(name="topobank.testing.test"),
                kwargs=dict(b=self._kwargs.c * "A"),
            ),
        }

    def topography_implementation(
        self,
        analysis,
        dependencies: Dict = {},
        progress_recorder=None,
    ):
        dep1 = dependencies["dep1"]
        return {
            "name": "Test with dependencies",
            "result_from_dep": dep1.result["xunit"],
        }


class TestImplementationWithError(WorkflowImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.testing.test_error"
        display_name = "Test implementation with error"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
        }

    class Parameters(WorkflowImplementation.Parameters):
        c: int = 1
        d: float = 1.3

    def topography_implementation(
        self,
        analysis,
        dependencies: Dict = {},
        progress_recorder=None,
    ):
        raise RuntimeError("An error occurred!")


class TestImplementationWithErrorInDependency(WorkflowImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.testing.test_error_in_dependency"
        display_name = "Test implementation with error in dependency"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
        }

        dependencies = {Topography: "topography_dependencies"}

    class Parameters(WorkflowImplementation.Parameters):
        c: int = 1
        d: float = 1.3

    def topography_dependencies(self, analysis) -> Dict[str, WorkflowDefinition]:
        topography = analysis.subject
        return {
            "dep": WorkflowDefinition(
                subject=topography,
                function=Workflow.objects.get(
                    name="topobank.testing.test_error"
                ),
                kwargs=self._kwargs.model_dump(),
            ),
        }

    def topography_implementation(
        self,
        analysis,
        dependencies: Dict = {},
        progress_recorder=None,
    ):
        return
