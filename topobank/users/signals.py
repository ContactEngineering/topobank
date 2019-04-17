
from allauth.account.signals import user_signed_up
from django.dispatch import receiver
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files import File

import os.path
import yaml

from topobank.manager.models import Surface, Topography

@receiver(user_signed_up)
def create_example_surface(sender, **kwargs):

    user = kwargs['user']

    example_info_fn = staticfiles_storage.path('data/example_surface.yaml')
    example_info = yaml.safe_load(open(example_info_fn))

    #
    # Create surface
    #
    surface = Surface.objects.create(user=user, name=example_info['name'],
                                     description=example_info['description'])

    #
    # Create topographies and trigger analyses
    #
    for topo_info in example_info['topographies']:

        topo_kwargs = topo_info.copy()
        del topo_kwargs['static_filename']

        # TODO this is a workaround for GH 132 - maybe we don't need to make sizes fixed?
        topo_kwargs['size_editable'] = True

        # TODO Workaround, maybe we don't need height scale restriction
        topo_kwargs['height_scale_editable'] = True

        topo = Topography(surface=surface, **topo_kwargs)

        abs_fn = staticfiles_storage.path(topo_info['static_filename'])
        file = open(abs_fn, 'rb') # we need binary mode for boto3 (S3 library)

        topo.datafile.save(os.path.basename(abs_fn), File(file))

        topo.save()

        topo.submit_automated_analyses()






