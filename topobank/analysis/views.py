from django.http import HttpResponseForbidden
from django.views.generic import ListView
from django.views.generic.edit import FormMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import OuterRef, Subquery
from rest_framework.generics import RetrieveAPIView

from ..manager.utils import selected_topographies, selection_from_session
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
        sq_analyses = Analysis.objects \
            .filter(topography__surface__user=self.request.user,
                    topography__in=topographies,
                    function__in=functions) \
            .filter(topography=OuterRef('topography'), function=OuterRef('function'),\
                    args=OuterRef('args'), kwargs=OuterRef('kwargs'))\
            .order_by('-start_time')

        # Use this subquery for finding only latest analyses for each (topography, function, args, kwargs) group
        analyses = Analysis.objects\
            .filter(pk=Subquery(sq_analyses.values('pk')[:1]))

        # thanks to minkwe for the contribution at https://gist.github.com/ryanpitts/1304725

        #
        # maybe be better solved with PostGreSQL and Window functions
        #
        return analyses

    def get_initial(self):
        return dict(
            selection=selection_from_session(self.request.session),
            functions=AnalysisListView._selected_functions(self.request),
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def post(self, request, *args, **kwargs):  # TODO is this really needed?
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):

        selection = form.cleaned_data.get('selection', [])

        self.request.session['selection'] = tuple(selection)
        messages.info(self.request, "Topography selection saved.")

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
