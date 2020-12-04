import json
import logging
import os.path
import traceback
import zipfile
from io import BytesIO

import django_tables2 as tables
import numpy as np
import yaml
import textwrap

from bokeh.embed import components
from bokeh.models import DataRange1d, LinearColorMapper, ColorBar, LabelSet, FuncTickFormatter, TapTool, OpenURL
from bokeh.plotting import figure, ColumnDataSource

from django.conf import settings
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.safestring import mark_safe
from django.views.generic import DetailView, UpdateView, CreateView, DeleteView, TemplateView, ListView, FormView
from django.views.generic.edit import FormMixin
from django_tables2 import RequestConfig
from django.contrib.staticfiles.storage import staticfiles_storage

from formtools.wizard.views import SessionWizardView
from guardian.decorators import permission_required_or_403
from guardian.shortcuts import get_users_with_perms, get_objects_for_user, get_anonymous_user
from notifications.signals import notify
from rest_framework.decorators import api_view
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.utils.urls import remove_query_param, replace_query_param
from trackstats.models import Metric, Period

from .forms import TopographyFileUploadForm, TopographyMetaDataForm, TopographyWizardUnitsForm, DEFAULT_LICENSE
from .forms import TopographyForm, SurfaceForm, SurfaceShareForm, SurfacePublishForm
from .models import Topography, Surface, TagModel, \
    NewPublicationTooFastException, LoadTopographyException, PlotTopographyException
from .serializers import SurfaceSerializer, TagSerializer
from .utils import selected_instances, bandwidths_data, get_topography_reader, tags_for_user, get_reader_infos, \
    mailto_link_for_reporting_an_error, current_selection_as_basket_items, filtered_surfaces, \
    filtered_topographies, get_search_term, get_category, get_sharing_status, get_tree_mode
from ..usage_stats.utils import increase_statistics_by_date, increase_statistics_by_date_and_object
from ..users.models import User
from ..users.utils import get_default_group
from ..publication.models import Publication, MAX_LEN_AUTHORS_FIELD

# create dicts with labels and option values for Select tab
CATEGORY_FILTER_CHOICES = {'all': 'All categories',
                           **{cc[0]: cc[1] + " only" for cc in Surface.CATEGORY_CHOICES}}
SHARING_STATUS_FILTER_CHOICES = {
    'all': 'All accessible surfaces',
    'own': 'Only own surfaces',
    'shared': 'Only surfaces shared with you',
    'published': 'Only surfaces published by anyone',
}
TREE_MODE_CHOICES = ['surface list', 'tag tree']

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 10

DEFAULT_SELECT_TAB_STATE = {
    'search_term': '',  # empty string means: no search
    'category': 'all',
    'sharing_status': 'all',
    'tree_mode': 'surface list',
    'page_size': 10,
    'current_page': 1,
    # all these values are the default if no filter has been applied
    # and the page is loaded the first time
}

_log = logging.getLogger(__name__)

surface_view_permission_required = method_decorator(
    permission_required_or_403('manager.view_surface', ('manager.Surface', 'pk', 'pk'))
    # translates to:
    #
    # In order to access, a specific permission is required. This permission
    # is 'view_surface' for a specific surface. Which surface? This is calculated
    # from view argument 'pk' (the last element in tuple), which is used to get a
    # 'manager.Surface' instance (first element in tuple) with field 'pk' with same value as
    # last element in tuple (the view argument 'pk').
    #
    # Or in pseudocode:
    #
    #  s = Surface.objects.get(pk=view.kwargs['pk'])
    #  assert request.user.has_perm('view_surface', s)
)

surface_update_permission_required = method_decorator(
    permission_required_or_403('manager.change_surface', ('manager.Surface', 'pk', 'pk'))
)

surface_delete_permission_required = method_decorator(
    permission_required_or_403('manager.delete_surface', ('manager.Surface', 'pk', 'pk'))
)

surface_share_permission_required = method_decorator(
    permission_required_or_403('manager.share_surface', ('manager.Surface', 'pk', 'pk'))
)

surface_publish_permission_required = method_decorator(
    permission_required_or_403('manager.publish_surface', ('manager.Surface', 'pk', 'pk'))
)


class TopographyPermissionMixin(UserPassesTestMixin):
    redirect_field_name = None

    def has_surface_permissions(self, perms):
        if 'pk' not in self.kwargs:
            return True

        try:
            topo = Topography.objects.get(pk=self.kwargs['pk'])
        except Topography.DoesNotExist:
            raise Http404()

        return all(self.request.user.has_perm(perm, topo.surface)
                   for perm in perms)

    def test_func(self):
        return NotImplementedError()


class TopographyViewPermissionMixin(TopographyPermissionMixin):
    def test_func(self):
        return self.has_surface_permissions(['view_surface'])


class TopographyUpdatePermissionMixin(TopographyPermissionMixin):
    def test_func(self):
        return self.has_surface_permissions(['view_surface', 'change_surface'])


class ORCIDUserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return not self.request.user.is_anonymous


