"""Resumable Celery / thread / eager background tasks for extraction runs."""

from __future__ import annotations

import threading

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.background_jobs.models import BackgroundJob
from apps.extraction.services import ExtractionOrchestrationService


@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def run_extraction_task(self, run_id: str, job_id: str | None = None) -> dict[str, str]:
    job = BackgroundJob.objects.filter(id=job_id).first() if job_id else None
    if job:
        job.status = "RUNNING"
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])
    try:
        run = ExtractionOrchestrationService.execute_run(run_id)
        if job:
            job.status = run.status
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "finished_at"])
        return {"run_id": str(run.id), "status": run.status}
    except Exception as exc:
        if job:
            job.status = "FAILED"
            job.error_message = str(exc)
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error_message", "finished_at"])
        raise


def dispatch_extraction_run(run, actor) -> BackgroundJob:
    job = BackgroundJob.objects.create(
        organization=run.project.organization,
        task_name="run_extraction_task",
        resource_type="ExtractionRun",
        resource_id=str(run.id),
        status="PENDING",
    )
    mode = getattr(settings, "EXTRACTION_EXECUTION_MODE", "eager").lower()
    if mode == "celery":
        res = run_extraction_task.delay(str(run.id), str(job.id))
        job.celery_task_id = str(res.id)
        job.save(update_fields=["celery_task_id"])
    elif mode == "thread":
        t = threading.Thread(target=run_extraction_task, args=(str(run.id), str(job.id)), daemon=True)
        t.start()
    else:
        run_extraction_task(str(run.id), str(job.id))
    return job
