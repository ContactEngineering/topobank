import numpy as np
from django.core.serializers.json import DjangoJSONEncoder


def nan_to_none(obj):
    if isinstance(obj, dict):
        return {k: nan_to_none(v) for k, v in obj.items()}
    elif isinstance(obj, list) or isinstance(obj, set) or isinstance(obj, np.ndarray):
        return [nan_to_none(v) for v in obj]
    elif isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


class ExtendedJSONEncoder(DjangoJSONEncoder):
    """
    Customized JSON encoder that gracefully handles:
    * numpy arrays, which will be converted to JSON arrays
    * NaNs and Infs, which will be converted to null
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
        np.float_: float,
        np.float16: float,
        np.float32: float,
        np.float64: float,
        np.bool_: bool
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


try:
    from jaxlib.xla_extension import ArrayImpl
    ExtendedJSONEncoder._TYPE_MAP[ArrayImpl] = lambda obj: obj.tolist()
except ModuleNotFoundError:
    pass
