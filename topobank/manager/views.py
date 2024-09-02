import itertools
import logging
import os.path
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.models import Case, F, Q, When
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import redirect
from django.utils.text import slugify
from notifications.signals import notify
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view
from rest_framework.exceptions import ParseError
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from trackstats.models import Metric, Period

from ..authorization.permissions import Permission
from ..manager.utils import get_upload_instructions
from ..supplib.versions import get_versions
from ..taskapp.utils import run_task
from ..usage_stats.utils import increase_statistics_by_date_and_object
from ..users.models import User
from .containers import write_surface_container
from .models import Property, Surface, Tag, Topography, topography_datafile_path
from .permissions import TagPermission
from .serializers import (
    PropertySerializer,
    SurfaceSerializer,
    TagSerializer,
    TopographySerializer,
)
from .tasks import import_container_from_url

_log = logging.getLogger(__name__)


class PropertyViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticatedOrReadOnly, Permission]

    def perform_create(self, serializer):
        # Check whether the user is allowed to write to the parent surface; if not, we
        # cannot add a topography
        parent = serializer.validated_data["surface"]
        if not parent.has_permission(self.request.user, "edit"):
            self.permission_denied(
                self.request,
                message=f"User {self.request.user} has no permission to edit dataset "
                f"{parent.get_absolute_url()}.",
            )
        serializer.save()


class TagViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Tag.objects.all()
    lookup_field = "name"
    lookup_value_regex = "[^.]+"  # We need to match paths that include slashes
    serializer_class = TagSerializer
    permission_classes = [TagPermission]

    def list(self, request, *args, **kwargs):
        all_tags = set(
            itertools.chain.from_iterable(
                Surface.objects.for_user(request.user).values_list("tags__name")
            )
        )

        if all_tags == {None}:
            return Response([])

        toplevel_tags = set(f"{tag}/".split("/", maxsplit=1)[0] for tag in all_tags)
        return Response(sorted(toplevel_tags))


class SurfaceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SurfaceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, Permission]

    def _notify(self, instance, verb):
        user = self.request.user
        other_users = instance.permissions.user_permissions.filter(~Q(user__id=user.id))
        for u in other_users:
            notify.send(
                sender=user,
                verb=verb,
                recipient=u.user,
                description=f"User '{user.name}' {verb}d digital surface twin '{instance.name}'.",
            )

    def get_queryset(self):
        qs = Surface.objects.for_user(self.request.user)
        tag = self.request.query_params.get("tag", None)
        if tag is not None or (tag == 'None' or tag == 'null'):
            if tag == 'None' or tag == 'null':
                tag = None
            qs = qs.filter(tags__name=tag)
        elif self.action == "list":
            # We do not allow simply listing all surfaces
            raise ParseError("Please limit you request with query parameters.")
        return qs

    def perform_create(self, serializer):
        # Set creator to current user when creating a new surface
        instance = serializer.save(creator=self.request.user)

        # We now have an id, set name if missing
        if "name" not in serializer.data or serializer.data["name"] == "":
            instance.name = f"Digital surface twin #{instance.id}"
            instance.save()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._notify(serializer.instance, "change")

    def perform_destroy(self, instance):
        self._notify(instance, "delete")
        super().perform_destroy(instance)


class TopographyViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    EXPIRE_UPLOAD = 100  # Presigned key for uploading expires after 10 seconds

    serializer_class = TopographySerializer
    permission_classes = [IsAuthenticatedOrReadOnly, Permission]

    def _notify(self, instance, verb):
        user = self.request.user
        other_users = instance.permissions.user_permissions.filter(~Q(user__id=user.id))
        for u in other_users:
            notify.send(
                sender=user,
                verb=verb,
                recipient=u.user,
                description=f"User '{user.name}' {verb}d digital surface twin "
                f"'{instance.name}'.",
            )

    def get_queryset(self):
        qs = Surface.objects.for_user(self.request.user)
        surface = self.request.query_params.get("surface", None)
        if surface is not None:
            qs = qs.filter(id=surface)
        elif self.action == "list":
            raise ParseError("Please limit you request with query parameters.")
        return Topography.objects.filter(surface__in=qs)

    def perform_create(self, serializer):
        # File name is passed in the 'name' field on create. It is the only field that
        # needs to be present for them create (POST) request.
        filename = self.request.data["name"]

        # Check whether the user is allowed to write to the parent surface; if not, we
        # cannot add a topography
        parent = serializer.validated_data["surface"]
        if not parent.has_permission(self.request.user, "edit"):
            self.permission_denied(
                self.request,
                message=f"User {self.request.user} has no permission to edit dataset "
                f"{parent.get_absolute_url()}.",
            )

        # Set creator to current user when creating a new topography
        instance = serializer.save(creator=self.request.user)

        # Now we have an id, so populate update path
        datafile_path = topography_datafile_path(instance, filename)

        # Populate upload_url with a presigned S3 URL; the presigned key should expire
        # quickly
        serializer.update(
            instance,
            {
                "upload_instructions": get_upload_instructions(
                    instance, datafile_path, self.EXPIRE_UPLOAD
                )
            },
        )

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
            _log.info(
                f"Creating cached properties of new {instance.get_subject_type()} {instance.id}..."
            )
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

    if not surface.has_permission(request.user, "view"):
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
                _log.info(
                    f"Saving container for publication with URL {pub.short_url} to storage for later.."
                )
                pub.container.save(pub.container_storage_path, container_bytes)
            except (OSError, BlockingIOError) as exc:
                _log.error(
                    f"Cannot save container for publication {pub.short_url} to storage. Reason: {exc}"
                )
            # Return redirect to S3
            if settings.USE_S3_STORAGE:
                # Return redirect to S3
                return redirect(pub.container.url)

    # Prepare response object.
    response = HttpResponse(content_data, content_type="application/x-zip-compressed")
    response["Content-Disposition"] = 'attachment; filename="{}"'.format(
        container_filename
    )

    increase_statistics_by_date_and_object(
        Metric.objects.SURFACE_DOWNLOAD_COUNT, period=Period.DAY, obj=surface
    )

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

    if not topo.has_permission(request.user, "view"):
        raise PermissionDenied()

    # okay, we have a valid topography and the user is allowed to see it

    return redirect(default_storage.url(f"{topo.storage_prefix}/dzi/{dzi_filename}"))