#
# Using a wizard because we need intermediate calculations
#
# There are 3 forms, used in 3 steps (0,1, then 2):
#
# 0: loading of the topography file
# 1: choosing the data source, add measurement date and a description
# 2: adding physical size and units (for data which is not available in the file, for 1D or 2D)
#
# Maybe an alternative would be to use AJAX calls as described here (under "GET"):
#
#  https://sixfeetup.com/blog/making-your-django-templates-ajax-y
#
class TopographyCreateWizard(ORCIDUserRequiredMixin, SessionWizardView):
    form_list = [TopographyFileUploadForm, TopographyMetaDataForm, TopographyWizardUnitsForm]
    template_name = 'manager/topography_wizard.html'
    file_storage = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'topographies/wizard'))

    def get_form_initial(self, step):

        initial = {}

        if step in ['upload']:
            #
            # Pass surface in order to
            # - have it later in done() method (for upload)
            #
            # make sure that the surface exists and belongs to the current user
            try:
                surface = Surface.objects.get(id=int(self.kwargs['surface_id']))
            except Surface.DoesNotExist:
                raise PermissionDenied()
            if not self.request.user.has_perm('change_surface', surface):
                raise PermissionDenied()

            initial['surface'] = surface

        if step in ['metadata', 'units']:
            # provide datafile attribute from first step
            step0_data = self.get_cleaned_data_for_step('upload')
            datafile = step0_data['datafile']
            datafile_format = step0_data['datafile_format']

        if step == 'metadata':
            initial['name'] = os.path.basename(datafile.name)  # the original file name

        if step in ['units']:

            step1_data = self.get_cleaned_data_for_step('metadata')

            toporeader = get_topography_reader(datafile, format=datafile_format)
            channel = int(step1_data['data_source'])
            channel_info = toporeader.channels[channel]

            #
            # Set initial size
            #

            has_2_dim = channel_info.dim == 2
            physical_sizes = channel_info.physical_sizes
            physical_sizes_is_None = (physical_sizes is None) or (physical_sizes == (None,)) \
                                     or (physical_sizes == (None, None))
            # workaround for GH 299 in PyCo and GH 446 in TopoBank

            if physical_sizes_is_None:
                initial_size_x, initial_size_y = None, None
                # both database fields are always set, also for 1D topographies
            elif has_2_dim:
                initial_size_x, initial_size_y = physical_sizes
            else:
                initial_size_x, = physical_sizes  # size is always a tuple
                initial_size_y = None  # needed for database field

            initial['size_x'] = initial_size_x
            initial['size_y'] = initial_size_y

            initial['size_editable'] = physical_sizes_is_None

            initial['is_periodic'] = False  # so far, this is not returned by the readers

            #
            # Set unit
            #
            initial['unit'] = channel_info.info['unit'] \
                if (('unit' in channel_info.info) and (not isinstance(channel_info.info['unit'], tuple))) \
                else None
            initial['unit_editable'] = initial['unit'] is None

            #
            # Set initial height and height unit
            #
            if 'height_scale_factor' in channel_info.info:
                initial['height_scale'] = channel_info.info['height_scale_factor']
            else:
                initial['height_scale'] = 1

            initial['height_scale_editable'] = True  # because of GH 131 we decided to always allow editing

            #
            # Set initial detrend mode
            #
            initial['detrend_mode'] = 'center'

            #
            # Set resolution (only for having the data later in the done method)
            #
            # TODO Can this be passed to done() differently? Creating the reader again later e.g.?
            #
            if has_2_dim:
                initial['resolution_x'], initial['resolution_y'] = channel_info.nb_grid_pts
            else:
                initial['resolution_x'], = channel_info.nb_grid_pts
                initial['resolution_y'] = None

        return initial

    def get_form_kwargs(self, step=None):

        kwargs = super().get_form_kwargs(step)

        if step in ['metadata', 'units']:
            # provide datafile attribute and reader from first step
            step0_data = self.get_cleaned_data_for_step('upload')
            datafile = step0_data['datafile']
            datafile_format = step0_data['datafile_format']
            toporeader = get_topography_reader(datafile, format=datafile_format)

        if step == 'metadata':

            def clean_channel_name(s):
                """Restrict data shown in the dropdown for the channel name.
                :param s: channel name as found in the file
                :return: string without NULL characters, 100 chars maximum
                """
                if s is None:
                    return "(unknown)"
                return s.strip('\0')[:100]

            #
            # Set data source choices based on file contents
            #
            kwargs['data_source_choices'] = [(k, clean_channel_name(channel_info.name)) for k, channel_info in
                                             enumerate(toporeader.channels)
                                             if not (('unit' in channel_info.info)
                                                     and isinstance(channel_info.info['unit'], tuple))]

            #
            # Set surface in order to check for duplicate topography names
            #
            kwargs['surface'] = step0_data['surface']
            kwargs['autocomplete_tags'] = tags_for_user(self.request.user)

        if step in ['units']:
            step1_data = self.get_cleaned_data_for_step('metadata')
            channel = int(step1_data['data_source'])
            channel_info = toporeader.channels[channel]

            has_2_dim = channel_info.dim == 2
            no_sizes_given = channel_info.physical_sizes is None

            # only allow periodic topographies in case of 2 dimension
            kwargs['allow_periodic'] = has_2_dim and no_sizes_given  # TODO simplify in 'no_sizes_given'?
            kwargs['has_size_y'] = has_2_dim  # TODO find common term, now we have 'has_size_y' and 'has_2_dim'

        return kwargs

    def get_context_data(self, form, **kwargs):
        context = super().get_context_data(form, **kwargs)
        surface = Surface.objects.get(id=int(self.kwargs['surface_id']))
        context['surface'] = surface

        redirect_in_get = self.request.GET.get("redirect")
        redirect_in_post = self.request.POST.get("redirect")

        if redirect_in_get:
            context.update({'cancel_action': redirect_in_get})
        elif redirect_in_post:
            context.update({'cancel_action': redirect_in_post})

        #
        # We want to display information about readers directly on upload page
        #
        if self.steps.current == "upload":
            context['reader_infos'] = get_reader_infos()

        #
        # Add context needed for tabs
        #
        context['extra_tabs'] = [
            {
                'title': f"{surface}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Add topography",
                'icon': "plus-square-o",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Adding a topography to surface '{surface.label}'"
            }
        ]

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

        #
        # Check whether given surface can be altered by this user
        #
        surface = d['surface']
        if not self.request.user.has_perm('change_surface', surface):
            raise PermissionDenied()

        #
        # move file to the permanent storage (wizard's files will be deleted)
        #
        new_path = os.path.join(self.request.user.get_media_path(),
                                os.path.basename(d['datafile'].name))
        with d['datafile'].open(mode='rb') as datafile:
            d['datafile'] = default_storage.save(new_path, File(datafile))

        #
        # Set the topography's creator to the current user uploading the file
        #
        d['creator'] = self.request.user

        #
        # create topography in database
        #
        instance = Topography(**d)
        instance.save()
        # we save once so the member variables like "data_source"
        # have the correct type for the next step

        # try to load topography once in order to
        # check whether it can be loaded - we don't want a corrupt
        # topography file in the system:
        topo = Topography.objects.get(id=instance.id)
        try:
            topo.topography()
            # since the topography should be saved in the cache this
            # should not take much extra time
            # TODO can't we determine/save resolution here?!
        except Exception as exc:
            _log.warning("Cannot read topography from file '{}', exception: {}".format(
                d['datafile'], str(exc)
            ))
            _log.warning("Topography {} was created, but will be deleted now.".format(topo.id))
            topo.delete()
            #
            # Redirect to an error page
            #
            return redirect('manager:topography-corrupted', surface_id=surface.id)

        topo.renew_thumbnail()
        topo.renew_analyses()

        #
        # Notify other others with access to the topography
        #
        other_users = get_users_with_perms(topo.surface).filter(~Q(id=self.request.user.id))
        for u in other_users:
            notify.send(sender=self.request.user, verb='create', target=topo, recipient=u,
                        description=f"User '{self.request.user.name}' has created the topography '{topo.name}' " + \
                                    f"in surface '{topo.surface.name}'.",
                        href=reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)))

        #
        # The topography could be correctly loaded and we show a page with details
        #
        return redirect('manager:topography-detail', pk=topo.pk)


