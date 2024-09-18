from topobank.analysis.functions import (
    SecondTestImplementation,
    TestImplementation,
    TestImplementationWithError,
    TestImplementationWithErrorInDependency,
    TopographyOnlyTestImplementation,
)
from topobank.analysis.registry import register_implementation

register_implementation(SecondTestImplementation)
register_implementation(TestImplementation)
register_implementation(TestImplementationWithError)
register_implementation(TestImplementationWithErrorInDependency)
register_implementation(TopographyOnlyTestImplementation)
