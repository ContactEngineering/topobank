import io
import pickle
import json
import numpy as np
import pandas as pd

from django.http import HttpResponse, HttpResponseForbidden, Http404
from django.views.generic.edit import FormView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import OuterRef, Subquery
from django.shortcuts import render
from django.db.models import Q
from rest_framework.generics import RetrieveAPIView

from ..manager.models import Topography
from ..manager.utils import selected_topographies, selection_from_session
from .models import Analysis, AnalysisFunction
from .serializers import AnalysisSerializer
from .forms import TopographyFunctionSelectForm
from .cards import function_card_context
from .utils import get_latest_analyses

import PyCo

def function_result_card(request):

    if request.is_ajax():

        request_method = request.GET
        try:
            function_id = int(request_method.get('function_id'))
            card_idx = int(request_method.get('card_idx'))
            topography_ids = [ int(tid) for tid in request_method.getlist('topography_ids[]')]
        except (KeyError, ValueError):
            return HttpResponse("Error in GET arguments")

        analyses_avail = get_latest_analyses(request.user, function_id, topography_ids)

        #
        # Determine status code of request - do we need to trigger request again?
        #
        analyses_ready = analyses_avail.filter(task_state__in=['su', 'fa'])
        analyses_unready = analyses_avail.filter(~Q(id__in=analyses_ready))

        num_analyses_avail = analyses_avail.count()
        num_analyses_ready = analyses_ready.count()

        if (num_analyses_avail > 0) and (num_analyses_ready < num_analyses_avail):
            status = 202  # signal to caller: please request again
        else:
            status = 200  # request is as complete as possible

        #
        # collect lists of successful analyses and analyses with failures
        #
        # Only the successful ones should show up in the plot
        # the ones with failure should be shown elsewhere
        analyses_success = analyses_ready.filter(task_state='su')
        analyses_failure = analyses_ready.filter(task_state='fa')

        #
        # collect list of topographies for which no analyses exist
        #
        topographies_available_ids = [ a.topography.id for a in analyses_avail ]
        topographies_missing = [ Topography.objects.get(id=tid) for tid in topography_ids
                                 if tid not in topographies_available_ids ]

        function = AnalysisFunction.objects.get(id=function_id)

        context = dict(
            idx = card_idx,
            title = function.name,
            analyses_available = analyses_avail, # all Analysis objects related to this card
            analyses_success = analyses_success, # ..the ones which were successful and can be displayed
            analyses_failure = analyses_failure,   # ..the ones which have failures and can't be displayed
            analyses_unready = analyses_unready,   # ..the ones which are still running
            topographies_missing = topographies_missing  # topographies for which there is no Analyis object yet
        )

        context.update(function_card_context(analyses_success))

        return render(request, template_name="analysis/function_result_card.html", context=context, status=status)
    else:
        return Http404

class AnalysesView(FormView):
    form_class = TopographyFunctionSelectForm
    success_url = reverse_lazy('analysis:list')
    template_name = "analysis/analyses.html"

    def get_initial(self):
        return dict(
            selection=selection_from_session(self.request.session),
            functions=AnalysesView._selected_functions(self.request),
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        cards = []

        for function in self._selected_functions(self.request):

            topographies = selected_topographies(self.request)

            cards.append(dict(template="analysis/function_result_card.html",
                              function=function,
                              topography_ids_json=json.dumps([ t.id for t in topographies])))

        context['cards'] = cards
        return context

class AnalysisRetrieveView(RetrieveAPIView): #TODO needed?
    queryset = Analysis.objects.all()
    serializer_class = AnalysisSerializer


def download_analysis_to_txt(request, ids):
    ids = [int(i) for i in ids.split(',')]

    # TODO: It would probably be useful to use the (some?) template engine for this.
    # TODO: We need a mechanism for embedding references to papers into output.
    # FIXME: TopoBank needs version information

    # Pack analysis results into a single text file.
    f = io.StringIO()
    for i, id in enumerate(ids):
        a = Analysis.objects.get(pk=id)
        if i == 0:
            f.write('# {}\n'.format(a.function) +
                    '# {}\n'.format('='*len(str(a.function))) +
                    '# TopoBank version: N/A\n' +
                    '# PyCo version: {}\n'.format(PyCo.__version__) +
                    '# IF YOU USE THIS DATA IN A PUBLICATION, PLEASE CITE XXX.\n' +
                    '\n')

        f.write('# Topography: {}\n'.format(a.topography.name) +
                '# {}\n'.format('='*(len('Topography: ')+len(str(a.topography.name)))) +
                '# Further arguments of analysis function: {}\n'.format(a.get_kwargs_display()) +
                '# Start time of analysis task: {}\n'.format(a.start_time) +
                '# End time of analysis task: {}\n'.format(a.end_time) +
                '# Duration of analysis task: {}\n'.format(a.duration()) +
                '\n')

        result = pickle.loads(a.result)
        header = 'Columns: {} ({}), {} ({})'.format(result['xlabel'], result['xunit'], result['ylabel'], result['yunit'])

        for series in result['series']:
            np.savetxt(f, np.transpose([series['x'], series['y']]),
                       header='{}\n{}\n{}'.format(series['name'], '-'*len(series['name']), header))
            f.write('\n')

    # Prepare response object.
    response = HttpResponse(f.getvalue(), content_type='application/text')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format('{}.txt'.format(a.function.pyfunc))

    # Close file and return response.
    f.close()
    return response


def download_analysis_to_xlsx(request, ids):
    ids = [int(i) for i in ids.split(',')]

    # TODO: We need a mechanism for embedding references to papers into output.
    # FIXME: TopoBank needs version information
    # TODO: Probably this function leaves out data if the sheet names are not unique (built from topography+series name)

    # Pack analysis results into a single text file.
    f = io.BytesIO()
    excel = pd.ExcelWriter(f)

    # Global properties and values.
    properties = []
    values = []
    for i, id in enumerate(ids):
        a = Analysis.objects.get(pk=id)
        if i == 0:
            properties += ['Function', 'TopoBank version', 'PyCo version']
            values += [str(a.function), 'N/A', PyCo.__version__]

        properties += ['Topography',
                       'Further arguments of analysis function', 'Start time of analysis task',
                       'End time of analysis task', 'Duration of analysis task']
        values += [str(a.topography.name), a.get_kwargs_display(), str(a.start_time),
                   str(a.end_time), str(a.duration())]

        result = pickle.loads(a.result)
        column1 = '{} ({})'.format(result['xlabel'], result['xunit'])
        column2 = '{} ({})'.format(result['ylabel'], result['yunit'])

        for series in result['series']:
            df = pd.DataFrame({column1: series['x'], column2: series['y']})
            df.to_excel(excel, sheet_name='{} - {}'.format(a.topography.name, series['name'].replace('/', ' div ')))
    df = pd.DataFrame({'Property': properties, 'Value': values})
    df.to_excel(excel, sheet_name='INFORMATION', index=False)
    excel.close()

    # Prepare response object.
    response = HttpResponse(f.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format('{}.xlsx'.format(a.function.pyfunc))

    # Close file and return response.
    f.close()
    return response
