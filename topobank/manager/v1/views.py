import itertools
import logging
import os.path
from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.db.models import Case, F, Q, When
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils.text import slugify
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from notifications.signals import notify
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ParseError, PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import (
    IsAdminUser,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
)
from rest_framework.response import Response
from trackstats.models import Metric, Period

from ...authorization.permissions import ObjectPermission
from ...files.models import Manifest
from ...organizations.models import resolve_organization
from ...supplib.mixins import UserUpdateMixin
from ...supplib.versions import get_versions
from ...taskapp.utils import run_task
from ...usage_stats.utils import increase_statistics_by_date_and_object
from ...users.models import User, resolve_user
from ..export_zip import export_container_zip
from ..filters import filter_surfaces
from ..models import Surface, Tag, Topography
from ..permissions import TagPermission
from ..tasks import import_container_from_url
from ..v1.serializers import SurfaceSerializer, TagSerializer, TopographySerializer

_log = logging.getLogger(__name__)


class TagViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Tag.objects.all()
    lookup_field = "name"
    lookup_value_regex = "[^.]+"  # We need to match paths that include slashes
    serializer_class = TagSerializer
    permission_classes = [TagPermission]
    pagination_class = LimitOffsetPagination

    def list(self, request, *args, **kwargs):
        all_tags = set(
            "" if tag_name is None else tag_name
            for tag_name in itertools.chain.from_iterable(
                # Need to ensure we only get tags of non-deleted surfaces
                Surface.objects.for_user(request.user).filter(deletion_time__isnull=True).values_list("tags__name")
            )
        )

        toplevel_tags = set(f"{tag}/".split("/", maxsplit=1)[0] for tag in all_tags)
        return Response(sorted(toplevel_tags))


class SurfaceViewSet(UserUpdateMixin, viewsets.ModelViewSet):
    serializer_class = SurfaceSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, ObjectPermission]
    pagination_class = LimitOffsetPagination

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
        qs = Surface.objects.for_user(self.request.user).filter(
            deletion_time__isnull=True
        )
        return filter_surfaces(self.request, qs)

    @transaction.atomic
    def perform_create(self, serializer):
        # Set created_by to current user when creating a new surface
        instance = super().perform_create(serializer)

        # We now have an id, set name if missing
        if "name" not in serializer.data or serializer.data["name"] == "":
            instance.name = f"Digital surface twin #{instance.id}"
            instance.save()

    @transaction.atomic
    def perform_update(self, serializer):
        super().perform_update(serializer)

    @transaction.atomic
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
    permission_classes = [IsAuthenticatedOrReadOnly, ObjectPermission]
    pagination_class = LimitOffsetPagination

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
        # Return empty queryset for schema generation
        if getattr(self, "swagger_fake_view", False):
            return Topography.objects.none()

        qs = Topography.objects.for_user(self.request.user).filter(
            deletion_time__isnull=True
        )
        surfaces = self.request.query_params.getlist("surface")
        tags = self.request.query_params.getlist("tag")
        tags_startswith = self.request.query_params.getlist("tag_startswith")
        subject_q = Q()
        if len(surfaces) > 0:
            for surface in surfaces:
                try:
                    surface_id = int(surface)
                except ValueError:
                    raise ParseError(
                        f"Invalid surface ID '{surface}'. Please provide an integer."
                    )
                subject_q |= Q(surface__id=surface_id)
        elif len(tags) > 0:
            for tag in tags:
                if tag:
                    subject_q |= Q(surface__tags__name=tag)
                else:
                    subject_q |= Q(surface__tags=None)
        elif len(tags_startswith) > 0:
            for tag_startswith in tags_startswith:
                subject_q |= (Q(surface__tags__name=tag_startswith)
                              | Q(surface__tags__name__startswith=tag_startswith.rstrip("/") + "/"))

        if len(subject_q) == 0:
            if self.action == "list":
                raise ParseError(
                    "Please limit your request with query parameters. Possible parameters "
                    "are: `surface`, `tag`, `tag_startswith`"
                )
            return qs
        else:
            return qs.filter(subject_q).distinct()

    @transaction.atomic
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

        # Set created_by to current user when creating a new topography
        # Don't pass permissions - let the save() method inherit from parent surface
        instance = serializer.save(created_by=self.request.user)

        # File name is passed in the 'name' field on create. It is the only field that
        # needs to be present for them create (POST) request.
        if instance.datafile is None:
            filename = serializer.validated_data["name"]
            instance.datafile = Manifest.objects.create(
                permissions=instance.permissions, filename=filename, kind="raw", folder=None
            )
            instance.save()

    @transaction.atomic
    def perform_update(self, serializer):
        super().perform_update(serializer)

    @transaction.atomic
    def perform_destroy(self, instance):
        self._notify(instance, "delete")
        instance.delete()

    # From mixins.RetrieveModelMixin
    @transaction.non_atomic_requests
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.task_state == Topography.NOTRUN:
            # The cache has never been created
            _log.info(
                f"Creating cached properties of new {instance.get_subject_type()} {instance.id}..."
            )
            with transaction.atomic():
                run_task(instance)  # Sets task state to 'pe' and triggers task on commit
                instance.save()  # Save the pending state
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
@transaction.non_atomic_requests
def download_surfaces(request, surfaces, container_filename=None):
    #
    # Check existence and permissions for given surface
    #
    for surface in surfaces:
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
    if len(surfaces) == 1:
        (surface,) = surfaces
        if surface.is_published:
            pub = surface.publication
            if container_filename is None:
                container_filename = os.path.basename(pub.container_storage_path)

            if pub.container:
                if settings.USE_S3_STORAGE:
                    # Return redirect to S3
                    return redirect(pub.container.url)
                else:
                    content_data = pub.container.read()
        else:
            if container_filename is None:
                container_filename = f"{slugify(surface.name)}.zip"
    else:
        if container_filename is None:
            container_filename = "digital-surface-twins.zip"

    if content_data is None:
        container_bytes = BytesIO()
        _log.info(
            f"Preparing container of surface with ids {' '.join([str(s.id) for s in surfaces])} for download..."
        )
        try:
            export_container_zip(container_bytes, surfaces)
        except FileNotFoundError:
            return HttpResponseBadRequest(
                "Cannot create ZIP container for download because some data file "
                "could not be accessed. (The file may be missing.)"
            )
        content_data = container_bytes.getvalue()

        if len(surfaces) == 1 and surfaces[0].is_published:
            pub = surfaces[0].publication
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

    for surface in surfaces:
        increase_statistics_by_date_and_object(
            Metric.objects.SURFACE_DOWNLOAD_COUNT, period=Period.DAY, obj=surface
        )

    return response


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@transaction.non_atomic_requests
def download_surface(request, surface_ids):
    # `surface_ids` is a comma-separated list of surface IDs as a string,
    # e.g. "1,2,3", we need to parse it
    try:
        surface_ids = [int(surface_id) for surface_id in surface_ids.split(",")]
    except ValueError:
        return HttpResponseBadRequest("Invalid surface ID(s).")

    # Get surfaces from database
    surfaces = [get_object_or_404(Surface, id=surface_id) for surface_id in surface_ids]

    # Trigger the actual download
    return download_surfaces(request, surfaces)


