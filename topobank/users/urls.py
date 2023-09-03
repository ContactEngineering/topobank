from django.urls import path

from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'api/user', views.UserViewSet, basename='user-api')

urlpatterns = router.urls

app_name = "users"
urlpatterns += [
    # path("", view=views.UserListView.as_view(), name="list"),
    path("~redirect/", view=views.UserRedirectView.as_view(), name="redirect"),
    path("~update/", view=views.UserUpdateView.as_view(), name="update"),
    path(
        "<str:username>/",
        view=views.UserDetailView.as_view(),
        name="detail",
    ),
]
