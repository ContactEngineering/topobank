import logging

from django import shortcuts
from django.utils.translation import gettext_lazy as _

from guardian.shortcuts import get_perms, get_users_with_perms
from rest_framework import reverse, serializers
from tagulous.contrib.drf import TagRelatedManagerField

from ..publication.serializers import PublicationSerializer
from ..taskapp.serializers import TaskStateModelSerializer
from ..users.serializers import UserSerializer

from .models import Surface, Topography, TagModel
from .permissions import guardian_to_api
from .utils import get_search_term, filtered_topographies, subjects_to_base64

_log = logging.getLogger(__name__)


# From: RomanKhudobei, https://github.com/encode/django-rest-framework/issues/1655
class StrictFieldMixin:
    """Raises error if read only fields or non-existing fields passed to input data"""
    default_error_messages = {
        'read_only': _('This field is read only'),
        'does_not_exist': _('This field does not exist')
    }

    def to_internal_value(self, data):
        field_names = set(field.field_name for field in self._writable_fields)
        errors = {}

        # check that all dictionary keys are fields
        for key in data.keys():
            if key not in field_names:
                errors[key] = serializers.ErrorDetail(self.error_messages['does_not_exist'], code='does_not_exist')

        if errors != {}:
            raise serializers.ValidationError(errors)

        return super().to_internal_value(data)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if not hasattr(self, 'initial_data'):
            return attrs

        # collect declared read only fields and read only fields from Meta
        read_only_fields = ({field_name for field_name, field in self.fields.items() if field.read_only} |
                            set(getattr(self.Meta, 'read_only_fields', set())))

        received_read_only_fields = set(self.initial_data) & read_only_fields

        if received_read_only_fields:
            errors = {}
            for field_name in received_read_only_fields:
                errors[field_name] = serializers.ErrorDetail(self.error_messages['read_only'], code='read_only')

            raise serializers.ValidationError(errors)

        return attrs


class TopographySerializer(StrictFieldMixin,
                           TaskStateModelSerializer):
    class Meta:
        model = Topography
        fields = ['url',
                  'id',
                  'surface',
                  'name',
                  'creator',
                  'datafile', 'datafile_format', 'channel_names', 'data_source',
                  'squeezed_datafile',
                  'description',
                  'measurement_date',
                  'size_editable', 'size_x', 'size_y',
                  'unit_editable', 'unit',
                  'height_scale_editable', 'height_scale',
                  'has_undefined_data', 'fill_undefined_data_mode',
                  'detrend_mode',
                  'resolution_x', 'resolution_y',
                  'bandwidth_lower', 'bandwidth_upper',
                  'short_reliability_cutoff',
                  'is_periodic',
                  'instrument_name', 'instrument_type', 'instrument_parameters',
                  'post_data',
                  'is_metadata_complete',
                  'thumbnail',
                  'duration', 'error', 'task_progress', 'task_state', 'tags']  # TaskStateModelSerializer

    url = serializers.HyperlinkedIdentityField(view_name='manager:topography-api-detail', read_only=True)
    creator = serializers.HyperlinkedRelatedField(view_name='users:user-api-detail', read_only=True)
    surface = serializers.HyperlinkedRelatedField(view_name='manager:surface-api-detail',
                                                  queryset=Surface.objects.all())

    tags = TagRelatedManagerField(required=False)

    is_metadata_complete = serializers.SerializerMethodField()

    post_data = serializers.DictField(default=None, read_only=True)  # Pre-signed upload location

    def validate(self, data):
        read_only_fields = []
        if self.instance is not None:
            if not self.instance.size_editable:
                if 'size_x' in data:
                    read_only_fields += ['size_x']
                if 'size_y' in data:
                    read_only_fields += ['size_y']
            if not self.instance.unit_editable:
                if 'unit' in data:
                    read_only_fields += ['unit']
            if not self.instance.height_scale_editable:
                if 'unit' in data:
                    read_only_fields += ['height_scale']
            if len(read_only_fields) > 0:
                s = ', '.join([f'`{name}`' for name in read_only_fields])
                raise serializers.ValidationError(f'{s} is given by the data file and cannot be set')
        return super().validate(data)

    def get_is_metadata_complete(self, obj):
        return obj.is_metadata_complete


