from django.shortcuts import redirect
from django.views.generic import DetailView, ListView, UpdateView, CreateView, DeleteView
from django.urls import reverse, reverse_lazy
from django.core.files.storage import FileSystemStorage # TODO use default_storage instead?
from django.core.files.storage import default_storage
from django.core.files import File
from django.core.exceptions import PermissionDenied
from django.conf import settings
from formtools.wizard.views import SessionWizardView

from django.http import HttpResponseForbidden
from django.views.generic.edit import FormMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import DataRange1d, Range1d, LinearColorMapper, ColorBar, Row
import numpy as np

import json
import os.path
import logging

from .models import Topography, Surface
from .forms import TopographyForm, SurfaceForm, TopographySelectForm
from .forms import TopographyFileUploadForm, TopographyMetaDataForm, Topography1DUnitsForm, Topography2DUnitsForm
from .utils import get_topography_file, optimal_unit, \
    selected_topographies, selection_from_session, selection_for_select_all, \
    bandwidths_data

_log = logging.getLogger(__name__)

class SurfaceAccessMixin(UserPassesTestMixin):

    login_url = reverse_lazy("manager:access-denied")
    redirect_field_name = None

    def test_func(self):
        if 'pk' not in self.kwargs:
            return True

        surface = Surface.objects.get(pk=self.kwargs['pk'])
        return surface.user == self.request.user

class TopographyAccessMixin(UserPassesTestMixin):

    login_url = reverse_lazy("manager:access-denied")
    redirect_field_name = None

    def test_func(self):
        if 'pk' not in self.kwargs:
            return True

        topo = Topography.objects.get(pk=self.kwargs['pk'])
        return topo.surface.user == self.request.user