class CorruptedTopographyView(TemplateView):
    template_name = "manager/topography_corrupted.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        surface = Surface.objects.get(id=kwargs['surface_id'])
        context['surface'] = surface
        #
        # Add context needed for tabs
        #
        context['extra_tabs'] = [
            {
                'title': f"{surface}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Corrupted File",
                'icon': "flash",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Failure while uploading a new file"
            }
        ]
        return context


class TopographyUpdateView(TopographyUpdatePermissionMixin, UpdateView):
    model = Topography
    form_class = TopographyForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        topo = self.object

        kwargs['has_size_y'] = topo.size_y is not None
        kwargs['autocomplete_tags'] = tags_for_user(self.request.user)

        toporeader = get_topography_reader(topo.datafile, format=topo.datafile_format)

        channel_info = toporeader.channels[topo.data_source]
        has_2_dim = channel_info.dim == 2
        no_sizes_given = channel_info.physical_sizes is None

        kwargs['allow_periodic'] = has_2_dim and no_sizes_given
        return kwargs

    def form_valid(self, form):

        topo = self.object
        user = self.request.user
        notification_msg = f"User {user} changed topography '{topo.name}'. Changed fields: {','.join(form.changed_data)}."

        #
        # If a significant field changed, renew all analyses
        #
        significant_fields = {'size_x', 'size_y', 'unit', 'is_periodic', 'height_scale',
                              'detrend_mode', 'datafile', 'data_source'}
        significant_fields_with_changes = set(form.changed_data).intersection(significant_fields)
        if len(significant_fields_with_changes) > 0:
            _log.info(f"During edit of topography {topo.id} significant fields changed: " + \
                      f"{significant_fields_with_changes}.")
            _log.info("Renewing thumbnail...")
            topo.renew_thumbnail()
            _log.info("Renewing analyses...")
            topo.renew_analyses()
            notification_msg += f"\nBecause significant fields have changed, all analyses are recalculated now."

        #
        # notify other users
        #
        other_users = get_users_with_perms(topo.surface).filter(~Q(id=user.id))
        for u in other_users:
            notify.send(sender=user, verb='change', target=topo,
                        recipient=u,
                        description=notification_msg,
                        href=reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)))

        return super().form_valid(form)

    def get_success_url(self):
        if "save-stay" in self.request.POST:
            return reverse('manager:topography-update', kwargs=dict(pk=self.object.pk))
        else:
            return reverse('manager:topography-detail', kwargs=dict(pk=self.object.pk))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        topo = self.object
        try:
            context['topography_next'] = topo.get_next_by_measurement_date(surface=topo.surface).id
        except Topography.DoesNotExist:
            context['topography_next'] = topo.id
        try:
            context['topography_prev'] = topo.get_previous_by_measurement_date(surface=topo.surface).id
        except Topography.DoesNotExist:
            context['topography_prev'] = topo.id

        #
        # Add context needed for tabs
        #
        context['extra_tabs'] = [
            {
                'title': f"{topo.surface.label}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=topo.surface.pk)),
                'active': False,
                'tooltip': f"Properties of surface '{topo.surface.label}'"
            },
            {
                'title': f"{topo.name}",
                'icon': "file-o",
                'href': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)),
                'active': False,
                'tooltip': f"Properties of topography '{topo.name}'"
            },
            {
                'title': f"Edit Topography",
                'icon': "pencil",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Editing topography '{topo.name}'"
            }
        ]
        return context


class TopographyDetailView(TopographyViewPermissionMixin, DetailView):
    model = Topography
    context_object_name = 'topography'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        topo = self.object

        errors = []  # list of dicts with keys 'message' and 'link'

        plotted = False

        try:
            plot = topo.get_plot()
            plotted = True
        except LoadTopographyException as exc:
            err_message = "Topography '{}' (id: {}) cannot be loaded unexpectedly.".format(
                topo.name, topo.id)
            _log.error(err_message)
            link = mailto_link_for_reporting_an_error(f"Failure loading topography (id: {topo.id})",
                                                      "Showing topography details",
                                                      err_message,
                                                      traceback.format_exc())

            errors.append(dict(message=err_message, link=link))
        except PlotTopographyException as exc:
            err_message = "Topography '{}' (id: {}) cannot be plotted.".format(topo.name, topo.id)
            _log.error(err_message)
            link = mailto_link_for_reporting_an_error(f"Failure plotting topography (id: {topo.id})",
                                                      "Showing topography details",
                                                      err_message,
                                                      traceback.format_exc())

            errors.append(dict(message=err_message, link=link))

        if plotted:
            script, div = components(plot)
            context['image_plot_script'] = script
            context['image_plot_div'] = div

        context['errors'] = errors

        try:
            context['topography_next'] = topo.get_next_by_measurement_date(surface=topo.surface).id
        except Topography.DoesNotExist:
            context['topography_next'] = topo.id
        try:
            context['topography_prev'] = topo.get_previous_by_measurement_date(surface=topo.surface).id
        except Topography.DoesNotExist:
            context['topography_prev'] = topo.id

        #
        # Add context needed for tabs
        #
        context['extra_tabs'] = [
            {
                'title': f"{topo.surface.label}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=topo.surface.pk)),
                'active': False,
                'login_required': False,
                'tooltip': f"Properties of surface '{topo.surface.label}'"
            },
            {
                'title': f"{topo.name}",
                'icon': "file-o",
                'href': self.request.path,
                'active': True,
                'login_required': False,
                'tooltip': f"Properties of topography '{topo.name}'"
            }
        ]

        return context


class TopographyDeleteView(TopographyUpdatePermissionMixin, DeleteView):
    model = Topography
    context_object_name = 'topography'
    success_url = reverse_lazy('manager:select')

    def get_success_url(self):
        user = self.request.user
        topo = self.object
        surface = topo.surface

        link = reverse('manager:surface-detail', kwargs=dict(pk=surface.pk))
        #
        # notify other users
        #
        other_users = get_users_with_perms(surface).filter(~Q(id=user.id))
        for u in other_users:
            notify.send(sender=user, verb="delete",
                        recipient=u,
                        description=f"User '{user.name}' deleted topography '{topo.name}' " + \
                                    f"from surface '{surface.name}'.",
                        href=link)

        return link

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        topo = self.object
        surface = topo.surface
        context['extra_tabs'] = [
            {
                'title': f"{topo.surface.label}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=topo.surface.pk)),
                'active': False,
                'tooltip': f"Properties of surface '{topo.surface.label}'"
            },
            {
                'title': f"{topo.name}",
                'icon': "file-o",
                'href': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)),
                'active': False,
                'tooltip': f"Properties of topography '{topo.name}'"
            },
            {
                'title': f"Delete Topography?",
                'icon': "trash",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Conforming deletion of topography '{topo.name}'"
            }
        ]
        return context


