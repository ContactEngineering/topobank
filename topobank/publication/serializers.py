from rest_framework import serializers

from .models import Publication


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
                  'doi_state']

    url = serializers.HyperlinkedIdentityField(view_name='publication:publication-api-detail', read_only=True)
    surface = serializers.HyperlinkedRelatedField(view_name='manager:surface-api-detail', read_only=True)
    original_surface = serializers.HyperlinkedRelatedField(view_name='manager:surface-api-detail', read_only=True)
    publisher = serializers.HyperlinkedRelatedField(view_name='users:user-api-detail', read_only=True)
