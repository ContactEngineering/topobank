from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views

app_name = "users"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register(r'api/user', views.UserViewSet, basename='user-api')

urlpatterns = router.urls
