import logging

from django.shortcuts import reverse
from guardian.shortcuts import get_perms
from rest_framework import serializers

from .models import Surface, Topography, TagModel
from .utils import get_search_term, filtered_topographies, subjects_to_base64, mangle_content_type

_log = logging.getLogger(__name__)


class TopographySerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Topography
        fields = ['id', 'type', 'name', 'creator', 'description', 'tags',
                  'urls', 'selected', 'key', 'surface_key', 'title', 'folder', 'version',
                  'publication_date', 'publication_authors', 'creator_name', 'sharing_status', 'label']

    title = serializers.CharField(source='name', read_only=True)  # set this through name

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
        default=serializers.CurrentUserDefault()
    )

    urls = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    surface_key = serializers.SerializerMethodField()
    sharing_status = serializers.SerializerMethodField()
    # `folder` is Fancytree-specific, see
    # https://wwwendt.de/tech/fancytree/doc/jsdoc/global.html#NodeData
    folder = serializers.BooleanField(default=False, read_only=True)
    tags = serializers.SerializerMethodField()
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
            'select': reverse('manager:topography-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:topography-unselect', kwargs=dict(pk=obj.pk))
        }

        if 'view_surface' in perms:
            urls['detail'] = reverse('manager:topography-detail', kwargs=dict(pk=obj.pk))
            urls['analyze'] = f"{reverse('analysis:results-list')}?subjects={subjects_to_base64([obj])}"

        if 'change_surface' in perms:
            urls.update({
                'update': reverse('manager:topography-update', kwargs=dict(pk=obj.pk))
            })

        if 'delete_surface' in perms:
            urls['delete'] = reverse('manager:topography-delete', kwargs=dict(pk=obj.pk))

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

    def get_tags(self, obj):  # TODO prove if own method needed
        return [t.name for t in obj.tags.all()]

    def get_creator_name(self, obj):
        return obj.creator.name

    def get_label(self, obj):
        return obj.label


class SurfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Surface
        fields = ['id', 'name', 'creator', 'description', 'category', 'tags', 'urls']

    urls = serializers.SerializerMethodField()

    def get_urls(self, obj):

        user = self.context['request'].user
        perms = get_perms(user, obj)  # TODO are permissions needed here?

        urls = {
            'select': reverse('manager:surface-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:surface-unselect', kwargs=dict(pk=obj.pk))
        }
        if 'view_surface' in perms:
            urls['detail'] = reverse('manager:surface-detail', kwargs=dict(pk=obj.pk))
            if obj.num_topographies() > 0:
                urls.update({
                    'analyze': f"{reverse('analysis:results-list')}?subjects={subjects_to_base64([obj])}"
                })
            urls['download'] = reverse('manager:surface-download', kwargs=dict(surface_id=obj.id))

        if 'change_surface' in perms:
            urls.update({
                'add_topography': reverse('manager:topography-create', kwargs=dict(surface_id=obj.id)),
                'update': reverse('manager:surface-update', kwargs=dict(pk=obj.pk)),
            })
        if 'delete_surface' in perms:
            urls.update({
                'delete': reverse('manager:surface-delete', kwargs=dict(pk=obj.pk)),
            })
        if 'share_surface' in perms:
            urls.update({
                'share': reverse('manager:surface-share', kwargs=dict(pk=obj.pk)),
            })
        if 'publish_surface' in perms:
            urls.update({
                'publish': reverse('manager:surface-publish', kwargs=dict(pk=obj.pk)),
            })

        return urls


class SearchSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Surface
        fields = ['id', 'type', 'name', 'creator', 'creator_name', 'description', 'category', 'category_name', 'tags',
                  'children', 'sharing_status', 'urls', 'selected', 'key', 'title', 'folder', 'version',
                  'publication_doi', 'publication_date', 'publication_authors', 'publication_license',
                  'topography_count', 'label']

    title = serializers.CharField(source='name')
    children = serializers.SerializerMethodField()

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username'
    )

    urls = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    # `folder` is Fancytree-specific, see
    # https://wwwendt.de/tech/fancytree/doc/jsdoc/global.html#NodeData
    folder = serializers.BooleanField(default=True, read_only=True)
    sharing_status = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
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
        return TopographySerializer(topographies, many=True, context=self.context).data

    def get_urls(self, obj):

        user = self.context['request'].user
        perms = get_perms(user, obj)  # TODO are permissions needed here?

        urls = {
            'select': reverse('manager:surface-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:surface-unselect', kwargs=dict(pk=obj.pk))
        }
        if 'view_surface' in perms:
            urls['detail'] = reverse('manager:surface-detail', kwargs=dict(pk=obj.pk))
            if obj.num_topographies() > 0:
                urls.update({
                    'analyze': f"{reverse('analysis:results-list')}?subjects={subjects_to_base64([obj])}"
                })
            urls['download'] = reverse('manager:surface-download', kwargs=dict(surface_id=obj.id))

        if 'change_surface' in perms:
            urls.update({
                'add_topography': reverse('manager:topography-create', kwargs=dict(surface_id=obj.id)),
                'update': reverse('manager:surface-update', kwargs=dict(pk=obj.pk)),
            })
        if 'delete_surface' in perms:
            urls.update({
                'delete': reverse('manager:surface-delete', kwargs=dict(pk=obj.pk)),
            })
        if 'share_surface' in perms:
            urls.update({
                'share': reverse('manager:surface-share', kwargs=dict(pk=obj.pk)),
            })
        if 'publish_surface' in perms:
            urls.update({
                'publish': reverse('manager:surface-publish', kwargs=dict(pk=obj.pk)),
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

    def get_tags(self, obj):
        return [t.name for t in obj.tags.all()]

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


class TagSerializer(serializers.ModelSerializer):
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
            'select': reverse('manager:tag-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:tag-unselect', kwargs=dict(pk=obj.pk))
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
        result.extend(TopographySerializer(topographies, many=True, context=self.context).data)
        result.extend(SurfaceSerializer(surfaces, many=True, context=self.context).data)
        result.extend(TagSerializer(tags, many=True, context=self.context).data)

        return result

    def get_label(self, obj):
        return obj.label
