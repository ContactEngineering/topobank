from rest_framework import serializers

from ..supplib.serializers import StrictFieldMixin
from .models import ORCIDException, User


class UserSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ['url', 'id', 'name', 'username', 'orcid']

    url = serializers.HyperlinkedIdentityField(view_name='users:user-api-detail', read_only=True)
    orcid = serializers.SerializerMethodField()

    def get_orcid(self, obj):
        try:
            return obj.orcid_id
        except ORCIDException:
            return None
