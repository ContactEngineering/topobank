from topobank.analysis.functions import (
    SecondTestImplementation,
    TestImplementation,
    TopographyOnlyTestImplementation,
)
from topobank.analysis.registry import register_implementation

register_implementation(TestImplementation)
register_implementation(TopographyOnlyTestImplementation)
register_implementation(SecondTestImplementation)
