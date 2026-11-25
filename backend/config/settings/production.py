"""Production Django settings enforcing strict security headers, HTTPS, cookie flags, and fail-fast env checks."""

from config.settings.base import *  # noqa: F403

DEBUG = False

if not SECRET_KEY or SECRET_KEY.startswith("dev-insecure") or len(SECRET_KEY) < 50:  # noqa: F405
    raise RuntimeError("SECRET_KEY environment variable must be set securely (>=50 chars) in production.")

if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("ALLOWED_HOSTS must be explicitly configured without wildcards in production.")

if not CORS_ALLOWED_ORIGINS:  # noqa: F405
    raise RuntimeError("CORS_ALLOWED_ORIGINS must be explicitly configured in production.")

if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    raise RuntimeError("CSRF_TRUSTED_ORIGINS must be explicitly configured in production.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
JWT_COOKIE_SECURE = True
JWT_COOKIE_SAMESITE = "Lax"
ENABLE_API_DOCS = False

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
