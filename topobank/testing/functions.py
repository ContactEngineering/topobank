import json

import numpy as np
from django.core.files.base import ContentFile

from ..analysis.functions import VIZ_SERIES, AnalysisImplementation, AnalysisInputData
from ..analysis.models import AnalysisFunction
from ..manager.models import Surface, Tag, Topography
from ..supplib.json import ExtendedJSONEncoder


class TestImplementation(AnalysisImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.analysis.test"
        display_name = "Test implementation"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
            Surface: "surface_implementation",
            Tag: "tag_implementation",
        }

    class Parameters(AnalysisImplementation.Parameters):
        a: int = 1
        b: str = "foo"

    def topography_implementation(self, analysis, progress_recorder=None):
        topography = analysis.subject
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
        name = "topobank.analysis.topography_only_test"
        display_name = "Topography-only test implementation"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
        }


class SecondTestImplementation(AnalysisImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.analysis.test2"
        display_name = "Second test implementation"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
        }

        dependencies = {Topography: "topography_dependencies"}

    class Parameters(AnalysisImplementation.Parameters):
        c: int = 1
        d: float = 1.3

    def topography_dependencies(self, analysis) -> list[AnalysisInputData]:
        topography = analysis.subject
        return [
            AnalysisInputData(
                subject=topography,
                function=AnalysisFunction.objects.get(name="Test implementation"),
                kwargs=dict(a=self._kwargs.c),
            ),
            AnalysisInputData(
                subject=topography,
                function=AnalysisFunction.objects.get(name="Test implementation"),
                kwargs=dict(b=self._kwargs.c * "A"),
            ),
        ]

    def topography_implementation(
        self,
        analysis,
        dependencies: list = None,
        progress_recorder=None,
    ):
        (dep1, dep2) = dependencies
        return {
            "name": "Test with dependencies",
            "result_from_dep": dep1.result["xunit"],
        }


class TestImplementationWithError(AnalysisImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.analysis.test_error"
        display_name = "Test implementation with error"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
        }

    class Parameters(AnalysisImplementation.Parameters):
        c: int = 1
        d: float = 1.3

    def topography_implementation(
        self,
        analysis,
        dependencies: list = None,
        progress_recorder=None,
    ):
        raise RuntimeError("An error occurred!")


class TestImplementationWithErrorInDependency(AnalysisImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.analysis.test_error_in_dependency"
        display_name = "Test implementation with error in dependency"
        visualization_type = VIZ_SERIES

        implementations = {
            Topography: "topography_implementation",
        }

        dependencies = {Topography: "topography_dependencies"}

    class Parameters(AnalysisImplementation.Parameters):
        c: int = 1
        d: float = 1.3

    def topography_dependencies(self, analysis) -> list[AnalysisInputData]:
        topography = analysis.subject
        return [
            AnalysisInputData(
                subject=topography,
                function=AnalysisFunction.objects.get(
                    name="Test implementation with error"
                ),
                kwargs=self._kwargs.model_dump(),
            ),
        ]

    def topography_implementation(
        self,
        analysis,
        dependencies: list = None,
        progress_recorder=None,
    ):
        return
