from django.apps import AppConfig


class MeasurementsAppConfig(AppConfig):
    name = "topobank.measurements"
    label = "measurements"
    verbose_name = "Measurement types"

    def ready(self):
        # Importing the module registers the built-in types through the
        # `register_measurement_type` decorator.
        from . import types  # noqa: F401
        from .registry import load_entry_points

        # Types shipped by external packages. Registered after the built-ins so a
        # plugin cannot shadow one of them; `register_measurement_type` raises on a
        # duplicate kind.
        load_entry_points()
