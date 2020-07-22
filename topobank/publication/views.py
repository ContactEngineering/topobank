from django.shortcuts import redirect

from .models import Publication


def go(request, ref):
    pub = Publication.objects.get(uuid=ref)
    return redirect(pub)
