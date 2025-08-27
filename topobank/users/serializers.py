from rest_framework import serializers
from rest_framework.reverse import reverse

from ..supplib.serializers import StrictFieldMixin
from .models import ORCIDException, User


class UserSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = [
            # Self
            'url',
            'id',
            # Auxiliary API endpoints
            'api',
            # Model fields
            'name',
            'username',
            'orcid',
            'email',
            'date_joined'
        ]
        read_only_fields = ['id', 'date_joined']

    url = serializers.HyperlinkedIdentityField(view_name='users:user-v1-detail', read_only=True)
    api = serializers.SerializerMethodField()
    orcid = serializers.SerializerMethodField()

    def get_api(self, obj: User) -> dict:
        return {
            "add_organization": reverse(
                "users:add-organization-v1",
                kwargs={"pk": obj.id},
                request=self.context["request"],
            ),
            "remove_organization": reverse(
                "users:remove-organization-v1",
                kwargs={"pk": obj.id},
                request=self.context["request"],
            )
        }

    def get_orcid(self, obj: User) -> str:
        try:
            return obj.orcid_id
        except ORCIDException:
            return None
