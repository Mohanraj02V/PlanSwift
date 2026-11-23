"""Base Django settings for Vortexen Estimator."""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent.parent
WORKSPACE_ROOT = BASE_DIR.parent

for p in (str(WORKSPACE_ROOT), str(BASE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-vortexen-key-change-in-production-50chars")
DEBUG = False
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]

AUTH_USER_MODEL = "accounts.User"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    # Domain: Identity & Governance
    "apps.accounts",
    "apps.organizations",
    "apps.permissions",
    "apps.audit_logs",
    "apps.notifications",
    # Domain: Projects & Ingestion
    "apps.projects",
    "apps.project_sources",
    "apps.source_inventory",
    "apps.planswift_connector",
    "apps.extraction",
    "apps.background_jobs",
    # Domain: Canonical Digital Project Model
    "apps.object_model",
    "apps.object_hierarchy",
    "apps.measurements",
    "apps.geometry",
    "apps.formulas",
    "apps.classifications",
    "apps.dimensions",
    "apps.annotations",
    "apps.assemblies",
    "apps.components",
    "apps.denotations",
    "apps.remarks",
    # Domain: Validation, Reconciliation, Estimation & Export
    "apps.validation",
    "apps.reconciliation",
    "apps.estimation",
    "apps.exports",
    "apps.integrations",
    # Domain: Independent AI & RAG Estimation
    "apps.ai_providers",
    "apps.ai_prompts",
    "apps.knowledge_base",
    "apps.retrieval",
    "apps.ai_agents",
    "apps.ai_assistant",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


def _build_database_config() -> dict:
    db_url = os.environ.get("DATABASE_URL", "")
    enable_postgis = os.environ.get("ENABLE_POSTGIS", "false").lower() == "true"
    if not db_url or db_url.startswith("sqlite"):
        sqlite_name = db_url.replace("sqlite:///", "") if db_url else str(BASE_DIR / "db.sqlite3")
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": sqlite_name,
                "OPTIONS": {"timeout": 30},
            }
        }
    parsed = urlparse(db_url)
    engine = "django.contrib.gis.db.backends.postgis" if enable_postgis else "django.db.backends.postgresql"
    return {
        "default": {
            "ENGINE": engine,
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
            "CONN_MAX_AGE": 60,
        }
    }


DATABASES = _build_database_config()
ENABLE_POSTGIS = os.environ.get("ENABLE_POSTGIS", "false").lower() == "true"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.exceptions.sanitized_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "600/minute",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Vortexen Estimator API",
    "DESCRIPTION": "PlanSwift Native Project Extraction, Canonical Digital Project Model, and Provenance-Aware AI Estimation API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
]

DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024  # 50 MiB API payload limit (large SwiftJobs use local extraction path)
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

# Source Ingestion Security
ALLOWED_SOURCE_ROOTS = [
    str(Path(p.strip()).resolve())
    for p in os.environ.get("ALLOWED_SOURCE_ROOTS", str(WORKSPACE_ROOT)).split(";")
    if p.strip()
]
PLANSWIFT_DEFAULT_SOURCE_PATH = os.environ.get("PLANSWIFT_SOURCE_PATH", str(WORKSPACE_ROOT / "project 4.SwiftJob.zip"))
EXTRACTION_WORK_DIR = Path(os.environ.get("EXTRACTION_WORK_DIR", str(WORKSPACE_ROOT / "extracted_tmp")))
EXTRACTION_EXECUTION_MODE = os.environ.get("EXTRACTION_EXECUTION_MODE", "eager")  # eager | thread | celery

# Celery & Redis
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_TASK_ALWAYS_EAGER = EXTRACTION_EXECUTION_MODE == "eager"

# Windows Connector Ingest Auth
CONNECTOR_SHARED_TOKEN = os.environ.get("CONNECTOR_SHARED_TOKEN", "")
CONNECTOR_REQUIRE_TLS = os.environ.get("CONNECTOR_REQUIRE_TLS", "false").lower() == "true"

# AI Provider Settings (strictly independent from extraction_engine)
AI_PROVIDER = os.environ.get("AI_PROVIDER", "deterministic")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "deterministic-v1")
AI_TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS", "30"))
AI_MAX_RETRIES = int(os.environ.get("AI_MAX_RETRIES", "2"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "structured"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
