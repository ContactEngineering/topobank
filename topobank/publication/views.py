from django.shortcuts import redirect

from .models import Publication


def go(request, short_url):
    pub = Publication.objects.get(short_url=short_url)
    return redirect(pub.surface.get_absolute_url())
