from __future__ import annotations

from django.apps import AppConfig


class PipelineDashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pipeline_dashboard"
    verbose_name = "Pipeline Dashboard"
