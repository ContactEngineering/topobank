import pickle

from rest_framework import serializers

from .models import Analysis


class PickledResult(serializers.DictField):
    def to_representation(self, value):
        return super().to_representation(pickle.loads(value))


class AnalysisSerializer(serializers.ModelSerializer):
    result = PickledResult()

    class Meta:
        model = Analysis
        fields = ('id', 'task_id', 'task_state', 'result')
