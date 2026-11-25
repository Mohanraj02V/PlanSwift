"""Cookie-first + Authorization-header JWT authentication with CSRF & token_version revocation."""

from __future__ import annotations

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication


class _CSRFDummyView(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


def enforce_csrf(request) -> None:
    """Enforce Django CSRF validation on unsafe cookie-authenticated requests."""
    check = _CSRFDummyView(lambda req: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise PermissionDenied(f"CSRF Failed: {reason}")


class CookieAwareJWTAuthentication(JWTAuthentication):
    """Authenticate via Authorization Bearer header or HttpOnly access cookie + CSRF + token_version check."""

    def authenticate(self, request):
        header = self.get_header(request)
        used_cookie = False
        if header is not None:
            raw_token = self.get_raw_token(header)
        else:
            cookie_name = getattr(settings, "JWT_ACCESS_COOKIE_NAME", "vortexen_access")
            raw_token = request.COOKIES.get(cookie_name)
            if raw_token is not None:
                raw_token = raw_token.encode("utf-8")
                used_cookie = True

        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)

        if not getattr(user, "is_active", False):
            raise AuthenticationFailed("User account is inactive.", code="user_inactive")

        token_ver = validated_token.get("token_version", 1)
        if int(token_ver) != int(getattr(user, "token_version", 1)):
            raise AuthenticationFailed("Session revoked due to credential or role update.", code="token_revoked")

        if used_cookie and request.method not in ("GET", "HEAD", "OPTIONS", "TRACE"):
            enforce_csrf(request)

        return (user, validated_token)


try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class CookieAwareJWTScheme(OpenApiAuthenticationExtension):
        target_class = "apps.accounts.authentication.CookieAwareJWTAuthentication"
        name = "cookieJwtAuth"

        def get_security_definition(self, auto_schema):
            return {
                "type": "apiKey",
                "in": "cookie",
                "name": getattr(settings, "JWT_ACCESS_COOKIE_NAME", "vortexen_access"),
            }
except Exception:
    pass
