import yaml
import zipfile
import traceback
from io import BytesIO

from django.shortcuts import redirect, render
from django.views.generic import DetailView, ListView, UpdateView, CreateView, DeleteView, TemplateView
from django.urls import reverse, reverse_lazy
from django.core.files.storage import FileSystemStorage
from django.core.files.storage import default_storage
from django.core.files import File
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.http import HttpResponse, Http404, JsonResponse
from django.views.generic.edit import FormMixin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.utils.decorators import method_decorator
from django.db.models import Q

from formtools.wizard.views import SessionWizardView
from guardian.decorators import permission_required_or_403
from guardian.shortcuts import assign_perm, get_users_with_perms, get_objects_for_user
from notifications.signals import notify
import django_tables2 as tables
from django_tables2 import RequestConfig
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import DataRange1d, LinearColorMapper, ColorBar

from trackstats.models import Metric, Period

from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.utils.urls import remove_query_param, replace_query_param
from django_filters import rest_framework as filters

import numpy as np
import json
import os.path
import logging

from .models import Topography, Surface, TagModel
from .forms import TopographyForm, SurfaceForm, SurfaceShareForm
from .forms import TopographyFileUploadForm, TopographyMetaDataForm, TopographyWizardUnitsForm
from .utils import selected_instances, bandwidths_data, surfaces_for_user, \
    get_topography_reader, tags_for_user, get_reader_infos
from .serializers import SurfaceSerializer, TopographySerializer, TagSerializer
from .utils import mailto_link_for_reporting_an_error, current_selection_as_basket_items
from .filters import SurfaceFilter, TagModelFilter

from ..usage_stats.utils import increase_statistics_by_date
from ..users.models import User

MAX_NUM_POINTS_FOR_SYMBOLS_IN_LINE_SCAN_PLOT = 100

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


class TopographyPermissionMixin(UserPassesTestMixin):
    redirect_field_name = None

    def has_surface_permissions(self, perms):
        if 'pk' not in self.kwargs:
            return True

        try:
            topo = Topography.objects.get(pk=self.kwargs['pk'])
        except Topography.DoesNotExist:
            raise Http404()
        return all(self.request.user.has_perm(perm, topo.surface) for perm in perms)

    def test_func(self):
        return NotImplementedError()


class TopographyViewPermissionMixin(TopographyPermissionMixin):
    def test_func(self):
        return self.has_surface_permissions(['view_surface'])


class TopographyUpdatePermissionMixin(TopographyPermissionMixin):
    def test_func(self):
        return self.has_surface_permissions(['view_surface', 'change_surface'])


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
class TopographyCreateWizard(SessionWizardView):
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
        context['active_tab'] = 'extra-tab-2'
        context['extra_tab_1_data'] = {
            'title': f"Surface <b>{surface.name}</b>",
            'icon': "fa-diamond",
            'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
        }
        context['extra_tab_2_data'] = {
            'title': f"Add topography to Surface <b>{surface.name}</b>",
            'icon': "fa-plus-square-o",
            'href': self.request.path,
        }

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
        context['surface'] = Surface.objects.get(id=kwargs['surface_id'])
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
                      f"{significant_fields_with_changes}. Renewing analyses...")
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
        context['active_tab'] = 'extra-tab-3'
        context['extra_tab_1_data'] = {
            'title': f"Surface <b>{topo.surface.name}</b>",
            'icon': "fa-diamond",
            'href': reverse('manager:surface-detail', kwargs=dict(pk=topo.surface.pk)),
        }
        context['extra_tab_2_data'] = {
            'title': f"Topography <b>{topo.name}</b>",
            'icon': "fa-file-o",
            'href': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)),
        }
        context['extra_tab_3_data'] = {
            'title': f"Edit Topography <b>{topo.name}</b>",
            'icon': "fa-pencil",
            'href': self.request.path,
        }

        return context


