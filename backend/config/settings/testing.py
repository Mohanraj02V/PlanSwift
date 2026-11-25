"""Automated test Django settings."""

from config.settings.base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-only-vortexen-secret-key-not-used-in-production-50chars"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EXTRACTION_EXECUTION_MODE = "eager"
CELERY_TASK_ALWAYS_EAGER = True
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "anon": "10000/minute",
    "user": "10000/minute",
    "auth_login": "10/minute",
    "auth_refresh": "30/minute",
}
