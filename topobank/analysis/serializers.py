import logging
import pickle

from django.shortcuts import reverse

from rest_framework import serializers

from generic_relations.relations import GenericRelatedField

from ..manager.models import Surface, Topography
from ..manager.serializers import SurfaceSerializer, TopographySerializer
from .models import Analysis

_log = logging.getLogger(__name__)


class AnalysisSerializer(serializers.ModelSerializer):
    duration = serializers.SerializerMethodField()
    kwargs = serializers.SerializerMethodField()
    subject = GenericRelatedField({
        Surface: SurfaceSerializer(),
        Topography: TopographySerializer()
    })
    task_progress = serializers.SerializerMethodField()
    urls = serializers.SerializerMethodField()

    def get_duration(self, obj):
        return obj.duration

    def get_kwargs(self, obj):
        return pickle.loads(obj.kwargs)

    def get_task_progress(self, obj):
        if obj.task_state == 'ru':
            return obj.get_task_progress()
        elif obj.task_state == 'su':
            return 1.0
        else:
            return 0.0

    def get_urls(self, obj):
        return {
            'status': reverse('analysis:status-detail', kwargs=dict(pk=obj.id))
        }

    class Meta:
        model = Analysis
        fields = ['id', 'function', 'subject', 'kwargs', 'task_progress', 'task_state', 'creation_time', 'start_time',
                  'end_time', 'dois', 'configuration', 'duration', 'urls']
        depth = 1