@extend_schema(request=None, responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@transaction.non_atomic_requests
def download_tag(request, name):
    # `tag_name` is the name of the tag, we need to parse it
    tag = get_object_or_404(Tag, name=name)
    tag.authorize_user(request.user, "view")

    # Trigger the actual download
    return download_surfaces(
        request, tag.get_descendant_surfaces(), f"{slugify(tag.name)}.zip"
    )


@extend_schema(
    description="Force inspection of a topography",
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="Topography ID",
        ),
    ],
    request=None,
    responses=OpenApiTypes.OBJECT,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.non_atomic_requests
def force_inspect(request, pk=None):
    user = request.user
    instance = get_object_or_404(Topography, pk=pk)

    # Check that user has the right to modify this measurement
    if not user.is_staff and not instance.has_permission(user, "edit"):
        return HttpResponseForbidden()

    _log.debug(f"Forcing renewal of cache for {instance}...")

    # Force renewal of cache within transaction
    with transaction.atomic():
        run_task(instance)
        instance.save()

    # Return current state of object
    data = TopographySerializer(instance, context={"request": request}).data
    return Response(data)


@extend_schema(
    description="Set permissions for a surface",
    parameters=[
        OpenApiParameter(
            name="pk",
            type=int,
            location=OpenApiParameter.PATH,
            description="Surface ID",
        ),
    ],
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.NONE, 405: OpenApiTypes.OBJECT},
)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def set_surface_permissions(request, pk=None):
    logged_in_user = request.user
    obj = get_object_or_404(Surface, pk=pk)

    # Check that user has the right to modify permissions
    if not obj.has_permission(logged_in_user, "full"):
        return HttpResponseForbidden()

    # Check that the request does not ask to revoke permissions from the current user
    for permission in request.data:
        if "user" in permission:
            other_user = resolve_user(permission["user"])
            if other_user == logged_in_user:
                if permission["permission"] != "full":
                    return Response(
                        {
                            "message": "Permissions cannot be revoked from logged in user"
                        },
                        status=405,
                    )  # Not allowed

    # Everything looks okay, update permissions
    for permission in request.data:
        perm = permission.get("permission", None)
        if perm is None:
            return HttpResponseBadRequest(reason="Permission was not provided")
        if "user" in permission:
            other_user = resolve_user(permission["user"])
            if other_user != logged_in_user:
                if perm == "no-access":
                    obj.revoke_permission(other_user)
                else:
                    obj.grant_permission(other_user, perm)
        elif "organization" in permission:
            organization = resolve_organization(permission["organization"])
            if perm == "no-access":
                obj.revoke_permission(organization)
            else:
                obj.grant_permission(organization, perm)
        else:
            return HttpResponseBadRequest(
                reason="Can only set permissions for users or organizations."
            )

    # Permissions were updated successfully, return 204 No Content
    return Response({}, status=204)