class TopographyDetailView(TopographyViewPermissionMixin, DetailView):
    model = Topography
    context_object_name = 'topography'

    def get_1D_plot(self, pyco_topo, topo):
        """Calculate 1D line plot of topography (line scan).

        :param pyco_topo: PyCo Topography instance
        :param topo: TopoBank Topography instance
        :return: bokeh plot
        """
        x, y = pyco_topo.positions_and_heights()

        x_range = DataRange1d(bounds='auto')
        y_range = DataRange1d(bounds='auto')

        TOOLTIPS = """
            <style>
                .bk-tooltip>div:not(:first-child) {{display:none;}}
                td.tooltip-varname {{ text-align:right; font-weight: bold}}
            </style>

            <table>
              <tr>
                <td class="tooltip-varname">x</td>
                <td>:</td>
                <td>@x {}</td>
              </tr>
              <tr>
                <td class="tooltip-varname">height</td>
                <td>:</td>
                <td >@y {}</td>
              </tr>
            </table>
        """.format(topo.unit, topo.unit)

        plot = figure(x_range=x_range, y_range=y_range,
                      x_axis_label=f'x ({topo.unit})',
                      y_axis_label=f'height ({topo.unit})',
                      toolbar_location="above",
                      tooltips=TOOLTIPS)

        show_symbols = y.shape[0] <= MAX_NUM_POINTS_FOR_SYMBOLS_IN_LINE_SCAN_PLOT

        plot.line(x, y)
        if show_symbols:
            plot.circle(x, y)

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

        topo_size = pyco_topo.physical_sizes
        # x_range = DataRange1d(start=0, end=topo_size[0], bounds='auto')
        # y_range = DataRange1d(start=0, end=topo_size[1], bounds='auto')
        x_range = DataRange1d(start=0, end=topo_size[0], bounds='auto', range_padding=5)
        y_range = DataRange1d(start=topo_size[1], end=0, flipped=True, range_padding=5)

        color_mapper = LinearColorMapper(palette="Viridis256", low=heights.min(), high=heights.max())

        TOOLTIPS = [
            ("x", "$x " + topo.unit),
            ("y", "$y " + topo.unit),
            ("height", "@image " + topo.unit),
        ]

        colorbar_width = 50

        aspect_ratio = topo_size[0] / topo_size[1]
        frame_height = 500
        frame_width = int(frame_height * aspect_ratio)

        if frame_width > 1200:  # rule of thumb, scale down if too wide
            frame_width = 1200
            frame_height = int(frame_width / aspect_ratio)

        plot = figure(x_range=x_range,
                      y_range=y_range,
                      frame_width=frame_width,
                      frame_height=frame_height,
                      # sizing_mode='scale_both',
                      # aspect_ratio=aspect_ratio,
                      match_aspect=True,
                      x_axis_label=f'x ({topo.unit})',
                      y_axis_label=f'y ({topo.unit})',
                      toolbar_location="above",
                      # tools=[PanTool(),BoxZoomTool(match_aspect=True), "save", "reset"],
                      tooltips=TOOLTIPS)

        plot.xaxis.axis_label_text_font_style = "normal"
        plot.yaxis.axis_label_text_font_style = "normal"

        # we need to rotate the height data in order to be compatible with image in Gwyddion
        plot.image([np.rot90(heights)], x=0, y=topo_size[1],
                   dw=topo_size[0], dh=topo_size[1], color_mapper=color_mapper)
        # the anchor point of (0,topo_size[1]) is needed because the y range is flipped
        # in order to have the origin in upper left like in Gwyddion

        plot.toolbar.logo = None

        colorbar = ColorBar(color_mapper=color_mapper,
                            label_standoff=12,
                            location=(0, 0),
                            width=colorbar_width,
                            title=f"height ({topo.unit})")

        plot.add_layout(colorbar, 'right')

        return plot

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        topo = self.object

        errors = []  # list of dicts with keys 'message' and 'link'

        loaded = False
        plotted = False

        try:
            pyco_topo = topo.topography()
            loaded = True
        except Exception as exc:
            err_message = "Topography '{}' (id: {}) cannot be loaded unexpectedly.".format(topo.name, topo.id)
            _log.error(err_message)
            link = mailto_link_for_reporting_an_error(f"Failure loading topography (id: {topo.id})",
                                                      "Image plot for topography",
                                                      err_message,
                                                      traceback.format_exc())

            errors.append(dict(message=err_message, link=link))

        if loaded:
            if pyco_topo.dim == 1:
                plot = self.get_1D_plot(pyco_topo, topo)
                plotted = True
            elif pyco_topo.dim == 2:
                plot = self.get_2D_plot(pyco_topo, topo)
                plotted = True
            else:
                err_message = f"Don't know how to display topographies with {pyco_topo.dim} dimensions."
                link = mailto_link_for_reporting_an_error(f"Invalid dimensions for topography (id: {topo.id})",
                                                          "Image plot for topography",
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
        context['active_tab'] = 'extra-tab-2'
        context['extra_tab_1_data'] = {
            'title': f"Surface <b>{topo.surface.name}</b>",
            'icon': "fa-diamond",
            'href': reverse('manager:surface-detail', kwargs=dict(pk=topo.surface.pk)),
        }
        context['extra_tab_2_data'] = {
            'title': f"Topography <b>{topo.name}</b>",
            'icon': "fa-file-o",
            'href': self.request.path,
        }

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
        context['active_tab'] = 'extra-tab-3'
        context['extra_tab_1_data'] = {
            'title': f"Surface <b>{surface.name}</b>",
            'icon': "fa-diamond",
            'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
        }
        context['extra_tab_2_data'] = {
            'title': f"Topography <b>{topo.name}</b>",
            'icon': "fa-file-o",
            'href': reverse('manager:topography-detail', kwargs=dict(pk=topo.pk)),
        }
        context['extra_tab_3_data'] = {
            'title': f"Delete Topography <b>{topo.name}</b>?",
            'icon': "fa-trash",
            'href': self.request.path,
        }

        return context


class SelectView(TemplateView):
    template_name = "manager/surface_list.html"  # TODO rename to select.html

    def dispatch(self, request, *args, **kwargs):
        # count this view event for statistics

        metric = Metric.objects.SEARCH_VIEW_COUNT
        increase_statistics_by_date(metric, period=Period.DAY)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_term = self.request.GET.get('search')
        category = self.request.GET.get('category')
        sharing_status = self.request.GET.get('sharing_status')

        if search_term:
            search_term = search_term.strip()
        if category and category not in [ 'all', 'exp', 'sim', 'dum']:  # TODO deduce automatically
            raise PermissionDenied()
        if sharing_status and sharing_status not in [ 'all', 'own', 'shared']:
            raise PermissionDenied

        context['base_search_url_surface_tree'] = reverse('manager:search')
        context['base_search_url_tag_tree'] = reverse('manager:tag-list')
        context['search_term'] = search_term

        # #
        # # Collect data for trees
        # #
        # surfaces = surfaces_for_user(self.request.user)
        #
        # # Filter for category and status
        # if category:
        #     surfaces = surfaces.filter(category=category)
        # if sharing_status == 'own':
        #     surfaces = surfaces.filter(creator=self.request.user)
        # elif sharing_status == 'shared':
        #     surfaces = surfaces.filter(~Q(creator=self.request.user))
        # topographies = Topography.objects.filter(surface__in=surfaces)
        #
        # # Filter for search term
        # if search_term:
        #     topographies = topographies.filter(
        #         Q(name__icontains=search_term) | Q(description__icontains=search_term))  # TODO tags missing
        #     surfaces = surfaces.filter(
        #         Q(name__icontains=search_term) | Q(description__icontains=search_term))  # TODO tags missing
        #
        # # matching topographies should be accessible via their surface as well as all topographies
        # # from matching surfaces
        # # surfaces_for_surface_tree = surfaces.union(t.surface for t in topographies)
        #
        #
        # tags = tags_for_user(self.request.user).filter(parent=None).order_by('label')  # only top level
        # surfaces_without_tags = surfaces.filter(tags=None)
        # topographies_without_tags = topographies.filter(tags=None)
        #
        #
        #
        #
        # #
        # # Prepare tree data for tree with surfaces at top level
        # #
        # serializer_context = dict(request=self.request,
        #                           selected_instances=selected_instances(self.request))
        #
        # surface_serializer = SurfaceSerializer(context=serializer_context)
        # surface_tree_data = [ surface_serializer.to_representation(s) for s in surfaces]
        #
        # context['surface_tree_data'] = json.dumps(surface_tree_data)
        # # TODO append _json to name
        #
        # #
        # # Prepare tree data for tree with tags at top level
        # #
        # topography_serializer = TopographySerializer(context=serializer_context)
        #
        # tag_serializer_context = serializer_context.copy()
        # tag_serializer_context['surfaces'] = surfaces
        # tag_serializer_context['topographies'] = topographies
        # tag_serializer = TagSerializer(context=tag_serializer_context)
        # serialized_tags = [ tag_serializer.to_representation(t) for t in tags ]
        #
        # serialized_surfaces_without_tags = [surface_serializer.to_representation(s)
        #                                     for s in surfaces_without_tags]
        #
        # serialized_topographies_without_tags = [topography_serializer.to_representation(t)
        #                                         for t in topographies_without_tags]
        #
        # serialized_tags.append(dict(
        #     type='tag',
        #     title='(untagged surfaces)',
        #     pk=None,
        #     name=None,
        #     folder=True,
        #     selected=False,
        #     children=serialized_surfaces_without_tags
        # ))
        # serialized_tags.append(dict(
        #     type='tag',
        #     title='(untagged topographies)',
        #     pk=None,
        #     name=None,
        #     folder=True,
        #     selected=False,
        #     children=serialized_topographies_without_tags
        # ))
        #
        # context['tag_tree_data'] = json.dumps(serialized_tags)
        return context


class SurfaceCreateView(CreateView):
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
        context['active_tab'] = 'extra-tab-1'

        context['extra_tab_1_data'] = {
            'title': f"Create surface",
            'icon': "fa-plus-square-o",
            'href': self.request.path,
        }
        return context


class SurfaceDetailView(DetailView):
    model = Surface
    context_object_name = 'surface'

    @surface_view_permission_required
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, *kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        #
        # bandwidth data
        #
        bw_data = bandwidths_data(self.object.topography_set.all())

        # filter out all entries with errors and display error messages
        bw_data_with_errors = [x for x in bw_data if x['error_message'] is not None]
        bw_data_without_errors = [x for x in bw_data if x['error_message'] is None]

        context['bandwidths_data_without_errors'] = json.dumps(bw_data_without_errors)
        context['bandwidths_data_with_errors'] = bw_data_with_errors

        #
        # permission data
        #
        ACTIONS = ['view', 'change', 'delete', 'share']  # defines the order of permissions in table

        # surface_perms = get_users_with_perms(self.object, attach_perms=True, only_with_perms_in=potential_perms)
        surface_perms = get_users_with_perms(self.object, attach_perms=True)
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
                auxilliary = "have"
            else:
                user_display_name = user.name
                auxilliary = "has"

            # the current user is represented as None, can be displayed in a special way in template ("You")
            row = [(user_display_name, user.get_absolute_url())]  # cell title is used for passing a link here
            for a in ACTIONS:

                perm = a + '_surface'
                has_perm = perm in surface_perms[user]

                cell_title = "{} {}".format(user_display_name, auxilliary)
                if not has_perm:
                    cell_title += "n't"
                cell_title += " the permission to {} this surface".format(a)

                row.append((has_perm, cell_title))

            surface_perms_table.append(row)

        context['permission_table'] = {
            'head': [''] + ACTIONS,
            'body': surface_perms_table
        }

        context['extra_tab_1_data'] = {
            'title': f"Surface <b>{self.object.name}</b>",
            'icon': "fa-diamond",
            'href': self.request.path,
        }

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

        context['active_tab'] = 'extra-tab-2'
        context['extra_tab_1_data'] = {
            'title': f"Surface <b>{surface.name}</b>",
            'icon': "fa-diamond",
            'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
        }
        context['extra_tab_2_data'] = {
            'title': f"Edit surface <b>{surface.name}</b>",
            'icon': "fa-pencil",
            'href': self.request.path,
        }

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
        context['active_tab'] = 'extra-tab-2'
        context['extra_tab_1_data'] = {
            'title': f"Surface <b>{surface.name}</b>",
            'icon': "fa-diamond",
            'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
        }
        context['extra_tab_2_data'] = {
            'title': f"Delete Surface <b>{surface.name}</b>?",
            'icon': "fa-trash",
            'href': self.request.path,
        }
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
                assign_perm('view_surface', user, self.object)

                notification_message = f"{self.request.user} has shared surface '{surface.name}' with you"
                notify.send(self.request.user, recipient=user,
                            verb="share",  # TODO Does verb follow activity stream defintions?
                            target=surface,
                            public=False,
                            description=notification_message,
                            href=surface.get_absolute_url())

                if allow_change:
                    assign_perm('change_surface', user, surface)
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

        context['active_tab'] = 'extra-tab-2'
        context['extra_tab_1_data'] = {
            'title': f"Surface <b>{surface.name}</b>",
            'icon': "fa-diamond",
            'href': reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)),
        }
        context['extra_tab_2_data'] = {
            'title': f"Share surface <b>{surface.name}</b>",
            'icon': "fa-share-alt",
            'href': self.request.path,
        }

        return context


