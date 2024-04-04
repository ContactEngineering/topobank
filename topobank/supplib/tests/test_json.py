import json

import jax.numpy as jnp
import numpy as np

from ..json import ExtendedJSONEncoder


def test_json_encoder():
    d = {
        'a': 1,
        'b': np.int64(2),
        'c': np.array([1, 2, 3], dtype=np.int64),
        'd': [1, 2, 4],
        'e': np.nan,
        'f': np.array([5, 6, np.nan]),
        'g': set([3, 4, 4]),
        'h': jnp.array([11, 12, 13], dtype=np.int64),
        'i': jnp.array([11, np.nan, 13]),
    }

    s = json.dumps(d, cls=ExtendedJSONEncoder)

    assert s == ('{"a": 1, "b": 2, "c": [1, 2, 3], "d": [1, 2, 4], "e": null, "f": [5.0, 6.0, null], "g": [3, 4], '
                 '"h": [11, 12, 13], "i": [11.0, null, 13.0]}')
