from ..functions import (
    VIZ_SERIES,
    surface_analysis_function_for_tests,
    surfacecollection_analysis_function_for_tests,
    topography_analysis_function_for_tests
)
from ..registry import register_implementation
from ..urls import app_name

register_implementation(app_name, VIZ_SERIES, 'test')(surfacecollection_analysis_function_for_tests)
register_implementation(app_name, VIZ_SERIES, 'test')(surface_analysis_function_for_tests)
register_implementation(app_name, VIZ_SERIES, 'test')(topography_analysis_function_for_tests)
