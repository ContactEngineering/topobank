import logging
import pickle

from rest_framework import serializers

from generic_relations.relations import GenericRelatedField

from ..manager.models import Surface, Topography
from ..manager.utils import mangle_content_type
from ..manager.serializers import SurfaceSerializer, TopographySerializer
from .models import Analysis

_log = logging.getLogger(__name__)


class AnalysisSerializer(serializers.ModelSerializer):
    kwargs = serializers.SerializerMethodField()
    subject = GenericRelatedField({
        Surface: SurfaceSerializer(),
        Topography: TopographySerializer()
    })

    def get_kwargs(self, obj):
        return pickle.loads(obj.kwargs)

    class Meta:
        model = Analysis
        fields = ['pk', 'function', 'subject', 'kwargs', 'task_state', 'creation_time',
                  'start_time', 'end_time', 'dois', 'configuration']
