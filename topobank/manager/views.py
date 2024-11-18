import itertools
import logging
import os.path
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Case, F, Q, When
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
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
from ..files.models import Manifest
from ..supplib.versions import get_versions
from ..taskapp.utils import run_task
from ..usage_stats.utils import increase_statistics_by_date_and_object
from ..users.models import User, resolve_user
from .containers import write_surface_container
from .models import Surface, Tag, Topography
from .permissions import TagPermission
from .serializers import SurfaceSerializer, TagSerializer, TopographySerializer
from .tasks import import_container_from_url

_log = logging.getLogger(__name__)


class TagViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Tag.objects.all()
    lookup_field = "name"
    lookup_value_regex = "[^.]+"  # We need to match paths that include slashes
    serializer_class = TagSerializer
    permission_classes = [TagPermission]

    def list(self, request, *args, **kwargs):
        all_tags = set(
            "" if tag_name is None else tag_name
            for tag_name in itertools.chain.from_iterable(
                Surface.objects.for_user(request.user).values_list("tags__name")
            )
        )

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
        tag_startswith = self.request.query_params.get("tag_startswith", None)
        if tag is not None:
            if tag_startswith is not None:
                raise ParseError(
                    "Please specify either `tag` or `tag_startswith`, not both."
                )
            if tag:
                qs = qs.filter(tags__name=tag)
            else:
                qs = qs.filter(tags=None)
        elif tag_startswith is not None:
            if tag_startswith:
                qs = qs.filter(
                    Q(tags__name=tag_startswith)
                    | Q(tags__name__startswith=tag_startswith.rstrip("/") + "/")
                ).order_by("id").distinct("id")
            else:
                raise ParseError("`tag_startswith` cannot be empty.")
        elif self.action == "list":
            # We do not allow simply listing all surfaces
            raise ParseError(
                "Please limit you request with query parameters. Possible parameters "
                "are: `tag`, `tag_startswith`"
            )
        return qs

    def perform_create(self, serializer):
        # Set creator to current user when creating a new surface
        instance = serializer.save(creator=self.request.user)

        # We now have an id, set name if missing
        if "name" not in serializer.data or serializer.data["name"] == "":
            instance.name = f"Digital surface twin #{instance.id}"
            instance.save()

    def perform_update(self, serializer):
        serializer.save()
        self._notify(serializer.instance, "change")

    def perform_destroy(self, instance):
        self._notify(instance, "delete")
        instance.delete()


class TopographyViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
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
        qs = Topography.objects.for_user(self.request.user)
        surface = self.request.query_params.get("surface", None)
        tag = self.request.query_params.get("tag", None)
        tag_startswith = self.request.query_params.get("tag_startswith", None)
        if sum([surface is not None, tag is not None, tag_startswith is not None]) > 1:
            raise ParseError(
                "Please specify only one of `surface`, `tag` or `tag_startswith`."
            )
        if surface is not None:
            qs = qs.filter(surface__id=int(surface))
        elif tag is not None:
            if tag:
                qs = qs.filter(surface__tags__name=tag)
            else:
                qs = qs.filter(surface__tags=None)
        elif tag_startswith is not None:
            if tag_startswith:
                qs = qs.filter(
                    Q(surface__tags__name=tag_startswith)
                    | Q(
                        surface__tags__name__startswith=tag_startswith.rstrip("/") + "/"
                    )
                )
            else:
                raise ParseError("`tag_startswith` cannot be empty")
        elif self.action == "list":
            raise ParseError(
                "Please limit your request with query parameters. Possible parameters "
                "are: `surface`, `tag`, `tag_startswith`"
            )
        return qs

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

        # Set creator to current user when creating a new topography
        instance = serializer.save(creator=self.request.user)

        # File name is passed in the 'name' field on create. It is the only field that
        # needs to be present for them create (POST) request.
        filename = serializer.validated_data["name"]
        instance.datafile = Manifest.objects.create(
            permissions=instance.permissions, filename=filename, kind="raw"
        )
        instance.save()

    def perform_update(self, serializer):
        serializer.save()
        self._notify(serializer.instance, "change")

    def perform_destroy(self, instance):
        self._notify(instance, "delete")
        instance.delete()

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
def set_surface_permissions(request, pk=None):
    logged_in_user = request.user
    obj = Surface.objects.get(pk=pk)

    # Check that user has the right to modify permissions
    if not obj.has_permission(logged_in_user, "full"):
        return HttpResponseForbidden()

    # Check that the request does not ask to revoke permissions from the current user
    for permission in request.data:
        other_user = resolve_user(permission["user"])
        if other_user == logged_in_user:
            if permission["permission"] != "full":
                return Response(
                    {"message": "Permissions cannot be revoked from logged in user"},
                    status=405,
                )  # Not allowed

    # Everything looks okay, update permissions
    for permission in request.data:
        other_user = resolve_user(permission["user"])
        if other_user != logged_in_user:
            perm = permission["permission"]
            if perm == "no-access":
                obj.revoke_permission(other_user)
            else:
                obj.grant_permission(other_user, perm)

    # Permissions were updated successfully, return 204 No Content
    return Response({}, status=204)


@api_view(["PATCH"])
def set_tag_permissions(request, name=None):
    logged_in_user = request.user
    obj = Tag.objects.get(name=name)

    # Check that the request does not ask to revoke permissions from the current user
    for permission in request.data:
        user = resolve_user(permission["user"])
        if user == logged_in_user:
            if permission["permission"] != "full":
                return Response(
                    {"message": "Permissions cannot be revoked from logged in user"},
                    status=405,
                )

    # Keep track of updated and insufficient permissions
    updated = []
    rejected = []

    # Loop over all surfaces
    obj.authorize_user(logged_in_user)
    for surface in obj.get_descendant_surfaces():
        # Check that user has the right to modify permissions
        if surface.has_permission(logged_in_user, "full"):
            updated += [surface.get_absolute_url(request)]
            # Loop over permissions
            for permission in request.data:
                other_user = resolve_user(permission["user"])
                if other_user != logged_in_user:
                    perm = permission["permission"]
                    if perm == "no-access":
                        surface.revoke_permission(other_user)
                    else:
                        surface.grant_permission(other_user, perm)
        else:
            rejected += [surface.get_absolute_url(request)]

    # Permissions were updated successfully, return 204 No Content
    return Response(
        {"updated": updated, "rejected": rejected},
        status=200,
    )


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
