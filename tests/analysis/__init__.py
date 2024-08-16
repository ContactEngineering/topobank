from topobank.analysis.functions import (
    VIZ_SERIES,
    surface_analysis_function_for_tests,
    tag_analysis_function_for_tests,
    topography_analysis_function_for_tests
)
from topobank.analysis.registry import register_implementation
from topobank.analysis.urls import app_name

register_implementation(app_name, VIZ_SERIES, 'test')(tag_analysis_function_for_tests)
register_implementation(app_name, VIZ_SERIES, 'test')(surface_analysis_function_for_tests)
register_implementation(app_name, VIZ_SERIES, 'test')(topography_analysis_function_for_tests)
