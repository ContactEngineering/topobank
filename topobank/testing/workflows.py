import json
from typing import Dict

import numpy as np
import pydantic
from django.core.files.base import ContentFile
from muGrid.Timer import Timer

from ..analysis.models import RESULT_FILE_BASENAME, Workflow
from ..analysis.outputs import OutputFile
from ..analysis.registry import register_implementation
from ..analysis.workflows import WorkflowDefinition, WorkflowImplementation
from ..manager.models import Surface, Tag, Topography
from ..supplib.dict import store_split_dict
from ..supplib.json import ExtendedJSONEncoder


class TestImplementation(WorkflowImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.testing.test"
        display_name = "Test implementation"

        implementations = {
            Topography: "topography_implementation",
            Surface: "surface_implementation",
            Tag: "tag_implementation",
        }

    class Parameters(WorkflowImplementation.Parameters):
        a: int = 1
        b: str = "foo"

    def topography_implementation(self, analysis, progress_recorder=None, timer=None):
        topography = analysis.subject
        if timer is None:
            timer = Timer("test_implementation")
        if progress_recorder:
            progress_recorder.set_progress(1, 2, "Hello from the test topography workflow!")
        with timer("save_file1"):
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
        with timer("save_file2"):
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
        result = {
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
        store_split_dict(analysis.folder, RESULT_FILE_BASENAME, result)

    def surface_implementation(self, analysis, progress_recorder=None, timer=None):
        surface = analysis.subject
        if progress_recorder:
            progress_recorder.set_progress(1, 2, "Hello from the test surface workflow!")
        result = {
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
        store_split_dict(analysis.folder, RESULT_FILE_BASENAME, result)

    def tag_implementation(self, analysis, progress_recorder=None, timer=None):
        tag = analysis.subject
        tag.authorize_user(permissions=analysis.permissions)
        name = (
            f"Test result for test function called for tag {tag}, "
            ", which is built from surfaces {}".format(
                [s.name for s in tag.surface_set.all()]
            )
        )

        result = {
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
        store_split_dict(analysis.folder, RESULT_FILE_BASENAME, result)


class TopographyOnlyTestImplementation(TestImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.testing.topography_only_test"
        display_name = "Topography-only test implementation"

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
        timer=None,
    ):
        dep1 = dependencies["dep1"]
        result = {
            "name": "Test with dependencies",
            "result_from_dep": dep1.result["xunit"],
        }
        store_split_dict(analysis.folder, RESULT_FILE_BASENAME, result)


class TestImplementationWithError(WorkflowImplementation):
    """
    This function will be registered in conftest.py by a fixture. The arguments have no
    meaning. Result are two series.
    """

    class Meta:
        name = "topobank.testing.test_error"
        display_name = "Test implementation with error"

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
        timer=None,
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
        timer=None,
    ):
        return


class TestResultSchema(pydantic.BaseModel):
    """Result schema for TestImplementationWithOutputs."""

    predicted_value: float
    predicted_error: float
    confidence: float = 0.95


class TestMetadataSchema(pydantic.BaseModel):
    """Metadata schema for TestImplementationWithOutputs."""

    model_name: str
    version: int


@register_implementation
class TestImplementationWithOutputs(WorkflowImplementation):
    """
    Test implementation that declares output schemas.
    Used for testing the Outputs class functionality.
    """

    class Meta:
        name = "topobank.testing.test_with_outputs"
        display_name = "Test implementation with outputs"

        implementations = {
            Topography: "topography_implementation",
        }

    class Parameters(WorkflowImplementation.Parameters):
        model_id: int = 0

    class Outputs:
        result = TestResultSchema
        files = {
            "model.nc": OutputFile(
                file_type="netcdf",
                description="Trained model in NetCDF format",
            ),
            "metadata.json": OutputFile(
                file_type="json",
                description="Model metadata",
                schema=TestMetadataSchema,
                optional=True,
            ),
        }

    def topography_implementation(self, analysis, progress_recorder=None, timer=None):
        result = {
            "predicted_value": 1.5,
            "predicted_error": 0.1,
            "confidence": 0.95,
        }
        store_split_dict(analysis.folder, RESULT_FILE_BASENAME, result)


class TestImplementationWithIntegerKeys(WorkflowImplementation):
    """
    Test implementation that uses integer keys in dependencies.
    This mimics workflows like sds-ml that use surface.id as dependency keys.
    Used for testing that integer keys survive JSON serialization/deserialization.
    """

    class Meta:
        name = "topobank.testing.test_integer_keys"
        display_name = "Test implementation with integer keys"

        implementations = {
            Topography: "topography_implementation",
        }

        dependencies = {Topography: "topography_dependencies"}

    class Parameters(WorkflowImplementation.Parameters):
        value: int = 42

    def topography_dependencies(self, analysis) -> Dict[int, WorkflowDefinition]:
        """Return dependencies with integer keys (topography.id)."""
        topography = analysis.subject
        return {
            topography.id: WorkflowDefinition(
                subject=topography,
                function=Workflow.objects.get(name="topobank.testing.test"),
                kwargs=dict(a=self._kwargs.value),
            ),
        }

    def topography_implementation(
        self,
        analysis,
        dependencies: Dict = {},
        progress_recorder=None,
        timer=None,
    ):
        """Access dependency using integer key (topography.id)."""
        topography = analysis.subject
        # This will raise KeyError if integer keys were converted to strings
        dep = dependencies[topography.id]
        result = {
            "name": "Test with integer key dependencies",
            "result_from_dep": dep.result["xunit"],
            "topography_id": topography.id,
        }
        store_split_dict(analysis.folder, RESULT_FILE_BASENAME, result)
