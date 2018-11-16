from django.shortcuts import render, redirect
from django.views.generic import DetailView, ListView, UpdateView, CreateView, DeleteView
from django.urls import reverse, reverse_lazy
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from formtools.wizard.views import SessionWizardView

from django.http import HttpResponseForbidden
from django.views.generic.edit import FormMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages

import json
import os.path
import logging

from .models import Topography, Surface
from .forms import TopographyForm, SurfaceForm, TopographySelectForm
from .forms import TopographyFileUploadForm, TopographyMetaDataForm, TopographyUnitsForm
from .utils import TopographyFile, optimal_unit, \
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


class TopographyCreateWizard(SessionWizardView):
    form_list = [TopographyFileUploadForm, TopographyMetaDataForm, TopographyUnitsForm]
    template_name = 'manager/topography_wizard.html'
    file_storage = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT,'topographies/wizard'))

    def dispatch(self, request, *args, **kwargs):
        if request.POST.get('cancel'):
            return redirect(reverse('manager:surface-list'))
        return super().dispatch(request, *args, **kwargs)

    def get_form_initial(self, step):

        session = self.request.session

        surface_id = int(self.kwargs['surface_id'])

        initial = {'surface': Surface.objects.get(id=surface_id)}

        if step in ['1', '2']:
            # provide datafile attribute from first step
            step0_data = self.get_cleaned_data_for_step('0')

            datafile = step0_data['datafile']
            initial['datafile'] = datafile.file.name # the file name in the upload directory
            initial['name'] = os.path.basename(datafile.name) # the original file name

        if step == '2':
            # provide datafile attribute from previous step
            step1_data = self.get_cleaned_data_for_step('1')

            data_source = step1_data['data_source']
            name = step1_data['name']
            measurement_date = step1_data['measurement_date']

            initial['data_source'] = data_source
            initial['name'] = name
            initial['measurement_date'] = measurement_date

            initial_unit, conversion_factor = optimal_unit(
                session['initial_size'],
                session['initial_size_unit'])

            initial_size_x, initial_size_y = session['initial_size']
            initial_size_x *= conversion_factor
            initial_size_y *= conversion_factor

            initial['size_x'] = int(initial_size_x)
            initial['size_y'] = int(initial_size_y)
            initial['size_unit'] = initial_unit

            initial['height_scale'] = session['initial_height_scale']
            initial['height_unit'] = session['initial_size_unit'] # TODO choose directly from surface?

            initial['detrend_mode'] = session['detrend_mode']


        return self.initial_dict.get(step, initial)

    def get_form_kwargs(self, step=None):

        kwargs = super(TopographyCreateWizard, self).get_form_kwargs(step)

        if step in ['1', '2']:
            step0_data = self.get_cleaned_data_for_step('0')

            datafile_fname = step0_data['datafile'].file.name

            #
            # Set good default based on file contents
            #
            topofile = TopographyFile(datafile_fname)

        if step == '1':
            kwargs['data_source_choices'] = [(k, ds) for k, ds in
                                             enumerate(topofile.data_sources)]

        elif step == '2':
            step1_data = self.get_cleaned_data_for_step('1')

            topo = topofile.topography(int(step1_data['data_source']))

            session = self.request.session

            if topo.size is None:
                session['initial_size'] = topo.shape
            else:
                session['initial_size'] = topo.size
            session['initial_size_unit'] = topo.unit
            session['initial_height_scale'] = topo.parent_topography.coeff
            session['detrend_mode'] = topo.detrend_mode
            session['size_x'], session['size_y'] = topo.resolution

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
        """Finally use form data when finished the wizard

        :param form_list:
        :param kwargs:
        :return:
        """
        # collect all data from forms
        d = dict((k, v) for form in form_list for k, v in form.cleaned_data.items())

        # move file in file system (wizard files will be deleted)
        from .models import user_directory_path
        old_path = d['datafile']
        new_path = os.path.join(self.request.user.get_media_path(),
                                os.path.basename(d['datafile']))
        os.rename(old_path, new_path)

        d['datafile'] = new_path

        d['resolution_x'] = self.request.session['size_x']
        d['resolution_y'] = self.request.session['size_y']

        # create topography in database
        instance = Topography(**d)
        instance.save()

        # put image creation tasks in queue
        instance.submit_images_creation()  # TODO create notification

        # put automated analysis in queue
        instance.submit_automated_analyses() # TODO create notification

        return redirect(reverse('manager:topography-detail', kwargs=dict(pk=instance.pk)))

class TopographyCreateView(CreateView):
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

    def get_success_url(self):
        self.object.submit_images_creation() # TODO this is only needed if image would change
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
