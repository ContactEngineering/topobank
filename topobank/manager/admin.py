from django.contrib import admin
from tagulous.admin import TagModelAdmin
import tagulous.models.fields

from .models import Surface, Topography, Tag

# Monkey-patch FakeQuerySet to display properly in admin
# This is needed for Django 5.2 compatibility with tagulous
_original_fakequeryset_str = tagulous.models.fields.FakeQuerySet.__str__
def _fakequeryset_str(self):
    """Return the tag string instead of object representation"""
    if hasattr(self.obj, 'pk') and isinstance(self.obj.pk, str):
        return self.obj.pk
    return _original_fakequeryset_str(self)

tagulous.models.fields.FakeQuerySet.__str__ = _fakequeryset_str


class TagFieldAdminMixin:
    """Mixin to fix TagField compatibility with Django 5.2
    
    If we upgrade to a tagulous version that supports Django 5.2,
    this mixin can be removed.
    """

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Override to handle TagField compatibility with Django 5.2"""
        import tagulous.models as tm
        from tagulous.forms import AdminTagWidget

        if isinstance(db_field, tm.TagField):
            # For TagFields, bypass Django's queryset injection and call formfield directly
            # Remove any queryset that might have been passed
            kwargs.pop('queryset', None)

            # Ensure we use the admin widget
            if 'widget' not in kwargs:
                kwargs['widget'] = AdminTagWidget

            # Get the form field from tagulous
            formfield = db_field.formfield(**kwargs)

            # Ensure autocomplete_tags is set (the tag model's queryset)
            if hasattr(db_field, 'tag_model') and formfield:
                if not hasattr(formfield, 'autocomplete_tags') or formfield.autocomplete_tags is None:
                    formfield.autocomplete_tags = db_field.tag_model.objects.all()

            return formfield

        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """Override to handle TagField compatibility"""
        import tagulous.models as tm
        from tagulous.forms import AdminTagWidget

        # For TagFields, ensure queryset is not passed
        if isinstance(db_field, (tm.TagField, tm.SingleTagField)):
            kwargs.pop('queryset', None)

            # Ensure we use the admin widget for tag fields
            if 'widget' not in kwargs:
                kwargs['widget'] = AdminTagWidget

            # Call the field's formfield directly
            formfield = db_field.formfield(**kwargs)

            # Ensure autocomplete_tags is set
            if hasattr(db_field, 'tag_model') and formfield:
                if not hasattr(formfield, 'autocomplete_tags') or formfield.autocomplete_tags is None:
                    formfield.autocomplete_tags = db_field.tag_model.objects.all()

            return formfield

        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Surface)
class SurfaceAdmin(TagFieldAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "creation_time")
    ordering = ["-creation_time"]


@admin.register(Topography)
class TopographyAdmin(TagFieldAdminMixin, admin.ModelAdmin):
    list_display = ("id", "name", "creation_time", "task_state", "task_id")
    list_filter = ("task_state",)
    ordering = ["-creation_time"]


@admin.register(Tag)
class TagAdmin(TagFieldAdminMixin, TagModelAdmin):
    list_display = ("id", "name", "label", "parent")
    ordering = ["id"]
    search_fields = ("name", "label")
