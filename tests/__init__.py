from topobank.analysis.registry import register_implementation
from topobank.testing.workflows import (
    SecondTestImplementation,
    TestImplementation,
    TestImplementationWithError,
    TestImplementationWithErrorInDependency,
    TestImplementationWithIntegerKeys,
    TopographyOnlyTestImplementation,
)

register_implementation(SecondTestImplementation)
register_implementation(TestImplementation)
register_implementation(TestImplementationWithError)
register_implementation(TestImplementationWithErrorInDependency)
register_implementation(TestImplementationWithIntegerKeys)
register_implementation(TopographyOnlyTestImplementation)
