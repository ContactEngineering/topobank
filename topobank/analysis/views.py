from django.views.generic import ListView
from django.views.generic.edit import FormMixin
from rest_framework.generics import RetrieveAPIView

from ..manager.models import Topography
from .models import Analysis, AnalysisFunction
from .serializers import AnalysisSerializer

from .forms import TopographySelectForm

class AnalysisListView(FormMixin, ListView):
    model = Analysis
    context_object_name = 'analyses'
    form_class = TopographySelectForm

    def get_queryset(self):
        topography_ids = self.request.GET.getlist('topographies', [])
        function_ids = self.request.GET.getlist('functions', [])

        # TODO only already calculated analyses are shown, trigger from here?

        analyses = Analysis.objects.filter(topography__surface__user=self.request.user,
                                           topography_id__in=topography_ids,
                                           function_id__in=function_ids).order_by('function')
        return analyses

    def get_initial(self):
        topography_ids = self.request.GET.getlist('topographies', [])
        function_ids = self.request.GET.getlist('functions', [])

        if len(function_ids) == 0:
            functions = AnalysisFunction.objects.all()
        else:
            functions = AnalysisFunction.objects.filter(id__in=function_ids)

        return dict(
            topographies=Topography.objects.filter(id__in=topography_ids),
            functions=functions,
        )


class AnalysisDetailView(RetrieveAPIView):
    queryset = Analysis.objects.all()
    serializer_class = AnalysisSerializer
