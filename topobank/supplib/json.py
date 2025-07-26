import numpy as np
import xarray
from django.core.serializers.json import DjangoJSONEncoder

try:
    from jaxlib.xla_extension import ArrayImpl
except ModuleNotFoundError:
    ArrayImpl = np.ndarray


def nan_to_none(obj):
    if isinstance(obj, dict):
        return {k: nan_to_none(v) for k, v in obj.items()}
    elif isinstance(obj, list) or isinstance(obj, set):
        return [nan_to_none(v) for v in obj]
    elif isinstance(obj, np.ma.MaskedArray):
        if obj.ndim == 0:
            return None if obj.mask else nan_to_none(obj.item())
        else:
            return [nan_to_none(v) for v in obj]
    elif (
        isinstance(obj, np.ndarray)
        or isinstance(obj, xarray.DataArray)
        or isinstance(obj, ArrayImpl)
    ):
        if obj.ndim == 0:
            return nan_to_none(obj.item())
        else:
            return [nan_to_none(v) for v in obj]
    elif isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


def none_to_nan(obj):
    if isinstance(obj, dict):
        return {k: none_to_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list) or isinstance(obj, set):
        return [none_to_nan(v) for v in obj]
    elif obj is None:
        return np.nan
    return obj


class ExtendedJSONEncoder(DjangoJSONEncoder):
    """
    Customized JSON encoder that gracefully handles:
    * numpy arrays, which will be converted to JSON arrays
    * NaNs and Infs, which will be converted to null
    * numpy masked arrays, which will be converted to JSON arrays
      with masked values converted to null
    """

    _TYPE_MAP = {
        np.int_: int,
        np.intc: int,
        np.intp: int,
        np.int8: int,
        np.int16: int,
        np.int32: int,
        np.int64: int,
        np.uint8: int,
        np.uint16: int,
        np.uint32: int,
        np.uint64: int,
        np.float16: float,
        np.float32: float,
        np.float64: float,
        np.bool_: bool,
        np.ndarray: nan_to_none,
        np.ma.MaskedArray: nan_to_none,
        xarray.DataArray: nan_to_none,
    }

    def default(self, obj):
        try:
            return self._TYPE_MAP[type(obj)](obj)
        except KeyError:
            # Pass it on the Django encoder
            return super().default(obj)

    def encode(self, obj, *args, **kwargs):
        # Solution suggested here:
        # https://stackoverflow.com/questions/28639953/python-json-encoder-convert-nans-to-null-instead
        obj = nan_to_none(obj)
        return super().encode(obj, *args, **kwargs)
