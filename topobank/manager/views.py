import logging
import os.path
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.models import Case, F, Prefetch, Q, When
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect
from django.utils.text import slugify
from guardian.shortcuts import assign_perm, get_users_with_perms, remove_perm
from notifications.signals import notify
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from trackstats.models import Metric, Period

from ..supplib.versions import get_versions
from ..taskapp.utils import run_task
from ..usage_stats.utils import increase_statistics_by_date_and_object
from ..users.models import User
from .containers import write_surface_container
from .models import Property, Surface, Tag, Topography, topography_datafile_path
from .permissions import ObjectPermissions, ParentObjectPermissions
from .serializers import PropertySerializer, SurfaceSerializer, TagSerializer, TopographySerializer
from .tasks import import_container_from_url
from .utils import api_to_guardian, get_upload_instructions

_log = logging.getLogger(__name__)


class PropertyViewSet(mixins.CreateModelMixin,
                      mixins.RetrieveModelMixin,
                      mixins.UpdateModelMixin,
                      mixins.DestroyModelMixin,
                      viewsets.GenericViewSet):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticatedOrReadOnly, ParentObjectPermissions]


class TagViewSet(mixins.RetrieveModelMixin,
                 viewsets.GenericViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]


class SurfaceViewSet(mixins.CreateModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     mixins.DestroyModelMixin,
                     viewsets.GenericViewSet):
    queryset = Surface.objects.prefetch_related(
        Prefetch('topography_set', queryset=Topography.objects.order_by('name')),
        Prefetch('properties', queryset=Property.objects.order_by('id')))
    serializer_class = SurfaceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, ObjectPermissions]

    def _notify(self, instance, verb):
        user = self.request.user
        other_users = get_users_with_perms(instance).filter(~Q(id=user.id))
        for u in other_users:
            notify.send(sender=user, verb=verb, recipient=u,
                        description=f"User '{user.name}' {verb}d digital surface twin '{instance.name}'.")

    def perform_create(self, serializer):
        # Set creator to current user when creating a new surface
        instance = serializer.save(creator=self.request.user)

        # We now have an id, set name if missing
        if 'name' not in serializer.data or serializer.data['name'] == '':
            instance.name = f'Digital surface twin #{instance.id}'
            instance.save()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._notify(serializer.instance, "change")

    def perform_destroy(self, instance):
        self._notify(instance, "delete")
        super().perform_destroy(instance)


class TopographyViewSet(mixins.CreateModelMixin,
                        mixins.UpdateModelMixin,
                        mixins.DestroyModelMixin,
                        viewsets.GenericViewSet):
    EXPIRE_UPLOAD = 100  # Presigned key for uploading expires after 10 seconds

    queryset = Topography.objects.all()
    serializer_class = TopographySerializer
    permission_classes = [IsAuthenticatedOrReadOnly, ParentObjectPermissions]

    def _notify(self, instance, verb):
        user = self.request.user
        other_users = get_users_with_perms(instance.surface).filter(~Q(id=user.id))
        for u in other_users:
            notify.send(sender=user, verb=verb, recipient=u,
                        description=f"User '{user.name}' {verb}d digital surface twin '{instance.name}'.")

    def perform_create(self, serializer):
        print('validated_data =', serializer.validated_data)

        # File name is passed in the 'name' field on create. It is the only field that needs to be present for the
        # create (POST) request.
        filename = self.request.data['name']

        # Check whether the user is allowed to write to the parent surface; if not, we cannot add a topography
        parent = serializer.validated_data['surface']
        if not self.request.user.has_perm(f'change_{parent._meta.model_name}', parent):
            self.permission_denied(
                self.request,
                code=403
            )

        # Set creator to current user when creating a new topography
        instance = serializer.save(creator=self.request.user)

        # Now we have an id, so populate update path
        datafile_path = topography_datafile_path(instance, filename)

        # Populate upload_url, the presigned key should expire quickly
        serializer.update(instance, {
            'upload_instructions': get_upload_instructions(instance, datafile_path, self.EXPIRE_UPLOAD)
        })

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._notify(serializer.instance, "change")

    def perform_destroy(self, instance):
        self._notify(instance, "delete")
        super().perform_destroy(instance)

    # From mixins.RetrieveModelMixin
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.task_state == Topography.NOTRUN:
            # The cache has never been created
            _log.info(f"Creating cached properties of new {instance.get_subject_type()} {instance.id}...")
            run_task(instance)
            instance.save()  # run_task sets the initial task state to 'pe', so we need to save
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