class SelectView(TemplateView):
    template_name = "manager/select.html"

    def dispatch(self, request, *args, **kwargs):
        # count this view event for statistics
        metric = Metric.objects.SEARCH_VIEW_COUNT
        increase_statistics_by_date(metric, period=Period.DAY)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        session = self.request.session

        search_term = get_search_term(self.request)
        if search_term:
            # When searching, we want the default select tab state except for
            # the search term, which is taken from thr request parameters.
            # If not using the default select tab state, this can result
            # in "Load Error!" on the page (#543) because e.g. page 2
            # is not available in the result.
            select_tab_state = DEFAULT_SELECT_TAB_STATE.copy()
            select_tab_state['search_term'] = search_term
        else:
            # .. otherwise keep search term from session variable 'select_tab_state'
            #    and all other state settings
            select_tab_state = session.get('select_tab_state',
                                           default=DEFAULT_SELECT_TAB_STATE.copy())

        # key: tree mode
        context['base_urls'] = {
            'surface list': self.request.build_absolute_uri(reverse('manager:search')),
            'tag tree': self.request.build_absolute_uri(reverse('manager:tag-list')),
        }

        context['category_filter_choices'] = CATEGORY_FILTER_CHOICES.copy()

        if self.request.user.is_anonymous:
            # Anonymous user have only one choice
            context['sharing_status_filter_choices'] = {
                'published': SHARING_STATUS_FILTER_CHOICES['published']
            }
            select_tab_state['sharing_status'] = 'published'  # this only choice should be selected
        else:
            context['sharing_status_filter_choices'] = SHARING_STATUS_FILTER_CHOICES.copy()

        context['select_tab_state'] = select_tab_state.copy()

        # The session needs a default for the state of the select tab
        session['select_tab_state'] = select_tab_state

        return context


class SurfaceCreateView(ORCIDUserRequiredMixin, CreateView):
    model = Surface
    form_class = SurfaceForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['autocomplete_tags'] = tags_for_user(self.request.user)
        return kwargs

    def get_initial(self, *args, **kwargs):
        initial = super(SurfaceCreateView, self).get_initial()
        initial = initial.copy()
        initial['creator'] = self.request.user
        return initial

    def get_success_url(self):
        return reverse('manager:surface-detail', kwargs=dict(pk=self.object.pk))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['extra_tabs'] = [
            {
                'title': f"Create surface",
                'icon': "plus-square-o",
                'href': self.request.path,
                'active': True,
                'tooltip': "Creating a new surface"
            }
        ]
        return context


class SurfaceDetailView(DetailView):
    model = Surface
    context_object_name = 'surface'

    @surface_view_permission_required
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, *kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        surface = self.object
        #
        # Count this event for statistics
        #
        increase_statistics_by_date_and_object(Metric.objects.SURFACE_VIEW_COUNT,
                                               period=Period.DAY, obj=surface)

        #
        # bandwidth data
        #
        bw_data = bandwidths_data(surface.topography_set.all())

        # filter out all entries with errors and display error messages
        bw_data_with_errors = [x for x in bw_data if x['error_message'] is not None]
        bw_data_without_errors = [x for x in bw_data if x['error_message'] is None]

        context['bandwidths_data_with_errors'] = bw_data_with_errors

        #
        # Plot bandwidths with bokeh
        #

        if len(bw_data_without_errors) > 0:

            bw_left = [bw['lower_bound'] for bw in bw_data_without_errors]
            bw_right = [bw['upper_bound'] for bw in bw_data_without_errors]
            bw_center = np.exp((np.log(bw_left)+np.log(bw_right))/2)  # we want to center on log scale
            bw_names = [bw['topography'].name for bw in bw_data_without_errors]
            bw_topography_links = [bw['link'] for bw in bw_data_without_errors]
            bw_thumbnail_links = [reverse('manager:topography-thumbnail',
                                          kwargs=dict(pk=bw['topography'].pk))
                                  for bw in bw_data_without_errors]
            bw_y = range(0, len(bw_data_without_errors))

            bw_source = ColumnDataSource(dict(y=bw_y, left=bw_left, right=bw_right, center=bw_center,
                                              name=bw_names,
                                              topography_link=bw_topography_links,
                                              thumbnail_link=bw_thumbnail_links))

            x_range = (min(bw_left), max(bw_right))

            TOOL_TIPS = """
            <div class="bandwidth-hover-box">
                <img src="@thumbnail_link" height="80" width="80" alt="Thumbnail is missing, sorry">
                </img>
                <span>@name</span>

            </div>
            """

            plot = figure(x_range=x_range,
                          x_axis_label="Bandwidth",
                          x_axis_type="log",
                          sizing_mode='stretch_width',
                          tools=["tap", "hover"],
                          toolbar_location=None,
                          tooltips=TOOL_TIPS)
            hbar_renderer = plot.hbar(y="y", left="left", right="right", height=0.95,
                                      name='bandwidths', source=bw_source)
            hbar_renderer.nonselection_glyph = None  # makes glyph invariant on selection
            plot.yaxis.visible = False
            plot.grid.visible = False
            plot.outline_line_color = None
            plot.xaxis.formatter = FuncTickFormatter(code="return siSuffixMeters(2)(tick)")

            # make clicking a bar going opening a new page
            taptool = plot.select(type=TapTool)
            taptool.callback = OpenURL(url="@topography_link", same_tab=True)

            # include plot into response
            bw_plot_script, bw_plot_div = components(plot)
            context['plot_script'] = bw_plot_script
            context['plot_div'] = bw_plot_div

        #
        # permission data
        #
        ACTIONS = ['view', 'change', 'delete', 'share']  # defines the order of permissions in table

        # surface_perms = get_users_with_perms(self.object, attach_perms=True, only_with_perms_in=potential_perms)
        surface_perms = get_users_with_perms(surface, attach_perms=True)
        # is now a dict of the form
        #  <User: joe>: ['view_surface'], <User: dan>: ['view_surface', 'change_surface']}
        surface_users = sorted(surface_perms.keys(), key=lambda u: u.name if u else '')

        # convert to list of boolean based on list ACTIONS
        #
        # Each table element here is a 2-tuple: (cell content, cell title)
        #
        # The cell content is inserted into the cell.
        # The cell title is shown in a tooltip and can be used in tests.
        #
        surface_perms_table = []
        for user in surface_users:

            is_request_user = user == self.request.user

            if is_request_user:
                user_display_name = "You"
                auxiliary = "have"
            else:
                user_display_name = user.name
                auxiliary = "has"

            # the current user is represented as None, can be displayed in a special way in template ("You")
            row = [(user_display_name, user.get_absolute_url())]  # cell title is used for passing a link here
            for a in ACTIONS:

                perm = a + '_surface'
                has_perm = perm in surface_perms[user]

                cell_title = "{} {}".format(user_display_name, auxiliary)
                if not has_perm:
                    cell_title += "n't"
                cell_title += " the permission to {} this surface".format(a)

                row.append((has_perm, cell_title))

            surface_perms_table.append(row)

        context['permission_table'] = {
            'head': [''] + ACTIONS,
            'body': surface_perms_table
        }

        #
        # Build tab information
        #
        context['extra_tabs'] = [
            {
                'title': surface.label,
                'icon': "diamond",
                'href': self.request.path,
                'active': True,
                'login_required': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            }
        ]

        #
        # Build urls for version selection in dropdown
        #
        def version_label_from_publication(pub):
            return f'Version {pub.version} ({pub.datetime.date()})' if pub else 'Work in progress'

        if surface.is_published:
            original_surface = surface.publication.original_surface
            context['this_version_label'] = version_label_from_publication(surface.publication)
            context['publication_url'] = self.request.build_absolute_uri(surface.publication.get_absolute_url())
        else:
            original_surface = surface
            context['this_version_label'] = version_label_from_publication(None)

        publications = Publication.objects.filter(original_surface=original_surface).order_by('version')
        version_dropdown_items = []

        if self.request.user.has_perm('view_surface', original_surface):
            # Only add link to original surface if user is allowed to view
            version_dropdown_items.append({
                'label': version_label_from_publication(None),
                'surface': original_surface,
            })

        for pub in publications:
            version_dropdown_items.append({
                'label': version_label_from_publication(pub),
                'surface': pub.surface,
            })
        context['version_dropdown_items'] = version_dropdown_items

        version_badge_text = ''
        if surface.is_published:
            if context['this_version_label'] != version_dropdown_items[-1]['label']:
                version_badge_text += 'Newer version available'
        elif len(publications) > 0:
            version_badge_text += 'Published versions available'

        context['version_badge_text'] = version_badge_text

        # add formats to show citations for
        context['citation_flavors'] = [
            ('Text format with link', 'html', False),  # title, flavor, use <pre><code>...</code></pre>
            ('RIS format', 'ris', True),
            ('BibTeX format', 'bibtex', True),
            ('BibLaTeX format', 'biblatex', True),
        ]

        return context


