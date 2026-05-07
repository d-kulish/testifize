from __future__ import annotations

from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("", include("pipeline_dashboard.urls")),
    path("admin/", admin.site.urls),
]
