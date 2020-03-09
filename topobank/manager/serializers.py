from django.shortcuts import reverse

from rest_framework import serializers
from guardian.shortcuts import get_perms

import logging

from .models import Surface, Topography, TagModel

_log = logging.getLogger(__name__)

class TopographySerializer(serializers.HyperlinkedModelSerializer):

    title = serializers.CharField(source='name')

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
    )

    urls = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    surface_key = serializers.SerializerMethodField()
    folder = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    def get_urls(self, obj):
        """Return only those urls which are usable for the usser

        :param obj: topography object
        :return: dict with { url_name: url }
        """
        user = self.context['request'].user
        surface = obj.surface

        perms = get_perms(user, surface)

        urls = {
            'select': reverse('manager:topography-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:topography-unselect', kwargs=dict(pk=obj.pk))
        }

        if 'view_surface' in perms:
            urls['detail'] = reverse('manager:topography-detail', kwargs=dict(pk=obj.pk))
            urls['analyze'] = reverse('analysis:topography', kwargs=dict(topography_id=obj.pk))

        if 'change_surface' in perms:
            urls.update({
                'update': reverse('manager:topography-update', kwargs=dict(pk=obj.pk))
            })

        if 'delete_surface' in perms:
            urls['delete'] = reverse('manager:topography-delete', kwargs=dict(pk=obj.pk))

        return urls

    def get_selected(self, obj):
        topographies, surfaces = self.context['selected_instances']
        return (obj in topographies) or (obj.surface in surfaces)

    def get_key(self, obj):
        return f"topography-{obj.pk}"

    def get_surface_key(self, obj):
        return f"surface-{obj.surface.pk}"

    def get_folder(self, obj):
        return False

    def get_tags(self, obj):  # TODO prove if own method needed
        return [t.name for t in obj.tags.all()]

    def get_type(self, obj):
        return "topography"

    class Meta:
        model = Topography
        fields = ['pk', 'type', 'name', 'creator', 'description', 'tags',
                  'urls', 'selected',
                  'key', 'surface_key', 'title', 'folder']


class SurfaceSerializer(serializers.HyperlinkedModelSerializer):

    title = serializers.CharField(source='name')
    children = TopographySerializer(source='topography_set', many=True)

    creator = serializers.HyperlinkedRelatedField(
        read_only=True,
        view_name='users:detail',
        lookup_field='username',
    )

    urls = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    folder = serializers.SerializerMethodField()
    sharing_status = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()

    def get_urls(self, obj):

        user = self.context['request'].user
        perms = get_perms(user, obj)

        urls =  {
            'select': reverse('manager:surface-select', kwargs=dict(pk=obj.pk)),
            'unselect': reverse('manager:surface-unselect', kwargs=dict(pk=obj.pk))
        }
        if 'view_surface' in perms:
            urls['detail'] = reverse('manager:surface-detail', kwargs=dict(pk=obj.pk))
            if obj.num_topographies() > 0:
                urls.update({
                    'analyze': reverse('analysis:surface', kwargs=dict(surface_id=obj.id)),
                    'download': reverse('manager:surface-download', kwargs=dict(surface_id=obj.id)),

                })
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

        return urls

    def get_selected(self, obj):
        topographies, surfaces  = self.context['selected_instances']
        # _log.info("Surface selected? %s in %s?", obj, surfaces)
        return obj in surfaces

    def get_key(self, obj):
        return f"surface-{obj.pk}"

    def get_sharing_status(self, obj):
        user = self.context['request'].user
        if user == obj.creator:
            return "own"
        else:
            return "shared"

    def get_folder(self, obj):
        return True

    def get_tags(self, obj): # TODO prove if own method needed
        return [ t.name for t in obj.tags.all()]

    def get_type(self, obj):
        return "surface"

    class Meta:
        model = Surface
        fields = ['pk', 'type', 'name', 'creator', 'description', 'category', 'tags', 'children',
                  'sharing_status', 'urls', 'selected', 'key', 'title', 'folder']


class TagSerializer(serializers.ModelSerializer):

    title = serializers.CharField(source='label')
    children = serializers.SerializerMethodField()
    folder = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    key = serializers.SerializerMethodField()
    selected = serializers.SerializerMethodField()

    class Meta:
        model = TagModel
        fields = ['pk', 'key', 'type', 'title', 'name', 'children', 'folder', 'selected']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._surface_serializer = SurfaceSerializer(context=self.context)
        self._topography_serializer = TopographySerializer(context=self.context)

    def get_folder(self, obj):
        return True

    def get_type(self, obj):
        return "tag"

    def get_key(self, obj):
        return f"tag-{obj.pk}"

    def get_selected(self, obj):
        return False
        # So far tags should not be considered as selected.
        # It would be an interesting enhancement to also allow the selection of tags,
        # but that's not yet implemented.

    def get_children(self, obj):

        result = []

        surfaces = self.context['surfaces'].filter(tags__name=obj.name)
        topographies = self.context['topographies'].filter(tags__name=obj.name)

        for t in topographies:
            result.append(self._topography_serializer.to_representation(t))

        for s in surfaces:
            result.append(self._surface_serializer.to_representation(s))

        if obj.pk is not None:
            # find all tags which are direct children of current tag and available for this user
            result.extend(self.to_representation(x) for x in obj.children.all() if x in self.context['tags_for_user'])

        return result


