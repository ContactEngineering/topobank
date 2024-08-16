import json

import numpy as np

try:
    import jax.numpy as jnp
except ModuleNotFoundError:
    jnp = np

from topobank.supplib.json import ExtendedJSONEncoder


def test_json_encoder():
    d = {
        "a": 1,
        "b": np.int64(2),
        "c": np.array([1, 2, 3], dtype=np.int64),
        "d": [1, 2, 4],
        "e": np.nan,
        "f": np.array([5, 6, np.nan]),
        "g": set([3, 4, 4]),
        "h": jnp.array([11, 12, 13], dtype=np.int64),
        "i": jnp.array([11, np.nan, 13]),
        "j": jnp.array([np.nan, np.nan, np.nan]),
    }

    s = json.dumps(d, cls=ExtendedJSONEncoder)

    assert s == (
        '{"a": 1, "b": 2, "c": [1, 2, 3], "d": [1, 2, 4], "e": null, "f": [5.0, 6.0, null], "g": [3, 4], '
        '"h": [11, 12, 13], "i": [11.0, null, 13.0], "j": [null, null, null]}'
    )


def test_used_json_encoder_with_nan():
    data = {"x": np.array([np.nan, np.nan])}
    encoded_data = json.dumps(data, cls=ExtendedJSONEncoder)
    assert "null" in encoded_data
