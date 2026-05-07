from __future__ import annotations

from django.urls import path

from .views import (
    assets,
    cancel_process_file,
    dashboard,
    folders,
    process,
    process_review_file,
    review_file_preview,
    update_folders,
    update_process_vendor,
    vendors,
)


app_name = "pipeline_dashboard"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("assets/", assets, name="assets"),
    path("process/", process, name="process"),
    path("process/<str:remote_item_id>/vendor/", update_process_vendor, name="update_process_vendor"),
    path("process/<str:remote_item_id>/cancel/", cancel_process_file, name="cancel_process_file"),
    path("folders/", folders, name="folders"),
    path("folders/update/", update_folders, name="update_folders"),
    path("folders/review/preview/", review_file_preview, name="review_file_preview"),
    path("folders/review/process/", process_review_file, name="process_review_file"),
    path("vendors/", vendors, name="vendors"),
]
