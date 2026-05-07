from __future__ import annotations

from django.urls import path

from .views import assets, dashboard, folders, vendors


app_name = "pipeline_dashboard"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("assets/", assets, name="assets"),
    path("folders/", folders, name="folders"),
    path("vendors/", vendors, name="vendors"),
]
