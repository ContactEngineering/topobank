from django.shortcuts import reverse

from rest_framework import serializers
from guardian.shortcuts import get_perms

import logging

from .models import Surface, Topography

_log = logging.getLogger(__name__)

class TopographySerializer(serializers.HyperlinkedModelSerializer):

    #
    # we could use a custom "ListSerializer" in order to
    # minimize the number of call when finding whether an instance is selected or not.

    title = serializers.CharField(source='name')

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
    )

    urls = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    folder = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    def get_urls(self, obj):
        """Return only those urls which are usable for the usser

        :param obj: topography object
        :return: dict with { url_name: url }
        """
        user = self.context['request'].user
        surface = obj.surface

        perms = get_perms(user, surface)

        urls = {
            'select': reverse('manager:topography-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:topography-unselect', kwargs=dict(pk=obj.pk))
        }

        if 'view_surface' in perms:
            urls['detail'] = reverse('manager:topography-detail', kwargs=dict(pk=obj.pk))
            urls['show_analyses'] = reverse('manager:topography-show-analyses', kwargs=dict(topography_id=obj.pk))

        if 'change_surface' in perms:
            urls.update({
                'update': reverse('manager:topography-update', kwargs=dict(pk=obj.pk))
            })

        if 'delete_surface' in perms:
            urls['delete'] = reverse('manager:topography-delete', kwargs=dict(pk=obj.pk))

        return urls

    def get_selected(self, obj):
        topographies, surfaces = self.context['selected_instances']
        return (obj in topographies) or (obj.surface in surfaces)

    def get_key(self, obj):
        return f"topography-{obj.pk}"

    def get_folder(self, obj):
        return False

    def get_tags(self, obj):  # TODO prove if own method needed
        return [t.name for t in obj.tags.all()]

    class Meta:
        model = Topography
        fields = ['pk', 'name', 'creator', 'description', 'tags',
                  'urls', 'selected',
                  'key', 'title', 'folder']


class SurfaceSerializer(serializers.HyperlinkedModelSerializer):

    #
    # we could use a custom "ListSerializer" in order to
    # minimize the number of call when finding whether an instance is selected or not.

    title = serializers.CharField(source='name')
    children = TopographySerializer(source='topography_set', many=True)

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
    )

    urls = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    folder = serializers.SerializerMethodField()
    sharing_status = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    def get_urls(self, obj):

        user = self.context['request'].user
        perms = get_perms(user, obj)

        urls =  {
            'select': reverse('manager:surface-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:surface-unselect', kwargs=dict(pk=obj.pk))
        }
        if 'view_surface' in perms:
            urls['detail'] = reverse('manager:surface-detail', kwargs=dict(pk=obj.pk))
            if obj.num_topographies() > 0:
                urls.update({
                    'show_analyses': reverse('manager:surface-show-analyses', kwargs=dict(surface_id=obj.id)),
                    'download': reverse('manager:surface-download', kwargs=dict(surface_id=obj.id)),

                })
        if 'change_surface' in perms:
            urls.update({
                'add_topography': reverse('manager:topography-create', kwargs=dict(surface_id=obj.id)),
                'update': reverse('manager:surface-update', kwargs=dict(pk=obj.pk)),
            })
        if 'delete_surface' in perms:
            urls.update({
                'delete': reverse('manager:surface-delete', kwargs=dict(pk=obj.pk)),
            })
        if 'share_surface' in perms:
            urls.update({
                'share': reverse('manager:surface-share', kwargs=dict(pk=obj.pk)),
            })

        return urls

    def get_selected(self, obj):
        topographies, surfaces  = self.context['selected_instances']
        # _log.info("Surface selected? %s in %s?", obj, surfaces)
        return obj in surfaces

    def get_key(self, obj):
        return f"surface-{obj.pk}"

    def get_sharing_status(self, obj):
        user = self.context['request'].user
        if user == obj.creator:
            return "own"
        else:
            return "shared"

    def get_folder(self, obj):
        return True

    def get_tags(self, obj): # TODO prove if own method needed
        return [ t.name for t in obj.tags.all()]

    class Meta:
        model = Surface
        fields = ['pk', 'name', 'creator', 'description', 'category', 'tags', 'children',
                  'sharing_status', 'urls', 'selected', 'key', 'title', 'folder']

