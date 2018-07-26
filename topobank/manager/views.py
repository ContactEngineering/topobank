from django.shortcuts import render, redirect
from django.views.generic import DetailView, ListView, UpdateView, CreateView, DeleteView
from django.urls import reverse, reverse_lazy
from django.core.files.storage import FileSystemStorage, DefaultStorage
from django.conf import settings
from formtools.wizard.views import SessionWizardView
import os.path

from .models import Topography
from .forms import TopographyForm
from .forms import TopographyFileUploadForm, TopographyMetaDataForm
from .utils import TopographyFile

class TopographyCreateWizard(SessionWizardView):
    form_list = [TopographyFileUploadForm, TopographyMetaDataForm]
    template_name = 'manager/topography_wizard.html'
    file_storage = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT,'topographies/wizard'))

    def get_form_initial(self, step):

        initial = {'user': self.request.user}

        if step == '1':
            # provide datafile attribute from previous step
            step0_data = self.get_cleaned_data_for_step('0')

            datafile = step0_data['datafile']
            initial['datafile'] = datafile.file.name

        return self.initial_dict.get(step, initial)

    def get_form_kwargs(self, step=None):

        kwargs = super(TopographyCreateWizard, self).get_form_kwargs(step)

        if step == '1':
            step0_data = self.get_cleaned_data_for_step('0')

            datafile_fname = step0_data['datafile'].file.name
            topofile = TopographyFile(datafile_fname)
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

        return redirect(reverse('manager:detail', kwargs=dict(pk=instance.pk)))

class TopographyCreateView(CreateView):
    model = Topography
    form_class = TopographyForm

    def get_initial(self, *args, **kwargs):
        initial = super(TopographyCreateView, self).get_initial()
        initial = initial.copy()
        initial['user'] = self.request.user
        return initial

    def get_success_url(self):
        return reverse('manager:detail', kwargs=dict(pk=self.object.pk))

class TopographyUpdateView(UpdateView):
    model = Topography
    form_class = TopographyForm

    def get_initial(self, *args, **kwargs):
        initial = super(TopographyUpdateView, self).get_initial()
        initial = initial.copy()
        initial['user'] = self.request.user # TODO reuse code
        return initial

    def get_success_url(self):
        return reverse('manager:detail', kwargs=dict(pk=self.object.pk))
        # TODO check if it is the correct user or add user later (do not send in form)

class TopographyListView(ListView):
    model = Topography
    context_object_name = 'topographies'

    def get_queryset(self):
        topos = Topography.objects.filter(user=self.request.user)
        return topos

class TopographyDetailView(DetailView):
    model = Topography
    context_object_name = 'topography'

    def get_context_data(self, **kwargs):
        context = super(TopographyDetailView, self).get_context_data(**kwargs)

        return context

class TopographyDeleteView(DeleteView):
    model = Topography
    context_object_name = 'topography'
    success_url = reverse_lazy('manager:list')






