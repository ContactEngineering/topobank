from topobank.analysis.functions import (
    SecondTestImplementation,
    TestImplementation,
    TestImplementationWithError,
    TopographyOnlyTestImplementation,
)
from topobank.analysis.registry import register_implementation

register_implementation(TestImplementation)
register_implementation(TopographyOnlyTestImplementation)
register_implementation(SecondTestImplementation)
register_implementation(TestImplementationWithError)
