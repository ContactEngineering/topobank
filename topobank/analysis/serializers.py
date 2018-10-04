import pickle

from rest_framework import serializers

from .models import Analysis


class PickledResult(serializers.DictField):
    def to_representation(self, value):
        return super().to_representation(pickle.loads(value))


class AnalysisSerializer(serializers.ModelSerializer):
    topography_name = serializers.CharField(source='topography.name')
    result = PickledResult()

    class Meta:
        model = Analysis
        fields = ('id', 'task_id', 'task_state', 'start_time', 'end_time', 'result',
                  'topography', 'topography_name')
