from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.urls import path, re_path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'api/tag', views.TagViewSet, basename='tag-api')
router.register(r'api/topography', views.TopographyViewSet, basename='topography-api')
router.register(r'api/surface', views.SurfaceViewSet, basename='surface-api')
router.register(r'api/property', views.PropertyViewSet, basename='property-api')
router.register(r'api/file', views.FileManifestViewSet, basename='file-api')

urlpatterns = router.urls

# Note: We only require a login for routes that can change a dataset. We don't
# require a login to see the dataset, because the anonymous user should be
# allowed to see its datasets. (Those are the ones that were published.)

app_name = "manager"
urlpatterns += [
    path('api/upload/direct/start/', view=views.FileDirectUploadStartApi.as_view()),
    path('api/upload/direct/finish/', view=views.FileDirectUploadFinishApi.as_view()),
    #
    # Data routes
    #
    re_path(
        r'api/topography/(?P<pk>\d+)/dzi/(?P<dzi_filename>.*)$',
        view=views.dzi,
        name='topography-dzi'
    ),
    re_path(
        r'api/surface/(?P<surface_id>\d+)/download/$',
        view=views.download_surface,
        name='surface-download'
    ),
    #
    # API routes
    #
    path(
        'api/topography/<pk>/force-inspect/',
        view=login_required(views.force_inspect),
        name='force-inspect'
    ),
    path(
        'api/surface/<pk>/set-permissions/',
        view=login_required(views.set_permissions),
        name='set-permissions'
    ),
    path(
        'api/tag/<pk>/numerical-properties/',
        view=login_required(views.tag_numerical_properties),
        name='numerical-properties'
    ),
    path(
        'api/tag/<pk>/categorical-properties/',
        view=login_required(views.tag_categorical_properties),
        name='categorical-properties'
    ),
    path(
        'api/import-surface/',
        view=login_required(views.import_surface),
        name='import-surface'
    ),
    path(
        'api/versions/',
        view=views.versions,
        name='versions'
    ),
    path(
        'api/statistics/',
        view=views.statistics,
        name='statistics'
    ),
    # GET
    # * Return memory usage of inspection tasks
    path(
        'api/memory-usage/',
        view=views.memory_usage,
        name='memory-usage'
    )
]

if not settings.USE_S3_STORAGE:
    urlpatterns += [path(
        'api/topography/<pk>/upload/',
        view=login_required(views.upload_topography),
        name='upload-topography'
    )]
    urlpatterns += [path(
        'api/upload/direct/local/<str:file_id>/',
        view=views.FileDirectUploadLocalApi.as_view(),
        name="upload-direct-local"
    )]
