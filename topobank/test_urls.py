from django.urls import include, path

urlpatterns = [
    path(
        "",
        include(
            [
                path(
                    "users/",
                    include("topobank_rest_api.users.urls", namespace="users"),
                ),
                path(
                    "organizations/",
                    include("topobank_rest_api.organizations.urls", namespace="organizations"),
                ),
                path(
                    "authorization/",
                    include("topobank_rest_api.authorization.urls", namespace="authorization"),
                ),
                path(
                    "files/",
                    include("topobank_rest_api.files.urls", namespace="files"),
                ),
                path(
                    "manager/",
                    include("topobank_rest_api.manager.urls", namespace="manager"),
                ),
                path(
                    "analysis/",
                    include("topobank_rest_api.analysis.urls", namespace="analysis"),
                ),
                path(
                    "watchman/",
                    include(("watchman.urls", "watchman"), namespace="watchman"),
                ),
            ]
        ),
    ),
]
