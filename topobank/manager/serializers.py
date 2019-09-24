from rest_framework import serializers

from .models import Surface, Topography

class TopographySerializer(serializers.HyperlinkedModelSerializer):

    #
    # we could use a custom "ListSerializer" in order to
    # minimize the number of call when finding whether an instance is selected or not.

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
    )
    class Meta:
        model = Topography
        fields = ['pk', 'name', 'creator', 'description']


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

    class Meta:
        model = Surface
        fields = ['pk', 'name', 'creator', 'description', 'category', 'topographies']


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
