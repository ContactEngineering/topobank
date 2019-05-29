import io
import pickle
import json
import numpy as np
import itertools
from collections import OrderedDict

from django.http import HttpResponse, HttpResponseForbidden, Http404
from django.views.generic import DetailView, FormView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Q
from django.conf import settings
from django import template
from rest_framework.generics import RetrieveAPIView

from bokeh.layouts import row, column, widgetbox
from bokeh.models import ColumnDataSource, CustomJS
from bokeh.palettes import Category10
from bokeh.models.formatters import FuncTickFormatter
from bokeh.models.ranges import DataRange1d
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models.widgets import CheckboxGroup
from bokeh.models.widgets.markups import Paragraph

from pint import UnitRegistry, UndefinedUnitError

from guardian.shortcuts import get_objects_for_user

import PyCo

from ..manager.models import Topography, Surface
from ..manager.utils import selected_topographies, selection_from_session
from .models import Analysis, AnalysisFunction
from .serializers import AnalysisSerializer
from .forms import TopographyFunctionSelectForm
from .utils import get_latest_analyses

import logging
_log = logging.getLogger(__name__)

SMALLEST_ABSOLUT_NUMBER_IN_LOGPLOTS = 1e-18
MAX_NUM_POINTS_FOR_SYMBOLS = 50

CARD_VIEW_FLAVORS = ['simple', 'plot', 'power spectrum']

def card_view_class(card_view_flavor):
    if card_view_flavor not in CARD_VIEW_FLAVORS:
        raise ValueError("Unknown card view flavor '{}'. Known values are: {}".format(card_view_flavor,
                                                                                       CARD_VIEW_FLAVORS))

    class_name = card_view_flavor.title().replace(' ','') + "CardView"
    return globals()[class_name]

def switch_card_view(request):
    """Selects appropriate card view upon request.

    Within the request, there is hint to which function
    the request is related to. Depending on the function,
    another view should be used.

    This view here creates than a new view and let
    it return the response instead.

    The request must have a "function_id" in its
    GET parameters.

    :param request:
    :return: HTTPResponse
    """
    if not request.is_ajax():
        return Http404

    try:
        function_id = int(request.GET.get('function_id'))
    except (KeyError, ValueError, TypeError):
        return HttpResponse("Error in GET arguments")

    function = AnalysisFunction.objects.get(id=function_id)

    view_class = card_view_class(function.card_view_flavor)

    return view_class.as_view()(request)

