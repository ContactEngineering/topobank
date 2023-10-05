from rest_framework import serializers

from .models import User


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ['url', 'id', 'name', 'username', 'orcid']

    url = serializers.HyperlinkedIdentityField(view_name='users:user-api-detail', read_only=True)
    orcid = serializers.SerializerMethodField()

    def get_orcid(self, obj):
        return obj.orcid_id

