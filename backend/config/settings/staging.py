"""Staging Django settings."""

from config.settings.base import *  # noqa: F403

DEBUG = False
if not SECRET_KEY or SECRET_KEY.startswith("dev-insecure") or len(SECRET_KEY) < 50:  # noqa: F405
    raise RuntimeError("SECRET_KEY must be explicitly set (>=50 chars) in staging.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
JWT_COOKIE_SECURE = True
JWT_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
