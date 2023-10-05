from rest_framework import serializers

from .models import User


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ['url', 'id', 'name', 'username']

    url = serializers.HyperlinkedIdentityField(view_name='users:user-api-detail', read_only=True)

