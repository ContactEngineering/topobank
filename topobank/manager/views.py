from django.shortcuts import render
from django.views.generic import DetailView, ListView, UpdateView, CreateView, DeleteView
from django.urls import reverse

from .models import Topography
from .forms import TopographyForm

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

class TopographyDeleteView(DeleteView):
    model = Topography