@extend_schema(request=None, responses=None)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@transaction.atomic
def set_tag_permissions(request, name=None):
    logged_in_user = request.user
    obj = get_object_or_404(Tag, name=name)

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
                perm = permission.get("permission", None)
                if perm is None:
                    return HttpResponseBadRequest(reason="Permission was not provided")

                if "user" in permission:
                    other_user = resolve_user(permission["user"])
                    if other_user != logged_in_user:
                        perm = permission["permission"]
                        if perm == "no-access":
                            surface.revoke_permission(other_user)
                        else:
                            surface.grant_permission(other_user, perm)
                elif "organization" in permission:
                    organization = resolve_organization(permission["organization"])
                    if perm == "no-access":
                        surface.revoke_permission(organization)
                    else:
                        surface.grant_permission(organization, perm)
                else:
                    return HttpResponseBadRequest(
                        reason="Can only set permissions for users or organizations."
                    )
        else:
            rejected += [surface.get_absolute_url(request)]

    # Permissions were updated successfully, return 204 No Content
    return Response({"updated": updated, "rejected": rejected})


@extend_schema(request=None, responses=None)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@transaction.non_atomic_requests
def tag_numerical_properties(request, name=None):
    obj = get_object_or_404(Tag, name=name)
    obj.authorize_user(request.user, "view")
    prop_values, prop_infos = obj.get_properties(kind="numerical")
    return Response(dict(names=list(prop_values.keys())))


@extend_schema(request=None, responses=None)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@transaction.non_atomic_requests
def tag_categorical_properties(request, name=None):
    obj = get_object_or_404(Tag, name=name)
    obj.authorize_user(request.user, "view")
    prop_values, prop_infos = obj.get_properties(kind="categorical")
    return Response(dict(names=list(prop_values.keys())))


@extend_schema(request=None, responses=None)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@transaction.non_atomic_requests
def import_surface(request):
    url = request.data.get("url")

    if not url:
        return HttpResponseBadRequest()

    user = request.user
    # Need to pass id here because user is not JSON serializable
    with transaction.atomic():
        transaction.on_commit(lambda: import_container_from_url.delay(user.id, url))

    return Response({})


@extend_schema(
    description="Get version information for all installed packages",
    request=None,
    responses=OpenApiTypes.OBJECT,
)
@api_view(["GET"])
@transaction.non_atomic_requests
def versions(request):
    return Response(get_versions())


@extend_schema(request=None, responses=None)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def statistics(request):
    # Global statistics
    stats = {
        "nb_users": User.objects.count()
        - 1,  # -1 because we don't count the anonymous user
        "nb_surfaces": Surface.objects.count(),
        "nb_topographies": Topography.objects.count(),
    }
    # User-specific statistics
    stats = {
        **stats,
        "nb_surfaces_of_user": Surface.objects.for_user(request.user).count(),
        "nb_topographies_of_user": Topography.objects.for_user(
            request.user
        ).count(),
        "nb_surfaces_shared_with_user": Surface.objects.for_user(request.user)
        .exclude(created_by=request.user)
        .count(),
    }
    return Response(stats)


@extend_schema(request=None, responses=None)
@api_view(["GET"])
@permission_classes([IsAdminUser])
@transaction.non_atomic_requests
def memory_usage(request):
    r = Topography.objects.values(
        "resolution_x", "resolution_y", "task_memory"
    ).annotate(
        task_duration=F("task_end_time") - F("task_start_time"),
        nb_data_pts=F("resolution_x")
        * Case(When(resolution_y__isnull=False, then=F("resolution_y")), default=1),
    )
    return Response(list(r))
