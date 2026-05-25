from __future__ import annotations

from django.urls import path

from .views import (
    approve_parsed_output,
    approve_process_file,
    cancel_parsed_output,
    cancel_process_file,
    assign_vendor_folder,
    create_vendor,
    dashboard,
    delete_vendor,
    folders,
    parse_file_preview,
    parse_process_file,
    parse_sheet_probe,
    process,
    process_review_file,
    review_file_preview,
    toggle_is_active,
    update_folders,
    update_process_vendor,
    update_vendor,
    vendors,
)


app_name = "pipeline_dashboard"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("process/", process, name="process"),
    path("process/<str:remote_item_id>/vendor/", update_process_vendor, name="update_process_vendor"),
    path("process/<str:remote_item_id>/cancel/", cancel_process_file, name="cancel_process_file"),
    path("process/<str:remote_item_id>/parse/preview/", parse_file_preview, name="parse_file_preview"),
    path("process/<str:remote_item_id>/parse/probe/", parse_sheet_probe, name="parse_sheet_probe"),
    path("process/<str:remote_item_id>/parse/", parse_process_file, name="parse_process_file"),
    path("process/<str:remote_item_id>/approve/", approve_process_file, name="approve_process_file"),
    path("process/approval/<int:parsed_output_id>/approved/", approve_parsed_output, name="approve_parsed_output"),
    path("process/approval/<int:parsed_output_id>/cancel/", cancel_parsed_output, name="cancel_parsed_output"),
    path("folders/", folders, name="folders"),
    path("folders/update/", update_folders, name="update_folders"),
    path("folders/review/preview/", review_file_preview, name="review_file_preview"),
    path("folders/review/process/", process_review_file, name="process_review_file"),
    path("folders/toggle-active/", toggle_is_active, name="toggle_is_active"),
    path("vendors/", vendors, name="vendors"),
    path("vendors/create/", create_vendor, name="create_vendor"),
    path("vendors/<int:vendor_id>/update/", update_vendor, name="update_vendor"),
    path("vendors/<int:vendor_id>/delete/", delete_vendor, name="delete_vendor"),
    path("vendors/folders/<int:folder_id>/assign/", assign_vendor_folder, name="assign_vendor_folder"),
]
