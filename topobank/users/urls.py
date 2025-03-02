from rest_framework.routers import DefaultRouter

from . import views

app_name = "users"

router = DefaultRouter()
router.register(r'api/user', views.UserViewSet, basename='user-api')

urlpatterns = router.urls
