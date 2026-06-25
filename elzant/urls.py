"""URL configuration for the elzant project."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]

# In DEBUG, django.contrib.staticfiles serves STATICFILES_DIRS via runserver.
# Media (user uploads) needs an explicit route in development — and optionally in
# production when no file-serving proxy is in front (SERVE_MEDIA=True). WhiteNoise
# only serves static files, never user media, so without one of these /media/ 404s.
if settings.DEBUG or settings.SERVE_MEDIA:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