#
# Using a wizard because we need intermediate calculations
#
# There are 4 forms, used in 3 steps (0,1, then 2 or 3):
#
# 0: loading of the topography file
# 1: choosing the data source, add measurement date and a description
# 2: adding physical size and units (if 2D and only for data which is not available in the file)
# 3: adding physical size and units (if 1D and only for data is not available in the file)
#
# Maybe an alternative would be to use AJAX calls as described here (under "GET"):
#
#  https://sixfeetup.com/blog/making-your-django-templates-ajax-y
#
class TopographyCreateWizard(SessionWizardView):
    form_list = [TopographyFileUploadForm, TopographyMetaDataForm, Topography2DUnitsForm, Topography1DUnitsForm]
    template_name = 'manager/topography_wizard.html'
    file_storage = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT,'topographies/wizard'))

    def dispatch(self, request, *args, **kwargs):
        if request.POST.get('cancel'):
            return redirect(reverse('manager:surface-list'))
        return super().dispatch(request, *args, **kwargs)

    def get_form_initial(self, step):

        initial = {}

        if step == 'upload':
            #
            # Pass surface in order to have it later in done() method
            #
            # make sure that the surface exists and belongs to the current user
            try:
                surface = Surface.objects.get(id=int(self.kwargs['surface_id']))
            except Surface.DoesNotExist:
                raise PermissionDenied()
            if surface.user != self.request.user:
                raise PermissionDenied()

            initial['surface'] = surface

        if step in ['metadata', 'units2D', 'units1D']:
            # provide datafile attribute from first step
            step0_data = self.get_cleaned_data_for_step('upload')
            datafile = step0_data['datafile']

        if step == 'metadata':
            initial['name'] = os.path.basename(datafile.name) # the original file name

        if step in ['units2D','units1D']:

            step1_data = self.get_cleaned_data_for_step('metadata')

            topofile = get_topography_file(datafile.file.name)

            topo = topofile.topography(int(step1_data['data_source']))
            # topography as it is in file

            size_unit = topo.info['unit']

            #
            # Set initial size and size unit
            #

            has_2_dim = topo.dim == 2

            if has_2_dim:
                initial_size_x, initial_size_y = topo.size
            else:
                initial_size_x, = topo.size # size is always a tuple
                initial_size_y = None # needed for database field

            if size_unit is not None:
                #
                # Try to optimize size unit
                #
                size_unit, conversion_factor = optimal_unit(topo.size, size_unit)

                initial_size_x *= conversion_factor # TODO Is it correct to do this if there is "int()" afterwards?
                if has_2_dim:
                    initial_size_y *= conversion_factor

            initial['size_x'] = initial_size_x
            initial['size_y'] = initial_size_y

            # Check whether the user should be able to change the size
            # see also #39
            #
            # Allowed if the topography/line scan object returned by read allows it
            # (i.e. there is a setter for the size)
            try:
                topo.size = topo.size # there are hopefully no side-effects
                size_setter_avail = True
            except AttributeError:
                size_setter_avail = False

            initial['size_editable'] = size_setter_avail

            initial['size_unit'] = size_unit
            initial['size_unit_editable'] = size_unit is None

            #
            # Set initial height and height unit
            #
            try:
                initial['height_scale'] = topo.coeff
                initial['height_scale_editable'] = False
            except AttributeError:
                initial['height_scale'] = 1
                initial['height_scale_editable'] = True # this factor can be changed by user because not given in file

            initial['height_unit'] = size_unit
            #
            # Set initial detrend mode
            #
            try:
                initial['detrend_mode'] = topo.detrend_mode
            except AttributeError:
                initial['detrend_mode'] = 'center'

            #
            # Set resolution (only for having the data later)
            #
            if topo.dim == 2:
                initial['resolution_x'], initial['resolution_y'] = topo.resolution
            else:
                initial['resolution_x'] = len(topo.positions()) # TODO Check: also okay for uniform line scans?

        return initial

    @staticmethod
    def get_topofile_cache_key(datafile_fname):
        return f"topofile_{datafile_fname}"  # filename is unique inside wizard's directory -> cache key unique

    def get_form_kwargs(self, step=None):

        kwargs = super(TopographyCreateWizard, self).get_form_kwargs(step)

        if step == 'metadata':
            step0_data = self.get_cleaned_data_for_step('upload')

            datafile_fname = step0_data['datafile'].file.name

            topofile = get_topography_file(datafile_fname)

            #
            # Set data source choices based on file contents
            #
            kwargs['data_source_choices'] = [(k, ds) for k, ds in
                                             enumerate(topofile.data_sources)]

        return kwargs

    def get_form_instance(self, step):
        # if there is no instance yet, but should be one,
        # get instance from database
        if not self.instance_dict:
            if 'pk' in self.kwargs:
                return Topography.objects.get(pk=self.kwargs['pk'])
        return None

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)
        context['surface'] = Surface.objects.get(id=int(self.kwargs['surface_id']))
        return context

    def done(self, form_list, **kwargs):
        """Finally use the form data when after finishing the wizard.

        :param form_list: list of forms
        :param kwargs:
        :return: HTTPResponse
        """
        #
        # collect all data from forms
        #
        d = dict((k, v) for form in form_list for k, v in form.cleaned_data.items())
        # TODO maybe use self.get_all_cleaned_data()

        #
        # collect additional data
        #
        # TODO Check if we'd better get resolution here

        #
        # Check whether given surface is from this user
        #
        surface = d['surface']
        if surface.user != self.request.user:
            raise PermissionDenied()

        #
        # move file to the permanent file system (wizard files will be deleted)
        #
        new_path = os.path.join(self.request.user.get_media_path(),
                                os.path.basename(d['datafile'].name))
        with d['datafile'].open(mode='rb') as datafile:
            d['datafile'] = default_storage.save(new_path, File(datafile))

        #
        # TODO remove topography file object from cache
        #

        #
        # create topography in database
        #
        instance = Topography(**d)
        instance.save()

        # put image creation tasks in queue
        # instance.submit_images_creation()

        # put automated analysis in queue
        instance.submit_automated_analyses() # TODO create notification

        return redirect(reverse('manager:topography-detail', kwargs=dict(pk=instance.pk)))

