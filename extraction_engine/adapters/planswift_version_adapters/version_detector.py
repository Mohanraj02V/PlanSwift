"""PlanSwift version and COM registration detector."""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PlanSwiftEnvironmentInfo:
    """Reports host OS, process bitness, and PlanSwift COM registry status."""

    os_name: str
    is_windows: bool
    python_bitness: int
    com_registered_progids: list[str]
    recommended_progid: str | None
    supports_live_com: bool
    reason: str


def detect_planswift_environment() -> PlanSwiftEnvironmentInfo:
    """Safely inspect Windows COM registry without fabricating PlanSwift availability."""
    is_win = sys.platform == "win32"
    bitness = 64 if sys.maxsize > 2**32 else 32
    found_progids: list[str] = []

    if is_win:
        try:
            import winreg

            for progid in ("PlanSwift.PlanSwift12", "PlanSwift9.PlanSwift", "PlanSwift.Application"):
                try:
                    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid):
                        found_progids.append(progid)
                except OSError:
                    continue
        except ImportError:
            pass

    if not is_win:
        return PlanSwiftEnvironmentInfo(
            os_name=platform.system(),
            is_windows=False,
            python_bitness=bitness,
            com_registered_progids=[],
            recommended_progid=None,
            supports_live_com=False,
            reason="PlanSwift COM automation requires a Windows desktop session; unavailable on non-Windows host.",
        )

    if not found_progids:
        return PlanSwiftEnvironmentInfo(
            os_name=platform.system(),
            is_windows=True,
            python_bitness=bitness,
            com_registered_progids=[],
            recommended_progid=None,
            supports_live_com=False,
            reason="No PlanSwift COM ProgID registered in HKCR (PlanSwift Desktop not installed on this host).",
        )

    rec = found_progids[0]
    if rec == "PlanSwift.PlanSwift12" and bitness != 64:
        return PlanSwiftEnvironmentInfo(
            os_name=platform.system(),
            is_windows=True,
            python_bitness=bitness,
            com_registered_progids=found_progids,
            recommended_progid=rec,
            supports_live_com=False,
            reason="PlanSwift 12 requires a 64-bit COM client process.",
        )

    return PlanSwiftEnvironmentInfo(
        os_name=platform.system(),
        is_windows=True,
        python_bitness=bitness,
        com_registered_progids=found_progids,
        recommended_progid=rec,
        supports_live_com=True,
        reason=f"Detected registered COM ProgID {rec}. Interactive signed-in PlanSwift session required for live calls.",
    )
