from django.db.models.signals import pre_delete
from django.dispatch import receiver
import shutil, os

from .models import Topography

@receiver(pre_delete, sender=Topography)
def remove_files(sender, instance, **kwargs):
    #
    # During the creation of the DZI files, many image files can be generated.
    # This method ensures that the files are removed when the
    # topography is removed.
    #
    if instance.dzi_file:

        dzi_path = instance.dzi_file.path
        files_path = dzi_path.replace('.dzi', '_files')
        shutil.rmtree(files_path)

        if os.path.exists(dzi_path):
            os.remove(dzi_path)

    if instance.image:
        image_path = instance.image.path
        if os.path.exists(image_path):
            os.remove(image_path)

    # TODO remove data file, if no longer needed (there could be other topographies using it)
