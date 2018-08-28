
import numpy as np

from PyCo.Surface import FromFile
from PyCo.Surface.SurfaceDescription import ScaledSurface, DetrendedSurface

DEFAULT_DATASOURCE_NAME = 'Default'
UNIT_TO_METERS = {'A': 1e-10, 'nm': 1e-9, 'µm': 1e-6, 'mm': 1e-3, 'm': 1.0,
                  'unknown': 1.0}



class TopographyFile:
    """Provide a simple generic interface to topography files independent of format."""

    def __init__(self, fname):

        self._fmt = FromFile.detect_format(fname)
        raw_surfaces = FromFile.read(fname, self._fmt)
        # we are relying here on a fixed order everytime the same file is read

        #
        # read() may return only one surface if there is only one
        #
        if not isinstance(raw_surfaces, list):
            raw_surfaces = [raw_surfaces]

        surfaces = [] # filtered surfaces
        # ignore all surfaces which have other units than lenghts
        # code taken from PyCo-web
        for surface in raw_surfaces:
            if type(surface.unit) is not tuple:
                # If this is not a tuple, that x-, y- and z-units are all
                # lengths. Discard all other channels.
                if not isinstance(surface, ScaledSurface):
                    surface = ScaledSurface(surface, 1.0)
                surfaces += [DetrendedSurface(surface, detrend_mode='height')]
        self._surfaces = surfaces


    @property
    def data_sources(self):
        """Return list of data source strings from surface infos."""
        return [ s.info['data_source'] if 'data_source' in s.info else DEFAULT_DATASOURCE_NAME
                 for s in self._surfaces ]

    def surface(self, data_source):
        """Get ScaledSurface instance based on data_source.

        :param data_source: integer
        :return: PyCo.Surface.SurfaceDescription.ScaledSurface
        """

        return self._surfaces[data_source]


def optimal_unit(length, unit='m'): # TODO write unit tests
    """
    Return a unit and a scale factor that minimizes the display width of a
    length.
    """
    if unit is None:
        return 'unknown', 1
    unit_fac = UNIT_TO_METERS[unit]
    if unit_fac is None:
        return unit, 1

    # Convert length to meters
    length = np.mean(length)*unit_fac

    # Length is meters now
    new_unit = 'm'
    conversion_factor = unit_fac / UNIT_TO_METERS['m']
    for name, meters in sorted(UNIT_TO_METERS.items(), key=lambda x: x[1]):
        if meters is not None and length > 1.1*meters:
            new_unit = name
            conversion_factor = unit_fac/meters

    return new_unit, conversion_factor
