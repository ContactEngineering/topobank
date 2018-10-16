from django.shortcuts import render, redirect
from django.views.generic import DetailView, ListView, UpdateView, CreateView, DeleteView
from django.urls import reverse, reverse_lazy
from django.core.files.storage import FileSystemStorage, DefaultStorage
from django.conf import settings
from formtools.wizard.views import SessionWizardView
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseForbidden
from django.views.generic.edit import FormMixin, ProcessFormView
from django.contrib import messages

import os.path
import logging

from rest_framework.decorators import api_view
from rest_framework.views import Response

from .models import Topography, Surface
from .forms import TopographyForm, SurfaceForm, TopographySelectForm
from .forms import TopographyFileUploadForm, TopographyMetaDataForm, TopographyUnitsForm
# from .utils import TopographyFile, optimal_unit, selected_topographies
from .utils import TopographyFile, optimal_unit, selected_topographies, selection_from_session, selection_for_select_all

_log = logging.getLogger(__name__)

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

        if step in ['1','2']:
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

            # TODO shorten!

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

            session['initial_size'] = topo.size
            session['initial_size_unit'] = topo.unit
            session['initial_height_scale'] = topo.parent_topography.coeff
            session['detrend_mode'] = topo.detrend_mode

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

        # move file in file system (wizard files will be deleted
        from .models import user_directory_path
        old_path = d['datafile']
        new_path = os.path.join(settings.MEDIA_ROOT, 'topographies',
                                'user_{}'.format(self.request.user.pk),
                                os.path.basename(d['datafile']))
        os.rename(old_path, new_path)

        d['datafile'] = new_path

        # create topography in database
        instance = Topography(**d)
        instance.save()

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

class TopographyUpdateView(UpdateView):
    model = Topography
    form_class = TopographyForm

    def get_initial(self, *args, **kwargs):
        initial = super(TopographyUpdateView, self).get_initial()
        initial = initial.copy()
        initial['user'] = self.request.user # TODO reuse code
        return initial

    def get_success_url(self):
        return reverse('manager:topography-detail', kwargs=dict(pk=self.object.pk))
        # TODO check if it is the correct user or add user later (do not send in form)

class TopographyListView(ListView):
    model = Topography
    context_object_name = 'topographies'

    def get_queryset(self):
        topos = Topography.objects.filter(surface__user=self.request.user)
        return topos

class TopographyDetailView(DetailView):
    model = Topography
    context_object_name = 'topography'

class TopographyDeleteView(DeleteView):
    model = Topography
    context_object_name = 'topography'
    success_url = reverse_lazy('manager:surface-list')

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
        messages.info(self.request, "Topography selection saved: {}".format(self.request.session.get('selection')))

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

class SurfaceDetailView(DetailView):
    model = Surface
    context_object_name = 'surface'

    #def get_context_data(self, **kwargs):
    #    context = super(SurfaceDetailView, self).get_context_data(**kwargs)
    #   context['topographies'] = Topography.objects.filter(surface=self.object)

# def toggle_topography_selection(request, pk):
#     selected_topos = request.session.get('selected_topographies', [])
#     if pk in selected_topos:
#         selected_topos.remove(pk)
#         is_selected = False
#     else:
#         selected_topos.append(pk)
#         is_selected = True
#     request.session['selected_topographies'] = selected_topos
#     return JsonResponse(dict(is_selected=is_selected))
#
# def is_topography_selected(request, pk):
#     selected_topos = request.session.get('selected_topographies', [])
#     is_selected = pk in selected_topos
#     return JsonResponse(is_selected)



