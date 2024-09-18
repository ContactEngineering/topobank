from topobank.analysis.registry import register_implementation
from topobank.testing.functions import (
    SecondTestImplementation,
    TestImplementation,
    TestImplementationWithError,
    TestImplementationWithErrorInDependency,
    TopographyOnlyTestImplementation,
)

register_implementation(SecondTestImplementation)
register_implementation(TestImplementation)
register_implementation(TestImplementationWithError)
register_implementation(TestImplementationWithErrorInDependency)
register_implementation(TopographyOnlyTestImplementation)
