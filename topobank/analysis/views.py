from django.http import HttpResponseForbidden
from django.views.generic import ListView
from django.views.generic.edit import FormMixin
from django.urls import reverse_lazy
from rest_framework.generics import RetrieveAPIView

from ..manager.models import Topography
from ..manager.utils import selected_topographies
from .models import Analysis, AnalysisFunction
from .serializers import AnalysisSerializer

from .forms import TopographyFunctionSelectForm

class AnalysisListView(FormMixin, ListView):
    model = Analysis
    context_object_name = 'analyses'
    form_class = TopographyFunctionSelectForm
    success_url = reverse_lazy('analysis:list')

    def get_queryset(self):
        topographies = selected_topographies(self.request)
        functions = AnalysisListView._selected_functions(self.request)
        analyses = Analysis.objects.filter(topography__surface__user=self.request.user,
                                           topography__in=topographies,
                                           function__in=functions).order_by('function')
        return analyses

    def get_initial(self):
        return dict(
            topographies=selected_topographies(self.request),
            functions=AnalysisListView._selected_functions(self.request),
        )

    def post(self, request, *args, **kwargs):  # TODO is this really needed?
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        # save selection from form in session as list of integers
        topographies = form.cleaned_data.get('topographies', [])
        self.request.session['selected_topographies'] = list(t.id for t in topographies)
        functions = form.cleaned_data.get('functions', [])
        self.request.session['selected_functions'] = list(t.id for t in functions)
        return super().form_valid(form)

    @staticmethod
    def _selected_functions(request):
        """Returns selected functions as saved in session.
        """
        function_ids = request.session.get('selected_functions', [])
        functions = AnalysisFunction.objects.filter(id__in=function_ids)
        return functions


class AnalysisDetailView(RetrieveAPIView):
    queryset = Analysis.objects.all()
    serializer_class = AnalysisSerializer