class SurfaceSerializer(StrictFieldMixin,
                        serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Surface
        fields = ['url',
                  'id',
                  'name',
                  'category',
                  'creator',
                  'description',
                  'publication',
                  'tags',
                  'topography_set',
                  'permissions']

    url = serializers.HyperlinkedIdentityField(view_name='manager:surface-api-detail', read_only=True)
    creator = serializers.HyperlinkedRelatedField(view_name='users:user-api-detail', read_only=True)
    # publication = serializers.HyperlinkedRelatedField(view_name='publication:publication-api-detail', read_only=True)
    publication = PublicationSerializer(read_only=True)
    topography_set = TopographySerializer(many=True, read_only=True)

    tags = TagRelatedManagerField(required=False)

    permissions = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # We only return the topography set if requested to do so
        children = self.context['request'].query_params.get('children')
        with_children = children is not None and children.lower() in ['yes', 'true']
        if not with_children:
            self.fields.pop('topography_set')

        # We only return permissions if requested to do so
        permissions = self.context['request'].query_params.get('permissions')
        with_permissions = permissions is not None and permissions.lower() in ['yes', 'true']
        if not with_permissions:
            self.fields.pop('permissions')

    def get_permissions(self, obj):
        request = self.context['request']
        current_user = request.user
        users = get_users_with_perms(obj, attach_perms=True)
        return {'current_user': {'user': UserSerializer(current_user, context=self.context).data,
                                 'permission': guardian_to_api(users[current_user])},
                'other_users': [{'user': UserSerializer(key, context=self.context).data,
                                 'permission': guardian_to_api(value)}
                                for key, value in users.items() if key != current_user]}


class TopographySearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topography
        fields = ['id', 'type', 'name', 'creator', 'description', 'tags', 'urls', 'selected', 'key', 'surface_key',
                  'title', 'folder', 'version', 'publication_date', 'publication_authors', 'datafile_format',
                  'measurement_date', 'resolution_x', 'resolution_y', 'size_x', 'size_y', 'size_editable', 'unit',
                  'unit_editable', 'height_scale', 'height_scale_editable', 'creator_name', 'sharing_status', 'label',
                  'is_periodic', 'thumbnail', 'tags', 'instrument_name', 'instrument_type', 'instrument_parameters']

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
        default=serializers.CurrentUserDefault()
    )

    title = serializers.CharField(source='name', read_only=True)  # set this through name

    urls = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    surface_key = serializers.SerializerMethodField()
    sharing_status = serializers.SerializerMethodField()
    # `folder` is Fancytree-specific, see
    # https://wwwendt.de/tech/fancytree/doc/jsdoc/global.html#NodeData
    folder = serializers.BooleanField(default=False, read_only=True)
    tags = TagRelatedManagerField()
    # `type` should be the output of mangle_content_type(Meta.model)
    type = serializers.CharField(default='topography', read_only=True)
    version = serializers.CharField(default=None, read_only=True)
    publication_authors = serializers.CharField(default=None, read_only=True)
    publication_date = serializers.CharField(default=None, read_only=True)
    creator_name = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()

    def get_urls(self, obj):
        """Return only those urls which are usable for the user

        :param obj: topography object
        :return: dict with { url_name: url }
        """
        user = self.context['request'].user
        surface = obj.surface

        perms = get_perms(user, surface)  # TODO are permissions needed here?

        urls = {
            'select': shortcuts.reverse('manager:topography-select', kwargs=dict(pk=obj.pk)),
            'unselect': shortcuts.reverse('manager:topography-unselect', kwargs=dict(pk=obj.pk))
        }

        if 'view_surface' in perms:
            urls['detail'] = f"{shortcuts.reverse('manager:topography-detail')}?topography={obj.pk}"
            urls['analyze'] = f"{shortcuts.reverse('analysis:results-list')}?subjects={subjects_to_base64([obj])}"

        return urls

    def get_selected(self, obj):
        try:
            topographies, surfaces, tags = self.context['selected_instances']
            return obj in topographies
        except KeyError:
            return False

    def get_key(self, obj):
        return f"topography-{obj.pk}"

    def get_surface_key(self, obj):
        return f"surface-{obj.surface.pk}"

    def get_sharing_status(self, obj):
        user = self.context['request'].user
        if hasattr(obj.surface, 'is_published') and obj.surface.is_published:
            return 'published'
        elif user == obj.surface.creator:
            return "own"
        else:
            return "shared"

    def get_creator_name(self, obj):
        return obj.creator.name

    def get_label(self, obj):
        return obj.label


class SurfaceSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Surface
        fields = ['id', 'type', 'name', 'creator', 'creator_name', 'description', 'category', 'category_name', 'tags',
                  'children', 'sharing_status', 'urls', 'selected', 'key', 'title', 'folder', 'version',
                  'publication_doi', 'publication_date', 'publication_authors', 'publication_license',
                  'topography_count', 'label']

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
        default=serializers.CurrentUserDefault()
    )

    title = serializers.CharField(source='name')
    children = serializers.SerializerMethodField()

    urls = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    # `folder` is Fancytree-specific, see
    # https://wwwendt.de/tech/fancytree/doc/jsdoc/global.html#NodeData
    folder = serializers.BooleanField(default=True, read_only=True)
    sharing_status = serializers.SerializerMethodField()
    tags = TagRelatedManagerField()
    # `type` should be the output of mangle_content_type(Meta.model)
    type = serializers.CharField(default='surface', read_only=True)
    version = serializers.SerializerMethodField()
    publication_date = serializers.SerializerMethodField()
    publication_authors = serializers.SerializerMethodField()
    publication_license = serializers.SerializerMethodField()
    publication_doi = serializers.SerializerMethodField()
    topography_count = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    creator_name = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()

    def get_children(self, obj):
        """Get serialized topographies for given surface.

        Parameters
        ----------
        obj : Surface

        Returns
        -------

        """
        #
        # We only want topographies as children which match the given search term,
        # if no search term is given, all topographies should be included
        #
        request = self.context['request']
        search_term = get_search_term(request)
        search_term_given = len(search_term) > 0

        # only filter topographies by search term if surface does not match search term
        # otherwise list all topographies
        if search_term_given:
            topographies = filtered_topographies(request, [obj])
        else:
            topographies = obj.topography_set.all()
        return TopographySearchSerializer(topographies, many=True, context=self.context).data

    def get_urls(self, obj):

        user = self.context['request'].user
        perms = get_perms(user, obj)  # TODO are permissions needed here?

        urls = {
            'select': shortcuts.reverse('manager:surface-select', kwargs=dict(pk=obj.pk)),
            'unselect': shortcuts.reverse('manager:surface-unselect', kwargs=dict(pk=obj.pk))
        }
        if 'view_surface' in perms:
            urls['detail'] = f"{shortcuts.reverse('manager:surface-detail')}?surface={obj.pk}",
            if obj.num_topographies() > 0:
                urls.update({
                    'analyze': f"{shortcuts.reverse('analysis:results-list')}?subjects={subjects_to_base64([obj])}"
                })
            urls['download'] = shortcuts.reverse('manager:surface-download', kwargs=dict(surface_id=obj.id))

        if 'publish_surface' in perms:
            urls.update({
                'publish': shortcuts.reverse('manager:surface-publish', kwargs=dict(pk=obj.pk)),
            })

        return urls

    def get_selected(self, obj):
        try:
            topographies, surfaces, tags = self.context['selected_instances']
            return obj in surfaces
        except KeyError:
            return False

    def get_key(self, obj):
        return f"surface-{obj.pk}"

    def get_sharing_status(self, obj):
        user = self.context['request'].user
        if hasattr(obj, 'is_published') and obj.is_published:
            return 'published'
        elif user == obj.creator:
            return "own"
        else:
            return "shared"

    def get_version(self, obj):
        return obj.publication.version if obj.is_published else None

    def get_publication_date(self, obj):
        return obj.publication.datetime.date() if obj.is_published else None

    def get_publication_authors(self, obj):
        return obj.publication.get_authors_string() if obj.is_published else None

    def get_publication_license(self, obj):
        return obj.publication.license if obj.is_published else None

    def get_publication_doi(self, obj):
        return obj.publication.doi_url if obj.is_published else None

    def get_topography_count(self, obj):
        return obj.topography_set.count()

    def get_category_name(self, obj):
        return obj.get_category_display()

    def get_creator_name(self, obj):
        return obj.creator.name

    def get_label(self, obj):
        return obj.label


class TagSearchSerizalizer(serializers.ModelSerializer):
    class Meta:
        model = TagModel
        fields = ['id', 'key', 'type', 'title', 'name', 'children', 'folder', 'urls', 'selected', 'version',
                  'publication_date', 'publication_authors', 'label']

    children = serializers.SerializerMethodField()
    # `folder` is Fancytree-specific, see
    # https://wwwendt.de/tech/fancytree/doc/jsdoc/global.html#NodeData
    folder = serializers.BooleanField(default=True, read_only=True)
    key = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()
    publication_authors = serializers.CharField(default=None, read_only=True)
    publication_date = serializers.CharField(default=None, read_only=True)
    selected = serializers.SerializerMethodField()
    title = serializers.CharField(source='label', read_only=True)
    # `type` should be the output of mangle_content_type(Meta.model)
    type = serializers.CharField(default='tag', read_only=True)
    urls = serializers.SerializerMethodField()
    version = serializers.CharField(default=None, read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._surface_serializer = SurfaceSerializer(context=self.context)
        self._topography_serializer = TopographySerializer(context=self.context)

    def get_urls(self, obj):
        urls = {
            'select': shortcuts.reverse('manager:tag-select', kwargs=dict(pk=obj.pk)),
            'unselect': shortcuts.reverse('manager:tag-unselect', kwargs=dict(pk=obj.pk))
        }
        return urls

    def get_key(self, obj):
        return f"tag-{obj.pk}"

    def get_selected(self, obj):
        topographies, surfaces, tags = self.context['selected_instances']
        return obj in tags

    def get_children(self, obj):
        result = []

        #
        # Assume that all surfaces and topographies given in the context are already filtered
        #
        surfaces = self.context['surfaces'].filter(tags__pk=obj.pk)  # .order_by('name')
        topographies = self.context['topographies'].filter(tags__pk=obj.pk)  # .order_by('name')
        tags = [x for x in obj.children.all() if x in self.context['tags_for_user']]

        #
        # Serialize children and append to this tag
        #
        result.extend(TopographySearchSerializer(topographies, many=True, context=self.context).data)
        result.extend(SurfaceSearchSerializer(surfaces, many=True, context=self.context).data)
        result.extend(TagSearchSerizalizer(tags, many=True, context=self.context).data)

        return result

    def get_label(self, obj):
        return obj.label
