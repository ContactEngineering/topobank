
from PyCo.Surface import FromFile
from PyCo.Surface.SurfaceDescription import ScaledSurface, DetrendedSurface

DEFAULT_DATASOURCE_NAME = 'Default'

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


