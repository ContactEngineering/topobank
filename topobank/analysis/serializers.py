from rest_framework import serializers

from .models import Analysis

class SnippetSerializer(serializers.Serializer):
    class Meta:
        model = Analyis
        fields = ('id', 'successful', 'failed')