class SurfaceUpdateView(UpdateView):
    model = Surface
    form_class = SurfaceForm

    @surface_update_permission_required
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, *kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['autocomplete_tags'] = tags_for_user(self.request.user)
        return kwargs

    def form_valid(self, form):
        surface = self.object
        user = self.request.user
        notification_msg = f"User {user} changed surface '{surface.name}'. Changed fields: {','.join(form.changed_data)}."

        #
        # notify other users
        #
        other_users = get_users_with_perms(surface).filter(~Q(id=user.id))
        for u in other_users:
            notify.send(sender=user, verb='change', target=surface,
                        recipient=u,
                        description=notification_msg,
                        href=reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)))

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        surface = self.object

        context['extra_tabs'] = [
            {
                'title': f"{surface.label}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Edit surface",
                'icon': "pencil",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Editing surface '{surface.label}'"
            }
        ]

        return context

    def get_success_url(self):
        return reverse('manager:surface-detail', kwargs=dict(pk=self.object.pk))


class SurfaceDeleteView(DeleteView):
    model = Surface
    context_object_name = 'surface'
    success_url = reverse_lazy('manager:select')

    @surface_delete_permission_required
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, *kwargs)

    def get_success_url(self):
        user = self.request.user
        surface = self.object

        link = reverse('manager:select')
        #
        # notify other users
        #
        other_users = get_users_with_perms(surface).filter(~Q(id=user.id))
        for u in other_users:
            notify.send(sender=user, verb="delete",
                        recipient=u,
                        description=f"User '{user.name}' deleted surface '{surface.name}'.",
                        href=link)
        return link

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        surface = self.object
        #
        # Add context needed for tabs
        #
        context['extra_tabs'] = [
            {
                'title': f"{surface.label}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Delete Surface?",
                'icon': "trash",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Conforming deletion of surface '{surface.label}'"
            }
        ]
        return context


class SurfaceShareView(FormMixin, DetailView):
    model = Surface
    context_object_name = 'surface'
    template_name = "manager/surface_share.html"
    form_class = SurfaceShareForm

    @surface_share_permission_required
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, *kwargs)

    def get_success_url(self):
        return reverse('manager:surface-detail', kwargs=dict(pk=self.object.pk))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def form_valid(self, form):

        if 'save' in self.request.POST:
            users = form.cleaned_data.get('users', [])
            allow_change = form.cleaned_data.get('allow_change', False)
            surface = self.object
            for user in users:
                _log.info("Sharing surface {} with user {} (allow change? {}).".format(
                    surface.pk, user.username, allow_change))

                surface.share(user, allow_change=allow_change)

                #
                # Notify user about the shared surface
                #
                notification_message = f"{self.request.user} has shared surface '{surface.name}' with you"
                notify.send(self.request.user, recipient=user,
                            verb="share",  # TODO Does verb follow activity stream defintions?
                            target=surface,
                            public=False,
                            description=notification_message,
                            href=surface.get_absolute_url())

                if allow_change:
                    notify.send(self.request.user, recipient=user, verb="allow change",
                                target=surface, public=False,
                                description=f"""
                                You are allowed to change the surface '{surface.name}' shared by {self.request.user}
                                """,
                                href=surface.get_absolute_url())

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        surface = self.object

        context['extra_tabs'] = [
            {
                'title': f"{surface.label}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Share surface?",
                'icon': "share-alt",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Sharing surface '{surface.label}'"
            }
        ]
        context['surface'] = surface

        return context


