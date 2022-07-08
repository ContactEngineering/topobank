"""Tests for utils module on topobank level"""

import json

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


def test_store_split_dict_with_supplementary():
    storage_prefix = "test"

    supplementary = {"suppl": "info"}
    series_0 = SplitDictionaryHere("series-0", {
        "x": [1, 2, 3],
        "y": np.array([5, 2, 11]),
    }, supplementary=supplementary)

    result_dict = {
        "name": "Test result",
        "series": [series_0],
    }

    store_split_dict(storage_prefix, "result", result_dict)

    #
    # Check whether load_split_dict can reproduce the result
    #
    result_from_storage = load_split_dict(storage_prefix, "result")
    assert result_from_storage['name'] == result_dict['name']
    assert np.array_equal(result_from_storage['series'][0]['x'], series_0.dict['x'])
    assert np.array_equal(result_from_storage['series'][0]['y'], series_0.dict['y'], equal_nan=True)

    #
    # The toplevel JSON should contain the supplementary information
    #
    toplevel_result_from_storage = json.load(default_storage.open(f'{storage_prefix}/result.json', 'r'))
    assert toplevel_result_from_storage['name'] == result_dict['name']
    print(toplevel_result_from_storage)
    series_0_from_storage = toplevel_result_from_storage['series']
    assert len(series_0_from_storage) == 1
    series_0_from_storage = series_0_from_storage[0]
    assert series_0_from_storage['__external__'] == 'series-0.json'
    for key, value in supplementary.items():
        assert series_0_from_storage[key] == supplementary[key]
    assert set(series_0_from_storage.keys()) == set(list(supplementary.keys()) + ['__external__'])