@api_view(["POST"])
def force_inspect(request, pk=None):
    user = request.user
    instance = Topography.objects.get(pk=pk)

    # Check that user has the right to modify this measurement
    if not user.is_staff and not instance.has_permission(user, "edit"):
        return HttpResponseForbidden()

    _log.debug(f"Forcing renewal of cache for {instance}...")

    # Force renewal of cache
    run_task(instance)
    instance.save()

    # Return current state of object
    data = TopographySerializer(instance, context={"request": request}).data
    return Response(data, status=200)


@api_view(["PATCH"])
def set_permissions(request, pk=None):
    user = request.user
    obj = Surface.objects.get(pk=pk)

    # Check that user has the right to modify permissions
    if not obj.has_permission(user, "full"):
        return HttpResponseForbidden()

    # Check that the request does not ask to revoke permissions from the current user
    for permission in request.data:
        if permission["user"]["id"] == user.id:
            if permission["permission"] != "full":
                return Response(
                    {"message": "Permissions cannot be revoked from logged in user"},
                    status=405,
                )  # Not allowed

    # Everything looks okay, update permissions
    for permission in request.data:
        user_id = permission["user"]["id"]
        if user_id != user.id:
            other_user = User.objects.get(id=user_id)
            perm = permission["permission"]
            if perm is None:
                obj.revoke_permission(other_user)
            else:
                obj.grant_permission(other_user, perm)

    # Permissions were updated successfully, return 204 No Content
    return Response({}, status=204)


@api_view(["GET"])
def tag_numerical_properties(request, pk=None):
    obj = Tag.objects.get(pk=pk)
    obj.authorize_user(request.user, "view")
    prop_values, prop_infos = obj.get_properties(kind="numerical")
    return Response(list(prop_values.keys()), status=200)


@api_view(["GET"])
def tag_categorical_properties(request, pk=None):
    obj = Tag.objects.get(pk=pk)
    obj.authorize_user(request.user, "view")
    prop_values, prop_infos = obj.get_properties(kind="categorical")
    return Response(list(prop_values.keys()), status=200)


@api_view(["POST"])
def upload_topography(request, pk=None):
    instance = Topography.objects.get(pk=pk)
    _log.debug(f"Receiving uploaded file for {instance}...")
    for key, file in request.FILES.items():
        instance.datafile.save(file.name, file)
        _log.debug(
            f"Received uploaded file and stored it at path '{instance.datafile.name}'."
        )
        instance.notify_users(
            request.user,
            "create",
            f"User '{instance.creator}' uploaded the measurement '{instance.name}' to "
            f"digital surface twin '{instance.surface.name}'.",
        )

    # Return 204 No Content
    return Response({}, status=204)


@api_view(["POST"])
def import_surface(request):
    url = request.data.get("url")

    if not url:
        return HttpResponseBadRequest()

    user = request.user
    # Need to pass id here because user is not JSON serializable
    import_container_from_url.delay(user.id, url)

    return Response({}, status=200)


@api_view(["GET"])
def versions(request):
    return Response(get_versions(), status=200)


@api_view(["GET"])
def statistics(request):
    return Response(
        {
            "nb_users": User.objects.count()
            - 1,  # -1 because we don't count the anonymous user
            "nb_surfaces": Surface.objects.count(),
            "nb_topographies": Topography.objects.count(),
        },
        status=200,
    )


@api_view(["GET"])
def memory_usage(request):
    r = Topography.objects.values(
        "resolution_x", "resolution_y", "task_memory"
    ).annotate(
        duration=F("end_time") - F("start_time"),
        nb_data_pts=F("resolution_x")
        * Case(When(resolution_y__isnull=False, then=F("resolution_y")), default=1),
    )
    return Response(list(r), status=200)
