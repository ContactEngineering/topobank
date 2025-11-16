"""DRF View Mixins for common functionality."""


from topobank.organizations.models import Organization


class UserUpdateMixin:
    """Mixin that tracks which user created and updated objects.

    Automatically sets created_by and updated_by fields based on the
    authenticated user making the request.

    Usage:
        class MyViewSet(UserUpdateMixin, viewsets.ModelViewSet):
            # Your view implementation
            pass
    """

    def perform_create(self, serializer):
        """Set created_by and updated_by when creating objects."""
        # Can't call super() here because we need to pass kwargs to save()
        user = self.request.user
        owned_by = Organization.objects.for_user(user).first()  # TODO: Limit to one organization per user
        serializer.save(owned_by=owned_by, created_by=user, updated_by=user)

    def perform_update(self, serializer):
        """Set updated_by when updating objects."""
        # Set the field on the instance then call super() to maintain MRO chain
        serializer.instance.updated_by = self.request.user
        super().perform_update(serializer)