class PublicationsTable(tables.Table):
    publication = tables.Column(linkify=True, verbose_name='Surface', order_by='surface__name')
    num_topographies = tables.Column(verbose_name='# Topographies')
    authors = tables.Column(verbose_name="Authors")
    license = tables.Column(verbose_name="License")
    datetime = tables.Column(verbose_name="Publication Date")
    version = tables.Column(verbose_name="Version")

    def render_publication(self, value):
        return value.surface.name

    def render_datetime(self, value):
        return value.date()

    def render_license(self, value, record):
        return mark_safe(f"""
        <a href="{settings.CC_LICENSE_INFOS[value]['description_url']}" target="_blank">
                {record['publication'].get_license_display()}</a>
        """)

    class Meta:
        orderable = True


class PublicationListView(ListView):
    template_name = "manager/publication_list.html"

    def get_queryset(self):
        return Publication.objects.filter(publisher=self.request.user)  # TODO move to publication app?

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)

        #
        # Create table cells
        #
        data = [
            {
                'publication': pub,
                'surface': pub.surface,
                'num_topographies': pub.surface.num_topographies(),
                'authors': pub.authors,
                'license': pub.license,
                'datetime': pub.datetime,
                'version': pub.version
            } for pub in self.get_queryset()
        ]

        context['publication_table'] = PublicationsTable(
            data=data,
            empty_text="You haven't published any surfaces yet.",
            request=self.request)

        return context


class SurfacePublishView(FormView):
    template_name = "manager/surface_publish.html"
    form_class = SurfacePublishForm

    @surface_publish_permission_required
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, *kwargs)

    def _get_surface(self):
        surface_pk = self.kwargs['pk']
        return Surface.objects.get(pk=surface_pk)

    def get_initial(self):
        initial = super().get_initial()
        initial['author_0'] = ''
        initial['num_author_fields'] = 1
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == 'POST':
            # The field 'num_author_fields' may have been increased by
            # Javascript (Vuejs) on the client in order to add new authors.
            # This should be sent to the form in order to know
            # how many fields the form should have and how many author names
            # should be combined. So this is passed here:
            kwargs['num_author_fields'] = int(self.request.POST.get('num_author_fields'))
        return kwargs

    def get_success_url(self):
        return reverse('manager:publications')

    def form_valid(self, form):
        license = form.cleaned_data.get('license')
        authors = form.cleaned_data.get('authors')
        surface = self._get_surface()
        try:
            surface.publish(license, authors)
        except NewPublicationTooFastException as exc:
            return redirect("manager:surface-publication-rate-too-high",
                            pk=surface.pk)

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        surface = self._get_surface()

        context['extra_tabs'] = [
            {
                'title': f"{surface.label}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Publish surface?",
                'icon': "bullhorn",
                'href': self.request.path,
                'active': True,
                'tooltip': f"Publishing surface '{surface.label}'"
            }
        ]
        context['surface'] = surface
        context['max_len_authors_field'] = MAX_LEN_AUTHORS_FIELD
        return context


class PublicationRateTooHighView(TemplateView):
    template_name = "manager/publication_rate_too_high.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['min_seconds'] = settings.MIN_SECONDS_BETWEEN_SAME_SURFACE_PUBLICATIONS

        surface_pk = self.kwargs['pk']
        surface = Surface.objects.get(pk=surface_pk)

        context['extra_tabs'] = [
            {
                'title': f"{surface.label}",
                'icon': "diamond",
                'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
                'active': False,
                'tooltip': f"Properties of surface '{surface.label}'"
            },
            {
                'title': f"Publication rate too high",
                'icon': "flash",
                'href': self.request.path,
                'active': True,
            }
        ]
        return context


class SharingInfoTable(tables.Table):
    surface = tables.Column(linkify=lambda **kwargs: kwargs['record']['surface'].get_absolute_url(),
                            accessor='surface__name')
    num_topographies = tables.Column(verbose_name='# Topographies')
    created_by = tables.Column(linkify=lambda **kwargs: kwargs['record']['created_by'].get_absolute_url(),
                               accessor='created_by__name')
    shared_with = tables.Column(linkify=lambda **kwargs: kwargs['record']['shared_with'].get_absolute_url(),
                               accessor='shared_with__name')
    allow_change = tables.BooleanColumn()
    selected = tables.CheckBoxColumn(attrs={
        'th__input': {'class': 'select-all-checkbox'},
        'td__input': {'class': 'select-checkbox'},
    })

    def __init__(self, *args, **kwargs):
        self._request = kwargs['request']
        super().__init__(*args, **kwargs)

    # def render_surface(self, value):
    #     return value.label

    # def render_created_by(self, value):
    #     return self._render_user(value)

    #def render_shared_with(self, value):
    #    return self._render_user(value)

    #def _render_user(self, user):
    #    if self._request.user == user:
    #        return "You"
    #    return user.name

    class Meta:
        orderable = True


def sharing_info(request):
    if request.user.is_anonymous:
        raise PermissionDenied()

    #
    # Handle POST request if any
    #
    if (request.method == "POST") and ('selected' in request.POST):
        # only do sth if there is a selection

        unshare = 'unshare' in request.POST
        allow_change = 'allow_change' in request.POST

        for s in request.POST.getlist('selected'):
            # decode selection string
            surface_id, share_with_user_id = s.split(',')
            surface_id = int(surface_id)
            share_with_user_id = int(share_with_user_id)

            surface = Surface.objects.get(id=surface_id)
            share_with = User.objects.get(id=share_with_user_id)

            if request.user not in [share_with, surface.creator]:
                # we don't allow to change shares if the request user is not involved
                _log.warning(f"Changing share on surface {surface.id} not allowed for user {request.user}.")
                continue

            if unshare:
                surface.unshare(share_with)
                notify.send(sender=request.user, recipient=share_with, verb='unshare', public=False,
                            description=f"Surface '{surface.name}' from {request.user} is no longer shared with you",
                            href=reverse('manager:sharing-info'))
            elif allow_change and (request.user == surface.creator):  # only allow change for surface creator
                surface.share(share_with, allow_change=True)
                notify.send(sender=request.user, recipient=share_with, verb='allow change', target=surface,
                            public=False,
                            description=f"{request.user} has given you permissions to change surface '{surface.name}'",
                            href=surface.get_absolute_url())
    #
    # Collect information to display
    #
    # Get all surfaces, which are visible, but exclude the published surfaces
    surfaces = get_objects_for_user(request.user, 'view_surface', klass=Surface).filter(publication=None)

    tmp = []
    for s in surfaces:
        surface_perms = get_users_with_perms(s, attach_perms=True)
        # is now a dict of the form
        #  <User: joe>: ['view_surface'], <User: dan>: ['view_surface', 'change_surface']}
        surface_users = sorted(surface_perms.keys(), key=lambda u: u.name if u else '')
        for u in surface_users:
            # Leave out these shares:
            #
            # - share of a user with himself as creator (trivial)
            # - ignore user if anonymous
            # - shares where the request user is not involved
            #
            if (u != s.creator) and (not u.is_anonymous) and \
                ((u == request.user) or (s.creator == request.user)):
                allow_change = ('change_surface' in surface_perms[u])
                tmp.append((s, u, allow_change))

    #
    # Create table cells
    #
    data = [
        {
            'surface': surface,
            'num_topographies': surface.num_topographies(),
            'created_by': surface.creator,
            'shared_with': shared_with,
            'allow_change': allow_change,
            'selected': "{},{}".format(surface.id, shared_with.id),
        } for surface, shared_with, allow_change in tmp
    ]

    #
    # Build table and render result
    #
    sharing_info_table = SharingInfoTable(data=data,
                                          empty_text="No surfaces shared by or with you.",
                                          request=request)

    RequestConfig(request).configure(sharing_info_table)
    # sharing_info_table.order_by('num_topographies')

    return render(request,
                  template_name='manager/sharing_info.html',
                  context={'sharing_info_table': sharing_info_table})


