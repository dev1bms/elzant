"""URL configuration for the elzant project."""

import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]

# Media (user uploads) needs an explicit route. WhiteNoise only serves static
# files, never user media, so without one of these /media/ 404s.
_media_re = r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/"))
if settings.DEBUG:
    # django.contrib.staticfiles serves /static/ via runserver; add /media/ too.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    # static() is a no-op when DEBUG is False, so register the route directly.
    # For the Gunicorn-behind-Cloudflare-Tunnel deploy with no file proxy.
    urlpatterns += [re_path(_media_re, serve, {"document_root": settings.MEDIA_ROOT})]
