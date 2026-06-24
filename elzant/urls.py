"""URL configuration for the elzant project."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]

# In DEBUG, django.contrib.staticfiles serves files from STATICFILES_DIRS
# automatically via runserver, so no extra static() route is needed here.