def download_surface(request, surface_id):
    """Returns a file comprised from topographies contained in a surface.

    :param request:
    :param surface_id: surface id
    :return:
    """

    #
    # Check permissions and collect analyses
    #
    try:
        surface = Surface.objects.get(id=surface_id)
    except Surface.DoesNotExist:
        raise PermissionDenied()

    if not request.user.has_perm('view_surface', surface):
        raise PermissionDenied()

    topographies = Topography.objects.filter(surface=surface_id)

    bytes = BytesIO()
    with zipfile.ZipFile(bytes, mode='w') as zf:
        for topography in topographies:
            zf.writestr(topography.name, topography.datafile.read())

        #
        # Add metadata file
        #
        zf.writestr("meta.yml", yaml.dump([topography.to_dict() for topography in topographies]))

        #
        # Add a Readme file
        #
        readme_txt = """
            Contents of this ZIP archive
            ============================
            This archive contains a surface: A collection of individual topography measurements.

            The meta data for the surface and the individual topographies can be found in the
            auxiliary file 'meta.yml'. It is formatted as a [YAML](https://yaml.org/) file.

            Version information
            ===================

            TopoBank: {}
            """.format(settings.TOPOBANK_VERSION)
        if surface.is_published:
            pub = surface.publication
            #
            # Add license information to README file
            #
            license_txt = pub.get_license_display()
            license_info = settings.CC_LICENSE_INFOS[pub.license]
            readme_txt += """
            License information
            ===================

            This surface has been published and the data is licensed under "{}".
            For details about this license see
            - {} (description) and
            - {} (legal code), or
            - file "LICENSE.txt" (legal code).
            """.format(license_txt, license_info['description_url'], license_info['legal_code_url'])
            #
            # Also add license file
            #
            zf.write(staticfiles_storage.path(f"other/{pub.license}-legalcode.txt"), arcname="LICENSE.txt")

        zf.writestr("README.txt", textwrap.dedent(readme_txt))

    # Prepare response object.
    response = HttpResponse(bytes.getvalue(),
                            content_type='application/x-zip-compressed')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format('surface.zip')

    increase_statistics_by_date_and_object(Metric.objects.SURFACE_DOWNLOAD_COUNT,
                                           period=Period.DAY, obj=surface)

    return response


#######################################################################################
# Views for REST interface
#######################################################################################
class SurfaceSearchPaginator(PageNumberPagination):
    page_size = DEFAULT_PAGE_SIZE
    page_query_param = 'page'
    page_size_query_param = 'page_size'
    max_page_size = MAX_PAGE_SIZE

    def get_paginated_response(self, data):

        #
        # Save information about requested data in session
        #
        session = self.request.session

        select_tab_state = session.get('select_tab_state', DEFAULT_SELECT_TAB_STATE.copy())
        # not using the keyword argument "default" here, because in some tests,
        # the session is a simple dict and no real session dict. A simple
        # dict's .get() has no keyword argument 'default', although it can be given
        # as second parameter.

        select_tab_state['search_term'] = get_search_term(self.request)
        select_tab_state['category'] = get_category(self.request)
        select_tab_state['sharing_status'] = get_sharing_status(self.request)
        select_tab_state['tree_mode'] = get_tree_mode(self.request)
        page_size = self.get_page_size(self.request)
        select_tab_state[self.page_size_query_param] = page_size
        select_tab_state['current_page'] = self.page.number
        _log.debug("Setting select tab state set in paginator: %s", select_tab_state)
        session['select_tab_state'] = select_tab_state

        return Response({
            'num_items': self.page.paginator.count,
            'num_pages': self.page.paginator.num_pages,
            'page_range': list(self.page.paginator.page_range),
            'page_urls': list(self.get_page_urls()),
            'current_page': self.page.number,
            'num_items_on_current_page': len(self.page.object_list),
            'page_size': page_size,
            'search_term': select_tab_state['search_term'],
            'category': select_tab_state['category'],
            'sharing_status': select_tab_state['sharing_status'],
            'tree_mode': select_tab_state['tree_mode'],
            'page_results': data
        })

    def get_page_urls(self):
        base_url = self.request.build_absolute_uri()
        urls = []
        for page_no in self.page.paginator.page_range:
            if page_no == 1:
                url = remove_query_param(base_url, self.page_query_param)
            else:
                url = replace_query_param(base_url, self.page_query_param, page_no)
            # always add page size, so requests for other pages have it
            url = replace_query_param(url, self.page_size_query_param, self.get_page_size(self.request))
            urls.append(url)
        return urls


class TagTreeView(ListAPIView):
    """
    Generate tree of tags with surfaces and topographies underneath.
    """
    serializer_class = TagSerializer
    pagination_class = SurfaceSearchPaginator

    def get_queryset(self):
        surfaces = filtered_surfaces(self.request)
        topographies = filtered_topographies(self.request, surfaces)
        return tags_for_user(self.request.user, surfaces, topographies).filter(parent=None)
        # Only top level are collected, the children are added in the serializer.
        #
        # The filtered surfaces and topographies are calculated twice here,
        # I'm not sure how to circumvent this.

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['selected_instances'] = selected_instances(self.request)
        context['request'] = self.request

        surfaces = filtered_surfaces(self.request)
        topographies = filtered_topographies(self.request, surfaces)
        tags = tags_for_user(self.request.user, surfaces, topographies)
        context['tags_for_user'] = tags

        #
        # also pass filtered surfaces and topographies the user has access to
        #
        context['surfaces'] = surfaces
        context['topographies'] = topographies

        return context


