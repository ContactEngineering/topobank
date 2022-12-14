from django.db.models.signals import pre_delete
from django.dispatch import receiver

# from topobank.organizations.signals import OrganizationFilteredSignal

import logging

from ..manager.utils import recursive_delete
from .models import Analysis

_log = logging.getLogger(__name__)


@receiver(pre_delete, sender=Analysis)
def remove_storage_files(sender, instance, **kwargs):
    recursive_delete(instance.storage_prefix)

# register_analysis_function_implementation = OrganizationFilteredSignal()

# analysis_function_names = OrganizationFilteredSignal()