def download_surface(request, surface_id):
    """Returns a file or redirect comprised from topographies contained in a surface.

    :param request:
    :param surface_id: surface id
    :return:
    """

    #
    # Check existence and permissions for given surface
    #
    try:
        surface = Surface.objects.get(id=surface_id)
    except Surface.DoesNotExist:
        raise PermissionDenied()

    if not request.user.has_perm('view_surface', surface):
        raise PermissionDenied()

    content_data = None

    #
    # If the surface has been published, there might be a container file already.
    # If yes:
    #   Is there already a container?
    #     Then it instead of creating a new container.from
    #     If no, save the container in the publication later.
    # If no: create a container for this surface on the fly
    #
    if surface.is_published:
        pub = surface.publication
        container_filename = os.path.basename(pub.container_storage_path)

        if pub.container:
            if settings.USE_S3_STORAGE:
                # Return redirect to S3
                return redirect(pub.container.url)
            else:
                content_data = pub.container.read()
    else:
        container_filename = slugify(surface.name) + ".zip"

    if content_data is None:
        container_bytes = BytesIO()
        _log.info(f"Preparing container of surface id={surface_id} for download..")
        write_surface_container(container_bytes, [surface])
        content_data = container_bytes.getvalue()

        if surface.is_published:
            try:
                container_bytes.seek(0)
                _log.info(f"Saving container for publication with URL {pub.short_url} to storage for later..")
                pub.container.save(pub.container_storage_path, container_bytes)
            except (OSError, BlockingIOError) as exc:
                _log.error(f"Cannot save container for publication {pub.short_url} to storage. Reason: {exc}")
            # Return redirect to S3
            if settings.USE_S3_STORAGE:
                # Return redirect to S3
                return redirect(pub.container.url)

    # Prepare response object.
    response = HttpResponse(content_data,
                            content_type='application/x-zip-compressed')
    response['Content-Disposition'] = 'attachment; filename="{}"'.format(container_filename)

    increase_statistics_by_date_and_object(Metric.objects.SURFACE_DOWNLOAD_COUNT,
                                           period=Period.DAY, obj=surface)

    return response


def dzi(request, pk, dzi_filename):
    """Returns deepzoom image data for a topography

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

    return redirect(default_storage.url(f'{topo.storage_prefix}/dzi/{dzi_filename}'))


@api_view(['POST'])
def force_inspect(request, pk=None):
    user = request.user
    instance = Topography.objects.get(pk=pk)

    # Check that user has the right to modify this measurement
    if not user.is_staff and not user.has_perms(['change_surface'], instance.surface):
        return HttpResponseForbidden()

    _log.debug(f'Forcing renewal of cache for {instance}...')

    # Force renewal of cache
    run_task(instance)
    instance.save()

    # Return current state of object
    data = TopographySerializer(instance, context={'request': request}).data
    return Response(data, status=200)


@api_view(['PATCH'])
def set_permissions(request, pk=None):
    user = request.user
    obj = Surface.objects.get(pk=pk)

    # Check that user has the right to modify permissions
    if not user.has_perms(['view_surface', 'change_surface', 'delete_surface', 'share_surface', 'publish_surface'],
                          obj):
        return HttpResponseForbidden()

    # Check that the request does not ask to revoke permissions from the current user
    for permission in request.data:
        if permission['user']['id'] == user.id:
            if permission['permission'] != 'full':
                return Response({'message': 'Permissions cannot be revoked from logged in user'},
                                status=405)  # Not allowed

    # Get all current object permissions
    users_with_perms = {user.id: perms for user, perms in get_users_with_perms(obj, attach_perms=True).items()}

    # Everything looks okay, update permissions
    for permission in request.data:
        user_id = permission['user']['id']
        if user_id != user.id:
            other_user = User.objects.get(id=user_id)

            # Get current set of permissions and new permissions
            try:
                current_perms = set(users_with_perms[user_id])
            except KeyError:
                current_perms = set()
            new_perms = set(api_to_guardian(permission['permission']))

            # Assign all perms that are in the new set but not in the old
            for perm in new_perms - current_perms:
                assign_perm(perm, other_user, obj)

            # Remove all perms that are in the old set but not in the new
            for perm in current_perms - new_perms:
                remove_perm(perm, other_user, obj)

    # Permissions were updated successfully, return 204 No Content
    return Response({}, status=204)


@api_view(['GET'])
def tag_numerical_properties(request, pk=None):
    obj = Tag.objects.get(pk=pk)
    prop_values, prop_infos = obj.get_properties(kind='numerical')
    return Response(list(prop_values.keys()), status=200)


@api_view(['GET'])
def tag_categorical_properties(request, pk=None):
    obj = Tag.objects.get(pk=pk)
    prop_values, prop_infos = obj.get_properties(kind='categorical')
    return Response(list(prop_values.keys()), status=200)


@api_view(['POST'])
def upload_topography(request, pk=None):
    instance = Topography.objects.get(pk=pk)
    _log.debug(f"Receiving uploaded file for {instance}...")
    for filename, file in request.FILES.items():
        instance.datafile.save(filename, file)
        _log.debug(f"Received uploaded file and stored it at path '{instance.datafile.name}'.")
        instance.notify_users_with_perms('create',
                                         f"User '{instance.creator}' uploaded the measurement '{instance.name}' to "
                                         f"digital surface twin '{instance.surface.name}'.")

    # Return 204 No Content
    return Response({}, status=204)


@api_view(['POST'])
def import_surface(request):
    url = request.data.get('url')

    if not url:
        return HttpResponseBadRequest()

    user = request.user
    import_container_from_url.delay(user.id, url)

    return Response({}, status=200)


@api_view(['GET'])
def versions(request):
    return Response(get_versions(), status=200)


@api_view(['GET'])
def statistics(request):
    return Response({
        'nb_users': User.objects.count() - 1,  # -1 because we don't count the anonymous user
        'nb_surfaces': Surface.objects.count(),
        'nb_topographies': Topography.objects.count(),
    }, status=200)


@api_view(['GET'])
def memory_usage(request):
    r = Topography.objects \
        .values('resolution_x', 'resolution_y', 'task_memory') \
        .annotate(duration=F('end_time') - F('start_time'),
                  nb_data_pts=F('resolution_x') * Case(
                      When(resolution_y__isnull=False, then=F('resolution_y')), default=1))
    return Response(list(r), status=200)
