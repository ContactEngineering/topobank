import json

import numpy as np
import xarray
from pydantic import BaseModel

try:
    import jax.numpy as jnp
except ModuleNotFoundError:
    jnp = np

from topobank.supplib.json import ExtendedJSONEncoder


class SampleModel(BaseModel):
    name: str
    value: int


class NestedModel(BaseModel):
    inner: SampleModel
    items: list[int]


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
        "k": np.ma.masked_invalid(np.array([14, np.nan, 15], dtype=np.float64)),
        "l": xarray.DataArray(data=[16, 17, np.nan], dims=["x"]),
    }

    s = json.dumps(d, cls=ExtendedJSONEncoder)

    assert s == (
        '{"a": 1, "b": 2, "c": [1, 2, 3], "d": [1, 2, 4], "e": null, '
        '"f": [5.0, 6.0, null], "g": [3, 4], "h": [11, 12, 13], '
        '"i": [11.0, null, 13.0], "j": [null, null, null], "k": [14.0, null, 15.0], '
        '"l": [16.0, 17.0, null]}'
    )


def test_used_json_encoder_with_nan():
    data = {"x": np.array([np.nan, np.nan])}
    encoded_data = json.dumps(data, cls=ExtendedJSONEncoder)
    assert "null" in encoded_data


def test_json_encoder_pydantic_model():
    """Test that Pydantic models are serialized via model_dump()."""
    model = SampleModel(name="test", value=42)
    result = json.dumps(model, cls=ExtendedJSONEncoder)
    assert result == '{"name": "test", "value": 42}'


def test_json_encoder_nested_pydantic_model():
    """Test that nested Pydantic models are serialized correctly."""
    model = NestedModel(inner=SampleModel(name="inner", value=1), items=[1, 2, 3])
    result = json.dumps(model, cls=ExtendedJSONEncoder)
    assert result == '{"inner": {"name": "inner", "value": 1}, "items": [1, 2, 3]}'


def test_json_encoder_pydantic_model_in_list():
    """Test that Pydantic models inside lists are serialized."""
    models = [SampleModel(name="a", value=1), SampleModel(name="b", value=2)]
    result = json.dumps(models, cls=ExtendedJSONEncoder)
    assert result == '[{"name": "a", "value": 1}, {"name": "b", "value": 2}]'


def test_json_encoder_pydantic_model_in_dict():
    """Test that Pydantic models inside dicts are serialized."""
    data = {"model": SampleModel(name="test", value=42), "other": "value"}
    result = json.dumps(data, cls=ExtendedJSONEncoder)
    assert result == '{"model": {"name": "test", "value": 42}, "other": "value"}'
