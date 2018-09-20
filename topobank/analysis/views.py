from django.views.generic import ListView
from django.views.generic.detail import SingleObjectMixin
from rest_framework.generics import RetrieveAPIView

from .models import Analysis
from .serializers import AnalysisSerializer

class AnalysisListView(ListView):
    model = Analysis
    context_object_name = 'analyses'

    def get_queryset(self):
        analyses = Analysis.objects.filter(topography__surface__user=self.request.user).order_by('function')
        # TODO add column with unpickled data
        return analyses


class AnalysisDetailView(RetrieveAPIView):
    queryset = Analysis.objects.all()
    serializer_class = AnalysisSerializer