class TopographyCreateView(CreateView):# TODO check if still needed
    model = Topography
    form_class = TopographyForm

    def get_initial(self, *args, **kwargs):
        initial = super(TopographyCreateView, self).get_initial()
        initial = initial.copy()
        initial['user'] = self.request.user
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['surface'] = Surface.objects.get(id=kwargs['surface_id'])
        return context

    def get_success_url(self):
        return reverse('manager:topography-detail', kwargs=dict(pk=self.object.pk))

class TopographyUpdateView(TopographyAccessMixin, UpdateView):
    model = Topography
    form_class = TopographyForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['has_size_y'] = self.object.size_y is not None
        return kwargs

    def get_success_url(self):
        #self.object.submit_images_creation() # TODO this is only needed if image would change
        self.object.submit_automated_analyses()
        return reverse('manager:topography-detail', kwargs=dict(pk=self.object.pk))

class TopographyListView(ListView):
    model = Topography
    context_object_name = 'topographies'

    def get_queryset(self):
        topos = Topography.objects.filter(surface__user=self.request.user)
        return topos

class TopographyDetailView(TopographyAccessMixin, DetailView):
    model = Topography
    context_object_name = 'topography'

    def get_1D_plot(self, pyco_topo, topo):
        """Calculate 1D line plot of topography (line scan).

        :param pyco_topo: PyCo Topography instance
        :param topo: TopoBank Topography instance
        :return: bokeh plot
        """


        TOOLTIPS = [
            ("x", "$x " + topo.size_unit),
            ("height", "$y " + topo.height_unit),
        ]

        x, y = pyco_topo.positions_and_heights()

        x_range = DataRange1d(bounds='auto')
        y_range = DataRange1d(bounds='auto')

        plot = figure(x_range=x_range, y_range=y_range,
                      x_axis_label=f'x ({topo.size_unit})',
                      y_axis_label=f'height ({topo.height_unit})',
                      toolbar_location="above",
                      tooltips=TOOLTIPS)


        plot.circle(x,y)

        plot.xaxis.axis_label_text_font_style = "normal"
        plot.yaxis.axis_label_text_font_style = "normal"

        plot.toolbar.logo = None

        return plot

    def get_2D_plot(self, pyco_topo, topo):
        """Calculate 2D image plot of topography.

        :param pyco_topo: PyCo Topography instance
        :param topo: TopoBank Topography instance
        :return: bokeh plot
        """
        heights = pyco_topo.heights()

        topo_size = pyco_topo.size
        x_range = DataRange1d(start=0, end=topo_size[0], bounds='auto')
        y_range = DataRange1d(start=0, end=topo_size[1], bounds='auto')

        color_mapper = LinearColorMapper(palette="Viridis256", low=heights.min(), high=heights.max())

        TOOLTIPS = [
            ("x", "$x " + topo.size_unit),
            ("y", "$y " + topo.size_unit),
            ("height", "@image " + topo.height_unit),
        ]

        colorbar_width = 40

        aspect_ratio = topo_size[0] / topo_size[1]
        plot_height = 800
        plot_width = int(plot_height * aspect_ratio)

        # from bokeh.models.tools import BoxZoomTool, WheelZoomTool, ZoomInTool, ZoomOutTool, PanTool
        plot = figure(x_range=x_range,
                      y_range=y_range,
                      plot_height=plot_height,
                      plot_width=plot_width,
                      # sizing_mode='scale_both',
                      # match_aspect=True,
                      x_axis_label=f'x ({topo.size_unit})',
                      y_axis_label=f'y ({topo.size_unit})',
                      toolbar_location="above",
                      # tools=[PanTool(),BoxZoomTool(match_aspect=True), "save", "reset"],
                      tooltips=TOOLTIPS)

        plot.xaxis.axis_label_text_font_style = "normal"
        plot.yaxis.axis_label_text_font_style = "normal"

        plot.image([heights], x=0, y=0, dw=topo_size[0], dh=topo_size[1], color_mapper=color_mapper)

        plot.toolbar.logo = None

        colorbar = ColorBar(color_mapper=color_mapper,
                            label_standoff=12, location=(0, 0),
                            width=colorbar_width)
        colorbar.title = f"height ({topo.height_unit})"

        plot.add_layout(colorbar, 'right')

        return plot

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        topo = self.object
        pyco_topo = topo.topography()

        if pyco_topo.dim == 1:
            plot = self.get_1D_plot(pyco_topo, topo)
        elif pyco_topo.dim == 2:
            plot = self.get_2D_plot(pyco_topo, topo)
        else:
            raise Exception(f"Don't know how to display topographies with {pyco_topo.dim} dimensions.")

        script, div = components(plot)
        context['image_plot_script'] = script
        context['image_plot_div'] = div

        return context

