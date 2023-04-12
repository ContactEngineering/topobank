import numpy as np

from django.core.serializers.json import DjangoJSONEncoder


class ExtendedJSONEncoder(DjangoJSONEncoder):
    """
    Customized JSON encoder that gracefully handles:
    * numpy arrays
    * NaNs
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
            return super().default(self, obj)
