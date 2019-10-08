from django.shortcuts import reverse
from rest_framework import serializers
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
    is_surface_selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    folder = serializers.SerializerMethodField()

    def get_urls(self, obj):
        return {
            'select': reverse('manager:topography-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:topography-unselect', kwargs=dict(pk=obj.pk)),
            'detail': reverse('manager:topography-detail', kwargs=dict(pk=obj.pk)),
        }

    def get_selected(self, obj):
        topographies, surfaces = self.context['selected_instances']
        return (obj in topographies) or (obj.surface in surfaces)

    def get_is_surface_selected(self, obj):
        topographies, surfaces = self.context['selected_instances']
        return obj.surface in surfaces

    def get_key(self, obj):
        return f"topography-{obj.pk}"

    def get_folder(self, obj):
        return False


    class Meta:
        model = Topography
        fields = ['pk', 'name', 'creator', 'description',
                  'urls', 'selected', 'is_surface_selected',
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

    topographies = TopographySerializer(source='topography_set', many=True)

    urls = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    folder = serializers.SerializerMethodField()
    sharing_status = serializers.SerializerMethodField()


    def get_urls(self, obj):
        return {
            'select': reverse('manager:surface-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:surface-unselect', kwargs=dict(pk=obj.pk)),
            'detail': reverse('manager:surface-detail', kwargs=dict(pk=obj.pk)),
        }

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


    class Meta:
        model = Surface
        fields = ['pk', 'name', 'creator', 'description', 'category', 'topographies',
                  'sharing_status', 'urls', 'selected', 'key', 'title', 'children', 'folder']

