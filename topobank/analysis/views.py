import io
import pickle
from zipfile import ZipFile, ZIP_DEFLATED

from django.http import HttpResponse, HttpResponseForbidden
from django.views.generic import DetailView, ListView
from django.views.generic.edit import FormMixin
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import OuterRef, Subquery
from rest_framework.generics import RetrieveAPIView

from ..manager.utils import selected_topographies, selection_from_session
from .models import Analysis, AnalysisFunction
from .serializers import AnalysisSerializer, PickledResult

from .forms import TopographyFunctionSelectForm

import numpy as np
import pandas as pd
import PyCo

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
                    args=OuterRef('args'), kwargs=OuterRef('kwargs')) \
            .order_by('-start_time')

        # Use this subquery for finding only latest analyses for each (topography, function, args, kwargs) group
        analyses = Analysis.objects\
            .filter(pk=Subquery(sq_analyses.values('pk')[:1]))\
            .order_by('function')

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
                '# Positional arguments of analysis function: {}\n'.format(a.get_args_display()) +
                '# Keyword arguments of analysis function: {}\n'.format(a.get_kwargs_display()) +
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

        properties += ['Topography', 'Positional arguments of analysis function',
                       'Keyword arguments of analysis function', 'Start time of analysis task',
                       'End time of analysis task', 'Duration of analysis task']
        values += [str(a.topography.name), a.get_args_display(), a.get_kwargs_display(), str(a.start_time),
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