class SharingInfoTable(tables.Table):
    surface = tables.Column(linkify=True)
    num_topographies = tables.Column(verbose_name='# Topographies')
    created_by = tables.Column(linkify=True)
    shared_with = tables.Column(linkify=True)
    allow_change = tables.BooleanColumn()
    selected = tables.CheckBoxColumn(attrs={
        'th__input': {'class': 'select-all-checkbox'},
        'td__input': {'class': 'select-checkbox'},
    })

    def __init__(self, *args, **kwargs):
        self._request = kwargs['request']
        super().__init__(*args, **kwargs)

    def render_surface(self, value):
        return value.name

    def render_created_by(self, value):
        return self._render_user(value)

    def render_shared_with(self, value):
        return self._render_user(value)

    def _render_user(self, user):
        if self._request.user == user:
            return "You"
        return user.name

    class Meta:
        orderable = False  # ordering does not work with custom columns


def sharing_info(request):
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
    surfaces = get_objects_for_user(request.user, 'view_surface', klass=Surface)

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
            # - shares where the request user is not involved
            #
            if (u != s.creator) and ((u == request.user) or (s.creator == request.user)):
                allow_change = ('change_surface' in surface_perms[u])
                tmp.append((s, u, allow_change))

    #
    # Create table cells
    #
    data = [
        {
            'surface': surface,
            'num_topographies': surface.num_topographies,
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
    user = request.user
    if not user.is_authenticated:
        raise PermissionDenied()

    try:
        surface = Surface.objects.get(id=surface_id)
    except Surface.DoesNotExist:
        raise PermissionDenied()

    if not user.has_perm('view_surface', surface):
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
        zf.writestr("README.txt", \
                    """
Contents of this ZIP archive
============================
This archive contains a surface: A collection of individual topography measurements.

The meta data for the surface and the individual topographies can be found in the
auxiliary file 'meta.yml'. It is formatted as a [YAML](https://yaml.org/) file.

Version information
===================

TopoBank: {}
""".format(settings.TOPOBANK_VERSION))

    # Prepare response object.
    response = HttpResponse(bytes.getvalue(),
                            content_type='application/x-zip-compressed')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format('surface.zip')

    return response


#######################################################################################
# Views for REST interface
#######################################################################################
class SurfaceSearchPaginator(PageNumberPagination):
    page_size = 8
    page_query_param = 'page'

    def get_paginated_response(self, data):
        return Response({
            'next_page_url': self.get_next_link(),  # TODO remove?
            'prev_page_url': self.get_previous_link(),
            'num_items': self.page.paginator.count,
            'num_pages': self.page.paginator.num_pages,
            'page_range': list(self.page.paginator.page_range),
            'page_urls': list(self.get_page_urls()),
            'current_page': self.page.number,
            'num_items_on_current_page': len(self.page.object_list),
            'page_size': self.page_size,
            'page_results': data
        })

    def get_page_urls(self):
        base_url = self.request.build_absolute_uri()
        urls = []
        for page_no in self.page.paginator.page_range:
            url = base_url
            if page_no == 1:
                url = remove_query_param(base_url, self.page_query_param)
            else:
                url = replace_query_param(base_url, self.page_query_param, page_no)
            urls.append(url)
        return urls


class TagTreeView(ListAPIView):
    """
    Generate tree of tags with surfaces and topographies underneath.
    """
    serializer_class = TagSerializer
    pagination_class = SurfaceSearchPaginator
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = TagModelFilter

    def get_queryset(self):
        return tags_for_user(self.request.user).filter(parent=None).order_by('label')  # only top level

    def list(self, request, *args, **kwargs):
        response = super().list(request, args, kwargs)
        # Add extra data to response.data for an empty tag
        context = self.get_serializer_context()
        surface_serializer = SurfaceSerializer(context=context)
        topography_serializer = TopographySerializer(context=context)

        surfaces_without_tags = context['surfaces'].filter(tags=None)
        topographies_without_tags = context['topographies'].filter(tags=None)

        serialized_surfaces_without_tags = [surface_serializer.to_representation(s)
                                            for s in surfaces_without_tags]

        serialized_topographies_without_tags = [topography_serializer.to_representation(t)
                                                for t in topographies_without_tags]

        results = response.data['page_results']

        results.append(dict(
            type='tag',
            title='(untagged surfaces)',
            pk=None,
            name=None,
            folder=True,
            selected=False,
            checkbox=False,
            children=serialized_surfaces_without_tags,
            urls=dict(select=None, unselect=None),
        ))
        results.append(dict(
            type='tag',
            title='(untagged topographies)',
            pk=None,
            name=None,
            folder=True,
            selected=False,
            checkbox=False,
            children=serialized_topographies_without_tags,
            urls=dict(select=None, unselect=None),
        ))

        return response

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['selected_instances'] = selected_instances(self.request)
        context['request'] = self.request
        surfaces = surfaces_for_user(self.request.user)
        context['tags_for_user'] = tags_for_user(self.request.user, surfaces)

        #
        # also pass all surfaces and topographies the user has access to
        #
        context['surfaces'] = surfaces
        context['topographies'] = Topography.objects.filter(surface__in=surfaces)
        return context


class SurfaceListView(ListAPIView):
    """
    List all surfaces with topographies underneath.
    """
    serializer_class = SurfaceSerializer
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = SurfaceFilter
    pagination_class = SurfaceSearchPaginator

    def get_queryset(self):
        # from django.db.models import Prefetch
        #
        # search_term = self.request.GET.get('search', default='')
        #
        # return surfaces_for_user(self.request.user).prefetch_related(
        #     Prefetch('topography_set', queryset=Topography.objects.filter(Q(name__icontains=search_term) | Q(description__icontains=search_term)),
        #              to_attr='filtered_topographies')
        # )

        return surfaces_for_user(self.request.user)

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
        user = request.user
        assert user.has_perm('view_surface', surface)
    except:
        raise PermissionDenied()  # This should be shown independent of whether the surface exists

    surface_key = _surface_key(pk)
    selection = _selection_set(request)
    is_selected = surface_key in selection

    if request.method == 'POST':
        # remove all explicitly selected topographies from this surface
        for t in surface.topography_set.all():
            topo_key = _topography_key(t.pk)
            if topo_key in selection:
                selection.remove(topo_key)

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
        user = request.user
        assert user.has_perm('view_surface', topo.surface)
    except:
        raise PermissionDenied()  # This should be shown independent of whether the surface exists

    topography_key = _topography_key(pk)
    surface_key = _surface_key(topo.surface.pk)
    selection = _selection_set(request)
    is_selected = topography_key in selection
    is_surface_selected = surface_key in selection

    if request.method == 'POST':

        if select_status:
            # topography should be selected

            if is_surface_selected:
                pass  # is already selected implicitly
            else:
                # check if all other topographies are selected - if yes,
                # remove those and add surface as selection
                other_topo_keys_in_surface = [_topography_key(t.pk) for t in topo.surface.topography_set.all()
                                              if t != topo]

                if all(k in selection for k in other_topo_keys_in_surface):
                    for k in other_topo_keys_in_surface:
                        selection.remove(k)
                    selection.add(_surface_key(topo.surface.pk))
                else:
                    selection.add(topography_key)
        else:
            # topography should be unselected

            # if surface is selected, remove this selection but add all other topographies instead
            if is_surface_selected:
                selection.remove(surface_key)
                for t in topo.surface.topography_set.all():
                    if t != topo:
                        selection.add(_topography_key(t.pk))

            # if topography is explicitly selected, remove it
            if is_selected:
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
        # tag = TagModel.objects.get(pk=pk)
        # TODO Check if user is select/unselect tag?
    except ValueError:
        raise PermissionDenied()  # This should be shown independent of whether the tag exists

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

