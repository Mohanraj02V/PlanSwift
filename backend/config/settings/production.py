"""Production Django settings enforcing strict security headers, HTTPS, and secret checks."""

from config.settings.base import *  # noqa: F403

DEBUG = False
if SECRET_KEY.startswith("dev-insecure"):  # noqa: F405
    raise RuntimeError("SECRET_KEY environment variable must be set securely in production.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CONNECTOR_REQUIRE_TLS = True