class SimpleCardView(TemplateView):
    """Very basic display of results. Base class for more complex views.

    Must be used in an AJAX call.
    """

    @staticmethod
    def _template_name(class_name, template_flavor):
        template_name_prefix = class_name.replace('View', '').replace('Card', '_card').lower()
        return f"analysis/{template_name_prefix}_{template_flavor}.html"

    def get_template_names(self):
        """Return list of possible templates.

        Uses request parameter 'template_flavor'.
        """
        try:
            template_flavor = self.request.GET.get('template_flavor')
        except (KeyError, ValueError):
            raise ValueError("Cannot read 'template_flavor' from GET arguments.")

        if template_flavor is None:
            raise ValueError("Missing 'template_flavor' in GET arguments.")

        template_name = self._template_name(self.__class__.__name__, template_flavor)

        #
        # If template does not exist, return template from parent class
        #
        # MAYBE later: go down the hierachy and take first template found
        try:
            template.loader.get_template(template_name)
        except template.TemplateDoesNotExist:
            base_class = self.__class__.__bases__[0]
            template_name = self._template_name(base_class.__name__, template_flavor)

        return [template_name]

    def get_context_data(self, **kwargs):
        """

        Gets function ids and topography ids from GET parameters.


        :return: dict to be used in analysis card templates' context

        The returned dict has the following keys:

          card_id: A CSS id referencing the card which is to be delivered
          analysis_available: queryset of all analyses which are relevant for this view
          analyses_success: queryset of successfully finished analyses (result is useable, can be displayed)
          analyses_failure: queryset of analyses finished with failures (result has traceback, can't be displayed)
          analyses_unready: queryset of analyses which are still running
          topographies_missing: list of topographies for which there is no Analysis object yet
        """
        context = super().get_context_data(**kwargs)

        request = self.request
        request_method = request.GET
        try:
            function_id = int(request_method.get('function_id'))
            card_id = request_method.get('card_id')
            topography_ids = [int(tid) for tid in request_method.getlist('topography_ids[]')]
        except (KeyError, ValueError):
            return HttpResponse("Error in GET arguments")

        #
        # Get all relevant analysis objects for this function and topography ids
        #
        analyses_avail = get_latest_analyses(function_id, topography_ids)

        #
        # Filter for analyses where the user has read permission for the related surface
        #
        readable_surfaces = get_objects_for_user(request.user, ['view_surface'], klass=Surface)
        analyses_avail = analyses_avail.filter(topography__surface__in=readable_surfaces)

        #
        # Determine status code of request - do we need to trigger request again?
        #
        analyses_ready = analyses_avail.filter(task_state__in=['su', 'fa'])
        analyses_unready = analyses_avail.filter(~Q(id__in=analyses_ready))

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
        topographies_available_ids = [a.topography.id for a in analyses_avail]
        topographies_missing = [Topography.objects.get(id=tid) for tid in topography_ids
                                if tid not in topographies_available_ids]

        function = AnalysisFunction.objects.get(id=function_id)

        context.update(dict(
            card_id=card_id,
            title=function.name,
            function=function,
            analyses_available=analyses_avail,  # all Analysis objects related to this card
            analyses_success=analyses_success,  # ..the ones which were successful and can be displayed
            analyses_failure=analyses_failure,  # ..the ones which have failures and can't be displayed
            analyses_unready=analyses_unready,  # ..the ones which are still running
            topographies_missing=topographies_missing  # topographies for which there is no Analysis object yet
        ))

        return context

    def get(self, request, *args, **kwargs):
        """
        Returns status code

        - 200 if all analysis are finished (success or failure).
        - 202 if there are still analyses which not have been finished,
          this can be used to request the card again later

        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        response = super().get(request, *args, **kwargs)

        #
        # Set status code depending on whether all analyses are finished
        #
        context = response.context_data
        num_analyses_avail = context['analyses_available'].count()
        num_analyses_ready = context['analyses_success'].count() + context['analyses_failure'].count()

        if (num_analyses_avail > 0) and (num_analyses_ready < num_analyses_avail):
            response.status_code = 202  # signal to caller: please request again
        else:
            response.status_code = 200  # request is as complete as possible

        return response

class PlotCardView(SimpleCardView):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        analyses_success = context['analyses_success']

        if len(analyses_success) == 0:
            #
            # Prepare plot, controls, and table with special values..
            #
            context.update(
                dict(plot_script="",
                     plot_div="No successfully finished analyses available",
                     special_values=[],
                     topography_colors=json.dumps(list()),
                     series_dashes=json.dumps(list())))
            return context

        first_analysis_result = analyses_success[0].result_obj
        title = first_analysis_result['name']

        xunit = first_analysis_result['xunit']
        yunit = first_analysis_result['yunit']

        ureg = UnitRegistry()  # for unit conversion for each analysis individually, see below

        #
        # set xrange, yrange -> automatic bounds for zooming
        #
        x_range = DataRange1d(bounds='auto')  # if min+max not given, calculate from data of render
        y_range = DataRange1d(bounds='auto')

        def get_axis_type(key):
            return first_analysis_result.get(key) or "linear"

        x_axis_label = first_analysis_result['xlabel'] + f' ({xunit})'
        y_axis_label = first_analysis_result['ylabel'] + f' ({yunit})'

        #
        # Create the plot figure
        #
        plot = figure(title=title,
                      plot_height=300,
                      sizing_mode='scale_width',
                      x_range=x_range,
                      y_range=y_range,
                      x_axis_label=x_axis_label,
                      y_axis_label=y_axis_label,
                      x_axis_type=get_axis_type('xscale'),
                      y_axis_type=get_axis_type('yscale'),
                      tools="crosshair,pan,reset,save,wheel_zoom,box_zoom")

        #
        # Prepare helpers for dashes and colors
        #
        color_cycle = itertools.cycle(Category10[10])
        dash_cycle = itertools.cycle(['solid', 'dashed', 'dotted', 'dotdash', 'dashdot'])
        # symbol_cycle = itertools.cycle(['circle', 'triangle', 'diamond', 'square', 'asterisk'])
        # TODO remove code for toggling symbols if not needed

        topography_colors = OrderedDict()  # key: Topography instance
        topography_names = []

        series_dashes = OrderedDict()  # key: series name
        series_names = []

        # Also give each series a symbol (only used for small number of points)
        # series_symbols = OrderedDict()  # key: series name

        #
        # Traverse analyses and plot lines
        #
        js_code = ""
        js_args = {}

        special_values = []  # elements: (topography, quantity name, value, unit string)

        for analysis in analyses_success:

            topography_name = analysis.topography.name

            #
            # find out colors for topographies
            #
            if analysis.topography not in topography_colors:
                topography_colors[analysis.topography] = next(color_cycle)
                topography_names.append(analysis.topography.name)

            if analysis.task_state == analysis.FAILURE:
                continue  # should not happen if only called with successful analyses
            elif analysis.task_state == analysis.SUCCESS:
                series = analysis.result_obj['series']
            else:
                # not ready yet
                continue  # should not happen if only called with successful analyses

            #
            # find out scale for data
            #
            analysis_result = analysis.result_obj

            try:
                analysis_xscale = ureg.convert(1, xunit, analysis_result['xunit'])
                analysis_yscale = ureg.convert(1, yunit, analysis_result['yunit'])
            except UndefinedUnitError as exc:
                _log.error("Cannot convert units when displaying results for analysis with id %s. Cause: %s",
                           analysis.id, str(exc))
                continue
                # TODO How to handle such an error here? Notification? Message in analysis box?

            for s in series:
                # One could use AjaxDataSource for retrieving the results, but useful if we are already in AJAX call?
                xarr = np.array(s['x'])
                yarr = np.array(s['y'])

                # if logplot, filter all zero values
                mask = np.zeros(xarr.shape, dtype=bool)
                if get_axis_type('xscale') == 'log':
                    mask |= np.isclose(xarr, 0, atol=SMALLEST_ABSOLUT_NUMBER_IN_LOGPLOTS)
                if get_axis_type('yscale') == 'log':
                    mask |= np.isclose(yarr, 0, atol=SMALLEST_ABSOLUT_NUMBER_IN_LOGPLOTS)

                source = ColumnDataSource(data=dict(x=analysis_xscale * xarr[~mask],
                                                    y=analysis_yscale * yarr[~mask]))

                series_name = s['name']
                #
                # find out dashes for data series
                #
                if series_name not in series_dashes:
                    series_dashes[series_name] = next(dash_cycle)
                    # series_symbols[series_name] = next(symbol_cycle)
                    series_names.append(series_name)

                #
                # Actually plot the line
                #
                show_symbols = np.count_nonzero(~mask) <= MAX_NUM_POINTS_FOR_SYMBOLS

                legend_entry = topography_name + ": " + series_name

                curr_color = topography_colors[analysis.topography]
                curr_dash = series_dashes[series_name]
                # curr_symbol = series_symbols[series_name]

                line_glyph = plot.line('x', 'y', source=source, legend=legend_entry,
                                       line_color=curr_color,
                                       line_dash=curr_dash)
                if show_symbols:
                    symbol_glyph = plot.scatter('x', 'y', source=source, legend=legend_entry,
                                                marker='circle',
                                                line_color=curr_color,
                                                line_dash=curr_dash,
                                                fill_color=curr_color)

                #
                # Prepare JS code to toggle visibility
                #
                series_idx = series_names.index(series_name)
                topography_idx = topography_names.index(topography_name)

                # prepare unique id for this line
                glyph_id = f"glyph_{topography_idx}_{series_idx}_line"
                js_args[glyph_id] = line_glyph  # mapping from Python to JS

                # only indices of visible glyphs appear in "active" lists of both button groups
                js_code += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) " \
                           + f"&& topography_btn_group.active.includes({topography_idx});"

                if show_symbols:
                    # prepare unique id for this symbols
                    glyph_id = f"glyph_{topography_idx}_{series_idx}_symbol"
                    js_args[glyph_id] = symbol_glyph  # mapping from Python to JS

                    # only indices of visible glyphs appear in "active" lists of both button groups
                    js_code += f"{glyph_id}.visible = series_btn_group.active.includes({series_idx}) " \
                               + f"&& topography_btn_group.active.includes({topography_idx});"

            #
            # Collect special values to be shown in the result card
            #
            if 'scalars' in analysis.result_obj:
                for k, v in analysis.result_obj['scalars'].items():
                    special_values.append((analysis.topography, k, v, analysis.topography.unit))

        #
        # Final configuration of the plot
        #

        # plot.legend.click_policy = "hide" # can be used to disable lines by clicking on legend
        plot.legend.visible = False  # we have extra widgets to disable lines
        plot.toolbar.logo = None
        plot.toolbar.active_inspect = None
        plot.xaxis.axis_label_text_font_style = "normal"
        plot.yaxis.axis_label_text_font_style = "normal"
        plot.xaxis.major_label_text_font_size = "12pt"
        plot.yaxis.major_label_text_font_size = "12pt"

        # see js function "format_exponential()" in project.js file
        plot.xaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")
        plot.yaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")

        #
        # Adding widgets for switching lines on/off
        #
        topo_names = list(t.name for t in topography_colors.keys())

        series_button_group = CheckboxGroup(
            labels=series_names,
            css_classes=["topobank-series-checkbox"],
            active=list(range(len(series_names))))  # all active

        topography_button_group = CheckboxGroup(
            labels=topo_names,
            css_classes=["topobank-topography-checkbox"],
            active=list(range(len(topo_names))))  # all active

        # extend mapping of Python to JS objects
        js_args['series_btn_group'] = series_button_group
        js_args['topography_btn_group'] = topography_button_group

        # add code for setting styles of widgetbox elements
        # js_code += """
        # style_checkbox_labels({});
        # """.format(card_idx)

        toggle_lines_callback = CustomJS(args=js_args, code=js_code)

        #
        # TODO Idea: Generate DIVs with Markup of colors and dashes and align with Buttons/Checkboxes
        #
        widgets = row(widgetbox(Paragraph(text="Topographies"), topography_button_group),
                      widgetbox(Paragraph(text="Data Series"), series_button_group))

        series_button_group.js_on_click(toggle_lines_callback)
        topography_button_group.js_on_click(toggle_lines_callback)

        #
        # Convert plot and widgets to HTML, add meta data for template
        #
        script, div = components(column(plot, widgets, sizing_mode='scale_width'))

        context.update(dict(
            plot_script=script,
            plot_div=div,
            special_values=special_values,
            topography_colors=json.dumps(list(topography_colors.values())),
            series_dashes=json.dumps(list(series_dashes.values()))))

        return context

