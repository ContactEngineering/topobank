"""Tests for utils module on topobank level"""
from django.core.files.storage import default_storage

import numpy as np

from .utils import store_split_dict, load_split_dict, SplitDictionaryHere


def test_store_split_dict_with_nan():
    storage_prefix = "test"

    series_0 = SplitDictionaryHere("series-0", {
        "x": [1, 2, 3],
        "y": np.array([np.nan, 2, np.nan]),
    })

    result_dict = {
        "name": "Test result",
        "series": [series_0],
    }

    store_split_dict(storage_prefix, "result", result_dict)

    # In order to work with bokehjs, we cannot use `NaN` (without quotes)
    # as value in JSON, because than JSON.parse fails to load it.
    # So `NaN` should be represented as `"NaN"` which is JSON compatible and seems
    # to work with bokehjs
    series_0_json_file = default_storage.open(f"{storage_prefix}/series-0.json")
    assert b'"NaN"' in series_0_json_file.read()

    #
    # Also check whether load_split_dict can reproduce the result
    #
    result_from_storage = load_split_dict(storage_prefix, "result")
    assert result_from_storage['name'] == result_dict['name']
    assert np.array_equal(result_from_storage['series'][0]['x'], series_0.dict['x'])
    assert np.array_equal(result_from_storage['series'][0]['y'], series_0.dict['y'], equal_nan=True)






