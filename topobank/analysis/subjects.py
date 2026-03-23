"""Subject resolution - Django models to native objects.

This module handles converting Django model instances (Topography, Surface, Tag)
to native SurfaceTopography objects that workflow implementations can use.
"""

from typing import Any, Tuple, Union

from topobank.manager.models import Surface, Tag, Topography


class ContainerProxy:
    """Proxy that iterates Django topographies as SurfaceTopography objects.

    This allows Surface workflows to iterate over native SurfaceTopography
    objects without loading all data upfront.
    """

    def __init__(self, queryset):
        self._queryset = queryset

    def __len__(self):
        return self._queryset.count()

    def __iter__(self):
        for topo in self._queryset:
            yield topo.topography()


def resolve_subject(django_subject: Union[Topography, Surface, Tag]) -> Any:
    """Convert Django model to native SurfaceTopography object(s).

    Parameters
    ----------
    django_subject : Topography, Surface, Tag, or duck-typed object
        The Django model instance or any object with a topography() method.

    Returns
    -------
    Any
        For Topography: a SurfaceTopography object
        For Surface: a ContainerProxy yielding SurfaceTopography objects
        For Tag: a ContainerProxy yielding SurfaceTopography objects from all surfaces
        For duck-typed objects: result of calling topography()

    Raises
    ------
    TypeError
        If the subject type is not recognized and has no topography() method.
    """
    if isinstance(django_subject, Topography):
        return django_subject.topography()
    elif isinstance(django_subject, Surface):
        return ContainerProxy(django_subject.topography_set.all())
    elif isinstance(django_subject, Tag):
        # Tags contain surfaces - flatten to all topographies
        topographies = Topography.objects.filter(surface__tags=django_subject)
        return ContainerProxy(topographies)
    elif hasattr(django_subject, 'topography'):
        # Duck typing: support any object with a topography() method
        # This handles test mocks like FakeTopographyModel
        return django_subject.topography()
    else:
        raise TypeError(f"Unknown subject type: {type(django_subject)}")


def get_subject_metadata(django_subject: Union[Topography, Surface, Tag]) -> Tuple[str, str]:
    """Get display name and URL for a subject.

    Parameters
    ----------
    django_subject : Topography, Surface, or Tag
        The Django model instance.

    Returns
    -------
    tuple[str, str]
        (name, url) tuple for the subject. URL may be empty if not available.
    """
    name = django_subject.name
    if hasattr(django_subject, 'get_absolute_url'):
        url = django_subject.get_absolute_url()
    else:
        url = ""
    return name, url