class SurfaceListView(ListAPIView):
    """
    List all surfaces with topographies underneath.
    """
    serializer_class = SurfaceSerializer
    pagination_class = SurfaceSearchPaginator

    def get_queryset(self):
        return filtered_surfaces(self.request)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['selected_instances'] = selected_instances(self.request)
        context['request'] = self.request
        return context


def _selection_set(request):
    return set(request.session.get('selection', []))


def _surface_key(pk):  # TODO use such a function everywhere: instance_key_for_selection()
    return 'surface-{}'.format(pk)


def _topography_key(pk):
    return 'topography-{}'.format(pk)


def _tag_key(pk):
    return 'tag-{}'.format(pk)


def set_surface_select_status(request, pk, select_status):
    """Marks the given surface as 'selected' in session or checks this.

        :param request: request
        :param pk: primary key of the surface
        :param select_status: True if surface should be selected, False if it should be unselected
        :return: JSON Response

        The response returns the current selection as suitable for the basket.
    """
    try:
        pk = int(pk)
        surface = Surface.objects.get(pk=pk)
        assert request.user.has_perm('view_surface', surface)
    except (ValueError, Surface.DoesNotExist, AssertionError):
        raise PermissionDenied()  # This should be shown independent of whether the surface exists

    surface_key = _surface_key(pk)
    selection = _selection_set(request)
    is_selected = surface_key in selection

    if request.method == 'POST':
        if select_status:
            # surface should be selected
            selection.add(surface_key)
        elif is_selected:
            selection.remove(surface_key)

        request.session['selection'] = list(selection)

    data = current_selection_as_basket_items(request)
    return Response(data)


@api_view(['POST'])
def select_surface(request, pk):
    """Marks the given surface as 'selected' in session.

    :param request: request
    :param pk: primary key of the surface
    :return: JSON Response

    The response returns the current selection as suitable for the basket.
    """
    return set_surface_select_status(request, pk, True)


@api_view(['POST'])
def unselect_surface(request, pk):
    """Marks the given surface as 'unselected' in session.

    :param request: request
    :param pk: primary key of the surface
    :return: JSON Response

    The response returns the current selection as suitable for the basket.
    """
    return set_surface_select_status(request, pk, False)


def set_topography_select_status(request, pk, select_status):
    """Marks the given topography as 'selected' or 'unselected' in session.

    :param request: request
    :param pk: primary key of the surface
    :param select_status: True or False, True means "mark as selected", False means "mark as unselected"
    :return: JSON Response

    The response returns the current selection as suitable for the basket.
    """
    try:
        pk = int(pk)
        topo = Topography.objects.get(pk=pk)
        assert request.user.has_perm('view_surface', topo.surface)
    except (ValueError, Topography.DoesNotExist, AssertionError):
        raise PermissionDenied()  # This should be shown independent of whether the surface exists

    topography_key = _topography_key(pk)
    selection = _selection_set(request)
    is_selected = topography_key in selection

    if request.method == 'POST':
        if select_status:
            # topography should be selected
            selection.add(topography_key)
        elif is_selected:
            selection.remove(topography_key)

        request.session['selection'] = list(selection)

    data = current_selection_as_basket_items(request)
    return Response(data)


@api_view(['POST'])
def select_topography(request, pk):
    """Marks the given topography as 'selected' in session.

    :param request: request
    :param pk: primary key of the surface
    :return: JSON Response

    The response returns the current selection as suitable for the basket.
    """
    return set_topography_select_status(request, pk, True)


@api_view(['POST'])
def unselect_topography(request, pk):
    """Marks the given topography as 'selected' in session.

    :param request: request
    :param pk: primary key of the surface
    :return: JSON Response

    The response returns the current selection as suitable for the basket.
    """
    return set_topography_select_status(request, pk, False)


def set_tag_select_status(request, pk, select_status):
    """Marks the given tag as 'selected' in session or checks this.

        :param request: request
        :param pk: primary key of the tag
        :param select_status: True if tag should be selected, False if it should be unselected
        :return: JSON Response

        The response returns the current selection as suitable for the basket.
    """
    try:
        pk = int(pk)
        tag = TagModel.objects.get(pk=pk)
    except ValueError:
        raise PermissionDenied()

    if not tag in tags_for_user(request.user):
        raise PermissionDenied()

    tag_key = _tag_key(pk)
    selection = _selection_set(request)
    is_selected = tag_key in selection

    if request.method == 'POST':
        if select_status:
            # tag should be selected
            selection.add(tag_key)
        elif is_selected:
            selection.remove(tag_key)

        request.session['selection'] = list(selection)

    data = current_selection_as_basket_items(request)
    return Response(data)


@api_view(['POST'])
def select_tag(request, pk):
    """Marks the given tag as 'selected' in session.

    :param request: request
    :param pk: primary key of the tag
    :return: JSON Response

    The response returns the current selection as suitable for the basket.
    """
    return set_tag_select_status(request, pk, True)


@api_view(['POST'])
def unselect_tag(request, pk):
    """Marks the given tag as 'unselected' in session.

    :param request: request
    :param pk: primary key of the tag
    :return: JSON Response

    The response returns the current selection as suitable for the basket.
    """
    return set_tag_select_status(request, pk, False)


@api_view(['POST'])
def unselect_all(request):
    """Removes all selections from session.

    :param request: request
    :return: empty list as JSON Response
    """
    request.session['selection'] = []
    return Response([])


def thumbnail(request, pk):
    """Returns image data for a topography thumbail

    Parameters
    ----------
    request

    Returns
    -------
    HTML Response with image data
    """
    try:
        pk = int(pk)
    except ValueError:
        raise Http404()

    try:
        topo = Topography.objects.get(pk=pk)
    except Topography.DoesNotExist:
        raise Http404()

    if not request.user.has_perm('view_surface', topo.surface):
        raise PermissionDenied()

    # okay, we have a valid topography and the user is allowed to see it

    image = topo.thumbnail
    response = HttpResponse(content_type="image/png")
    try:
        response.write(image.file.read())
    except Exception as exc:
        _log.warning("Cannot load thumbnail for topography %d. Reason: %s", topo.id, exc)
        # return some default image so the client gets sth in any case
        with staticfiles_storage.open('images/thumbnail_unavailable.png', mode='rb') as img_file:
            response.write(img_file.read())

    return response


