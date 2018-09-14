from django.shortcuts import render
from django.views.generic import ListView
import pickle

from .models import Analysis

def analyses(request):

    analyses = Analysis.objects.filter(topography__surface__user=request.user)

    analyses = [
            {
                'func_name': a.function.name,
                'topography': a.topography,
                'result': pickle.loads(a.result),
                'task_state': a.get_task_state_display(),
                'task_id': a.task_id,
            }
            for a in analyses
        ]

    return render(request, 'analysis/analysis_list.html', context=dict(analyses=analyses))







