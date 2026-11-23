"""Celery configuration for Vortexen Estimator."""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("vortexen_estimator")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
