from topobank.analysis.functions import surface_analysis_function_for_tests, \
        surfacecollection_analysis_function_for_tests, \
        topography_analysis_function_for_tests, register_implementation, ART_SERIES

register_implementation(ART_SERIES, 'test')(surfacecollection_analysis_function_for_tests)
register_implementation(ART_SERIES, 'test')(surface_analysis_function_for_tests)
register_implementation(ART_SERIES, 'test')(topography_analysis_function_for_tests)
