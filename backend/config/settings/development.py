"""Development Django settings."""

from config.settings.base import *  # noqa: F403

DEBUG = True
CORS_ALLOW_ALL_ORIGINS = False
EXTRACTION_EXECUTION_MODE = os.environ.get("EXTRACTION_EXECUTION_MODE", "eager")  # noqa: F405
CELERY_TASK_ALWAYS_EAGER = EXTRACTION_EXECUTION_MODE == "eager"
