import logging

from django.shortcuts import reverse

from rest_framework import serializers

from generic_relations.relations import GenericRelatedField

from ..manager.models import Surface, Topography
from ..manager.serializers import SurfaceSerializer, TopographySerializer
from .models import Analysis, AnalysisFunction
from .registry import AnalysisRegistry

_log = logging.getLogger(__name__)


class AnalysisResultSerializer(serializers.ModelSerializer):
    duration = serializers.SerializerMethodField()
    kwargs = serializers.SerializerMethodField()
    subject = GenericRelatedField({
        Surface: SurfaceSerializer(),
        Topography: TopographySerializer()
    })
    task_state = serializers.SerializerMethodField()
    task_progress = serializers.SerializerMethodField()
    api = serializers.SerializerMethodField()

    def get_duration(self, obj):
        return obj.duration

    def get_kwargs(self, obj):
        return obj.kwargs

    def get_task_state(self, obj):
        """
        Return the most likely state of the task from the self-reported task
        information in the database and the information obtained from Celery.
        """
        # This is self-reported by the task runner
        self_reported_task_state = obj.task_state
        # This is what Celery reports back
        celery_task_state = obj.get_celery_state()

        if celery_task_state is None:
            # There is no Celery state, possibly because the Celery task has not yet been created
            return self_reported_task_state

        if self_reported_task_state == celery_task_state:
            # We're good!
            return self_reported_task_state
        else:
            if self_reported_task_state == Analysis.SUCCESS:
                # Something is wrong, but we return success if the task self-reports success.
                _log.info(f"The analysis with id {obj.id} self-reported the state '{self_reported_task_state}', "
                          f"but Celery reported '{celery_task_state}'. I am returning a success.")
                return Analysis.SUCCESS
            elif celery_task_state == Analysis.FAILURE:
                # Celery seems to think this task failed, we trust it as the self-reported state will
                # be unreliable in this case.
                _log.info(f"The analysis with id {obj.id} self-reported the state '{self_reported_task_state}', "
                          f"but Celery reported '{celery_task_state}'. I am returning a failure.")
                return Analysis.FAILURE
            else:
                # In all other cases, we trust the self-reported state.
                _log.info(f"The analysis with id {obj.id} self-reported the state '{self_reported_task_state}', "
                          f"but Celery reported '{celery_task_state}'. I am returning the self-reported state.")
                return self_reported_task_state

    def get_task_progress(self, obj):
        if obj.task_state == Analysis.STARTED:
            return obj.get_task_progress()
        elif obj.task_state == Analysis.SUCCESS:
            return 1.0
        else:
            return 0.0

    def get_api(self, obj):
        return {
            'dataUrl': reverse('analysis:data', kwargs=dict(pk=obj.id, location='')),
            'statusUrl': reverse('analysis:status-detail', kwargs=dict(pk=obj.id))
        }

    class Meta:
        model = Analysis
        fields = ['id', 'function', 'subject', 'kwargs', 'task_progress', 'task_state', 'creation_time', 'start_time',
                  'end_time', 'dois', 'configuration', 'duration', 'api']
        depth = 1


class AnalysisFunctionSerializer(serializers.ModelSerializer):
    visualization_app_name = serializers.SerializerMethodField()
    visualization_type = serializers.SerializerMethodField()

    def get_visualization_app_name(self, obj):
        app_name, type = AnalysisRegistry().get_visualization_type_for_function_name(obj.name)
        return app_name

    def get_visualization_type(self, obj):
        app_name, type = AnalysisRegistry().get_visualization_type_for_function_name(obj.name)
        return type

    class Meta:
        model = AnalysisFunction
        fields = ['id', 'name', 'visualization_app_name', 'visualization_type']
