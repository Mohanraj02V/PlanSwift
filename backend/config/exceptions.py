"""Sanitized DRF exception handler preventing leakage of internal paths or stack traces."""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("vortexen.api")


def sanitized_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    response = exception_handler(exc, context)
    if response is not None:
        return Response(
            {
                "error": {
                    "code": getattr(exc, "default_code", "api_error"),
                    "status": response.status_code,
                    "detail": response.data,
                }
            },
            status=response.status_code,
        )

    if isinstance(exc, APIException):
        return Response(
            {"error": {"code": exc.default_code, "status": exc.status_code, "detail": str(exc.detail)}},
            status=exc.status_code,
        )

    logger.exception("Unhandled server exception in %s", context.get("view"))
    return Response(
        {
            "error": {
                "code": "internal_server_error",
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "detail": "An unexpected internal error occurred.",
            }
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
