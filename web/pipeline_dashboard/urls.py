from __future__ import annotations

from django.urls import path

from .views import (
    approve_parsed_output,
    approve_process_file,
    cancel_parsed_output,
    cancel_process_file,
    dashboard,
    folders,
    parse_file_preview,
    parse_process_file,
    process,
    process_review_file,
    review_file_preview,
    update_folders,
    update_process_vendor,
)


app_name = "pipeline_dashboard"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("process/", process, name="process"),
    path("process/<str:remote_item_id>/vendor/", update_process_vendor, name="update_process_vendor"),
    path("process/<str:remote_item_id>/cancel/", cancel_process_file, name="cancel_process_file"),
    path("process/<str:remote_item_id>/parse/preview/", parse_file_preview, name="parse_file_preview"),
    path("process/<str:remote_item_id>/parse/", parse_process_file, name="parse_process_file"),
    path("process/<str:remote_item_id>/approve/", approve_process_file, name="approve_process_file"),
    path("process/approval/<int:parsed_output_id>/approved/", approve_parsed_output, name="approve_parsed_output"),
    path("process/approval/<int:parsed_output_id>/cancel/", cancel_parsed_output, name="cancel_parsed_output"),
    path("folders/", folders, name="folders"),
    path("folders/update/", update_folders, name="update_folders"),
    path("folders/review/preview/", review_file_preview, name="review_file_preview"),
    path("folders/review/process/", process_review_file, name="process_review_file"),
]
