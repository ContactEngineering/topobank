from django.db import models
from django.urls import reverse

import uuid


class Publication(models.Model):

    LICENSE_CHOICES = [
        ('cc0-1.0', 'CC0 (Public Domain Dedication)'),
        # https://creativecommons.org/publicdomain/zero/1.0/
        ('ccby-4.0', 'CC BY 4.0'),
        # https://creativecommons.org/licenses/by/4.0/
        ('ccbysa-4.0', 'CC BY-SA 4.0'),
        # https://creativecommons.org/licenses/by-sa/4.0/
    ]

    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    surface = models.OneToOneField("manager.Surface", on_delete=models.PROTECT, related_name='publication')
    original_surface = models.ForeignKey("manager.Surface", on_delete=models.SET_NULL,
                                         null=True, related_name='derived_publications')
    publisher = models.ForeignKey("users.User", on_delete=models.PROTECT)
    version = models.PositiveIntegerField(default=1)
    datetime = models.DateTimeField(auto_now_add=True)
    license = models.CharField(max_length=12, choices=LICENSE_CHOICES, blank=False, default='')

    def get_absolute_url(self):
        return reverse('publication:go', args=[self.uuid])

