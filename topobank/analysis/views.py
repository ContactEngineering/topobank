from django.shortcuts import render
from django.views.generic import ListView
import pickle

from .models import Analysis

class AnalysisListView(ListView):
    model = Analysis
    context_object_name = 'analyses'

    def get_queryset(self):
        analyses = Analysis.objects.filter(topography__surface__user=self.request.user)
        # TODO add column with unpickled data
        return analyses