class PowerSpectrumCardView(PlotCardView):
    pass


class AnalysisFunctionDetailView(DetailView):

    model = AnalysisFunction
    template_name = "analysis/analyses_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        function = self.object

        topographies = selected_topographies(self.request)

        card = dict(function=function,
                    topography_ids_json=json.dumps([ t.id for t in topographies]))

        context['card'] = card
        return context


class AnalysesListView(FormView):
    form_class = TopographyFunctionSelectForm
    success_url = reverse_lazy('analysis:list')
    template_name = "analysis/analyses_list.html"

    def get_initial(self):
        return dict(
            selection=selection_from_session(self.request.session),
            functions=AnalysesListView._selected_functions(self.request),
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

            cards.append(dict(function=function,
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

    # Pack analysis results into a single text file.
    f = io.StringIO()
    for i, id in enumerate(ids):
        a = Analysis.objects.get(pk=id)
        if i == 0:
            f.write('# {}\n'.format(a.function) +
                    '# {}\n'.format('='*len(str(a.function))) +
                    '# TopoBank version: {}\n'.format(settings.TOPOBANK_VERSION) +
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
    # TODO: Probably this function leaves out data if the sheet names are not unique (built from topography+series name)
    # TODO: pandas is a requirement that takes quite long when building docker images, do we really need it here?
    import pandas as pd

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
            values += [str(a.function), settings.TOPOBANK_VERSION, PyCo.__version__]

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
