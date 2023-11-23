from rest_framework import serializers

from ..users.serializers import UserSerializer

from .models import Publication, CITATION_FORMAT_FLAVORS


class PublicationSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Publication
        fields = ['url',
                  'id',
                  'short_url',
                  'surface',
                  'original_surface',
                  'publisher',
                  'publisher_orcid_id',
                  'version',
                  'datetime',
                  'license',
                  'authors_json',
                  'datacite_json',
                  'container',
                  'doi_name',
                  'doi_state',
                  'citation',
                  'has_access_to_original_surface']

    url = serializers.HyperlinkedIdentityField(view_name='publication:publication-api-detail', read_only=True)
    surface = serializers.HyperlinkedRelatedField(view_name='manager:surface-api-detail', read_only=True)
    original_surface = serializers.HyperlinkedRelatedField(view_name='manager:surface-api-detail', read_only=True)
    publisher = UserSerializer(read_only=True)
    citation = serializers.SerializerMethodField()
    has_access_to_original_surface = serializers.SerializerMethodField()

    def get_citation(self, obj):
        d = {}
        for flavor in CITATION_FORMAT_FLAVORS:
            d[flavor] = obj.get_citation(flavor)
        return d

    def get_has_access_to_original_surface(self, obj):
        return self.context['request'].user.has_perm('view_surface', obj.original_surface)