class TopographyDeleteView(TopographyAccessMixin, DeleteView):
    model = Topography
    context_object_name = 'topography'
    success_url = reverse_lazy('manager:surface-list')

    def get_success_url(self):
        return reverse('manager:surface-detail', kwargs=dict(pk=self.object.surface.pk))

class SelectedTopographyView(FormMixin, ListView):
    model = Topography
    context_object_name = 'topographies'
    form_class = TopographySelectForm

    def get_queryset(self):
        user = self.request.user

        topography_ids = self.request.GET.get('topographies',[])

        filter_kwargs = dict(
            surface__user=user
        )

        if len(topography_ids) > 0:
            filter_kwargs['id__in'] = topography_ids

        topographies = Topography.objects.filter(**filter_kwargs)

        return topographies


class SurfaceListView(FormMixin, ListView):
    model = Surface
    context_object_name = 'surfaces'
    form_class = TopographySelectForm
    success_url = reverse_lazy('manager:surface-list') # stay on same view

    def get_queryset(self):
        surfaces = Surface.objects.filter(user=self.request.user)
        return surfaces

    def get_initial(self):
        # make sure the form is already filled with earlier selection
        return dict(selection=selection_from_session(self.request.session))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def post(self, request, *args, **kwargs): # TODO is this really needed?
        if not request.user.is_authenticated:
            return HttpResponseForbidden()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):

        # when pressing "select all" button, select all topographies
        # of current user
        if 'select-all' in self.request.POST:
            selection = selection_for_select_all(self.request.user)
        else:
            # take selection from form
            selection = form.cleaned_data.get('selection', [])

        _log.info('Form valid, selection: %s', selection)

        self.request.session['selection'] = tuple(selection)
        messages.info(self.request, "Topography selection saved.")

        # when pressing the analyze button, trigger analysis for
        # all selected topographies
        if 'analyze' in self.request.POST:
            #
            # trigger analysis for all functions
            #
            from topobank.taskapp.tasks import submit_analysis
            from topobank.analysis.models import AnalysisFunction

            auto_analysis_funcs = AnalysisFunction.objects.filter(automatic=True)

            topographies = selected_topographies(self.request)
            for topo in topographies:
                for af in auto_analysis_funcs:
                    submit_analysis(af, topo)

            messages.info(self.request, "Submitted analyses for {} topographies.".format(len(topographies)))

        return super().form_valid(form)


class SurfaceCreateView(CreateView):
    model = Surface
    form_class = SurfaceForm

    def get_initial(self, *args, **kwargs):
        initial = super(SurfaceCreateView, self).get_initial()
        initial = initial.copy()
        initial['user'] = self.request.user
        return initial

    def get_success_url(self):
        return reverse('manager:surface-detail', kwargs=dict(pk=self.object.pk))

class SurfaceDetailView(SurfaceAccessMixin, DetailView):
    model = Surface
    context_object_name = 'surface'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        bw_data = bandwidths_data(self.object.topography_set.all())
        context['bandwidths_data'] = json.dumps(bw_data)
        return context

class SurfaceUpdateView(SurfaceAccessMixin, UpdateView):
    model = Surface
    form_class = SurfaceForm

    def get_initial(self, *args, **kwargs):
        initial = super().get_initial(*args, **kwargs)
        initial = initial.copy()
        initial['user'] = self.request.user
        return initial

    def get_success_url(self):
        return reverse('manager:surface-detail', kwargs=dict(pk=self.object.pk))

class SurfaceDeleteView(SurfaceAccessMixin, DeleteView):
    model = Surface
    context_object_name = 'surface'
    success_url = reverse_lazy('manager:surface-list')
