from __future__ import annotations

from typing import Any

from apps.audit_logs.models import AuditLog


def _extract_ip(request) -> str | None:
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_audit_event(
    action: str,
    actor=None,
    organization=None,
    request=None,
    resource_type: str = "",
    resource_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    user = actor if getattr(actor, "is_authenticated", False) else None
    ua = request.META.get("HTTP_USER_AGENT", "")[:512] if request is not None else ""
    return AuditLog.objects.create(
        organization=organization,
        actor=user,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else "",
        ip_address=_extract_ip(request),
        user_agent=ua,
        metadata=metadata or {},
    )
