from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse


@api_view(["GET"])
def entry_points(request):
    e = {
        "analysis": reverse("analysis:result-list", request=request),
        "surface": reverse("manager:surface-list", request=request),
        "topography": reverse("manager:topography-list", request=request),
    }

    if request.user.is_staff:
        e["admin"] = reverse("admin:index", request=request)

    return Response(e)
