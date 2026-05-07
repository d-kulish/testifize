from __future__ import annotations

from django.urls import path

from .views import assets, dashboard, folders, update_folders, vendors


app_name = "pipeline_dashboard"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("assets/", assets, name="assets"),
    path("folders/", folders, name="folders"),
    path("folders/update/", update_folders, name="update_folders"),
    path("vendors/", vendors, name="vendors"),
]
