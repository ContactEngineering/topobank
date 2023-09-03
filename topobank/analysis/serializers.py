import logging

from rest_framework import serializers
from rest_framework.reverse import reverse

from .models import Analysis, AnalysisFunction, AnalysisSubject, Configuration
from .registry import AnalysisRegistry

_log = logging.getLogger(__name__)


class ConfigurationSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Configuration
        fields = ['valid_since', 'versions']

    versions = serializers.SerializerMethodField()

    def get_versions(self, obj):
        versions = {}
        for version in obj.versions.all():
            versions[str(version.dependency)] = version.number_as_string()
        return versions


class AnalysisFunctionSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = AnalysisFunction
        fields = ['id', 'url', 'name', 'visualization_app_name', 'visualization_type']

    url = serializers.HyperlinkedIdentityField(view_name='analysis:function-detail', read_only=True)

    visualization_app_name = serializers.SerializerMethodField()
    visualization_type = serializers.SerializerMethodField()

    def get_visualization_app_name(self, obj):
        app_name, type = AnalysisRegistry().get_visualization_type_for_function_name(obj.name)
        return app_name

    def get_visualization_type(self, obj):
        app_name, type = AnalysisRegistry().get_visualization_type_for_function_name(obj.name)
        return type


class AnalysisSubjectSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = AnalysisSubject
        fields = ['topography', 'surface', 'collection']

    topography = serializers.HyperlinkedRelatedField(view_name='manager:topography-api-detail', read_only=True)
    surface = serializers.HyperlinkedRelatedField(view_name='manager:surface-api-detail', read_only=True)


class AnalysisResultSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Analysis
        fields = ['url', 'function', 'subject', 'kwargs', 'task_progress', 'task_state', 'creation_time', 'start_time',
                  'end_time', 'dois', 'configuration', 'duration', 'data_prefix', 'error']

    url = serializers.HyperlinkedIdentityField(view_name='analysis:result-detail', read_only=True)
    data_prefix = serializers.SerializerMethodField()

    configuration = serializers.HyperlinkedRelatedField(view_name='analysis:configuration-detail', read_only=True)
    function = serializers.HyperlinkedRelatedField(view_name='analysis:function-detail', read_only=True)

    subject = AnalysisSubjectSerializer()

    duration = serializers.SerializerMethodField()
    task_state = serializers.SerializerMethodField()
    task_progress = serializers.SerializerMethodField()
    error = serializers.SerializerMethodField()

    def get_data_prefix(self, obj):
        return reverse('analysis:data', args=(obj.id, ''), request=self.context['request'])

    def get_duration(self, obj):
        return obj.duration

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
        task_state = self.get_task_state(obj)
        if task_state == Analysis.STARTED:
            return obj.get_task_progress()
        elif task_state == Analysis.SUCCESS:
            return 1.0
        else:
            return 0.0

    def get_error(self, obj):
        return obj.get_error()
