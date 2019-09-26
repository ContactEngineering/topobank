from django.shortcuts import reverse
from rest_framework import serializers
import logging

from .models import Surface, Topography

_log = logging.getLogger(__name__)

class TopographySerializer(serializers.HyperlinkedModelSerializer):

    #
    # we could use a custom "ListSerializer" in order to
    # minimize the number of call when finding whether an instance is selected or not.


    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
    )

    is_selected = serializers.SerializerMethodField()
    def get_is_selected(self, obj):
        topographies, surfaces = self.context['selected_instances']
        # _log.info("Topography selected? %s in %s? %s in %s?", obj, topographies, obj.surface, surfaces)
        return (obj in topographies) or (obj.surface in surfaces)

    class Meta:
        model = Topography
        fields = ['pk', 'name', 'creator', 'description', 'is_selected']


class SurfaceSerializer(serializers.HyperlinkedModelSerializer):

    #
    # we could use a custom "ListSerializer" in order to
    # minimize the number of call when finding whether an instance is selected or not.

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
    )

    topographies = TopographySerializer(source='topography_set', many=True)

    select_url = serializers.SerializerMethodField()
    unselect_url = serializers.SerializerMethodField()
    is_selected = serializers.SerializerMethodField()

    def get_select_url(self, obj):
        return reverse('manager:surface-select', kwargs=dict(pk=obj.pk))

    def get_unselect_url(self, obj):
        return reverse('manager:surface-unselect', kwargs=dict(pk=obj.pk))

    def get_is_selected(self, obj):
        topographies, surfaces  = self.context['selected_instances']
        # _log.info("Surface selected? %s in %s?", obj, surfaces)
        return obj in surfaces

    class Meta:
        model = Surface
        fields = ['pk', 'name', 'creator', 'description', 'category', 'topographies',
                  'select_url', 'unselect_url', 'is_selected']


# class SearchResult(object):
#
#     def __init__(self, surfaces, topographies):
#         self._surfaces = surfaces
#         self._topographies = topographies
#
#
#
# class SeachResultSerializer(serializers.Serializer):
#
#     surfaces = serializers.RelatedField
#
#
