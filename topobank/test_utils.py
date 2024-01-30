"""Tests for utils module on topobank level"""

import json

import numpy as np
from django.core.files.storage import default_storage

from topobank.supplib.json import ExtendedJSONEncoder

from .utils import SplitDictionaryHere, load_split_dict, store_split_dict


def test_used_json_encoder_with_nan():
    data = {'x': np.array([np.nan, np.nan])}
    encoded_data = json.dumps(data, cls=ExtendedJSONEncoder)
    assert 'null' in encoded_data


def test_store_split_dict_with_supplementary():
    storage_prefix = "test"

    series_0 = SplitDictionaryHere("series-0", {
        "x": [1, 2, 3],
        "y": np.array([2, 4, 6]),
    }, supplementary=dict(extra_info="This is some supplementary data"))

    result_dict = {
        "name": "Test result",
        "series": [series_0],
    }

    store_split_dict(storage_prefix, "result", result_dict)

    # The supplementary data should be part of the top level dict in the split version
    split_result_json_file = default_storage.open(f"{storage_prefix}/result.json")
    split_result = json.load(split_result_json_file)
    assert split_result['series'][0]['extra_info'] == "This is some supplementary data"

    # .. but should not be included in the result
    result_from_storage = load_split_dict(storage_prefix, "result")
    assert "extra_info" not in result_from_storage


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
    assert b'null' in series_0_json_file.read()

    #
    # Also check whether load_split_dict can reproduce the result
    #
    result_from_storage = load_split_dict(storage_prefix, "result")
    assert result_from_storage['name'] == result_dict['name']
    assert np.array_equal(result_from_storage['series'][0]['x'], series_0.dict['x'])
    y = [np.nan if _y is None else _y for _y in result_from_storage['series'][0]['y']]  # np.nans will be read as None
    assert np.array_equal(y, series_0.dict['y'], equal_nan=True)
