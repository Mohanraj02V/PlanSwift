"""Model provider adapter interface with retries, timeouts, fallback, and zero hardwiring."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol

import httpx
from django.conf import settings


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_structured(self, system_prompt: str, user_prompt: str, context_bundle: dict[str, Any]) -> dict[str, Any]:
        ...


class DeterministicGroundedProvider:
    """Offline, zero-hallucination structured provider answering strictly from retrieved SQL/Graph/RAG facts."""

    provider_name = "deterministic"
    model_name = "deterministic-v1"

    def generate_structured(self, system_prompt: str, user_prompt: str, context_bundle: dict[str, Any]) -> dict[str, Any]:
        project = context_bundle.get("project", {})
        matched_objects = context_bundle.get("objects", [])
        unresolved_formulas = context_bundle.get("unresolved_formulas", [])
        kb_snippets = context_bundle.get("knowledge_snippets", [])

        project_guid = project.get("native_guid", "")
        source_objects: list[dict[str, Any]] = []
        lines: list[str] = []

        if matched_objects:
            lines.append(f"Retrieved {len(matched_objects)} matching native object(s) from project '{project.get('name', '')}':")
            for obj in matched_objects[:15]:
                meas_summary = []
                for m in obj.get("measurements", []):
                    if m.get("property_name") == "Qty":
                        raw_f = m.get("raw_formula") or m.get("native_stored_value") or ""
                        ps_q = m.get("planswift_computed_quantity")
                        drv_q = m.get("derived_quantity")
                        unit = m.get("unit") or ""
                        if ps_q is not None:
                            meas_summary.append(f"PlanSwift Qty={ps_q} {unit} (status=computed_by_planswift, formula={raw_f})")
                        elif drv_q is not None:
                            meas_summary.append(f"derived_qty={drv_q} {unit} from {obj.get('section_count', 0)} DigitizerData sections (raw formula={raw_f}, status=derived)")
                        else:
                            meas_summary.append(f"raw_formula={raw_f} (status=unresolved)")
                lines.append(
                    f"- [{obj.get('native_class')}] {obj.get('name')} ({obj.get('native_guid')}): "
                    + ("; ".join(meas_summary) if meas_summary else "no quantity measurement")
                )
                source_objects.append(
                    {
                        "project_guid": project_guid,
                        "object_guid": obj.get("native_guid", ""),
                        "native_class": obj.get("native_class", ""),
                        "source_property": "Qty" if meas_summary else "Name",
                        "provenance": obj.get("quantity_provenance", obj.get("provenance", "original")),
                    }
                )
        else:
            lines.append(
                f"No exact native objects matched the query in project '{project.get('name', '')}' "
                f"(total objects={project.get('total_objects', 0)}, total pages={project.get('total_pages', 0)})."
            )

        if unresolved_formulas:
            lines.append(
                f"Note: {len(unresolved_formulas)} formula expression(s) (e.g. PascalScript or system variables) remain marked 'unresolved' without live PlanSwift COM evaluation."
            )

        if kb_snippets:
            lines.append(f"Supporting knowledge context ({len(kb_snippets)} snippet(s)): {kb_snippets[0].get('title', '')}.")

        has_derived = any(s.get("provenance") == "derived" for s in source_objects)
        data_status = "derived" if has_derived else ("original" if source_objects else "unresolved")

        return {
            "answer": "\n".join(lines),
            "source_objects": source_objects,
            "data_status": data_status,
            "inference_used": False,
            "usage": {"prompt_tokens": len(user_prompt.split()), "completion_tokens": len("\n".join(lines).split()), "cost_usd": 0.0},
        }


class OpenAICompatibleProvider:
    """Configurable OpenAI-compatible HTTP provider with timeout, retries, and fallback."""

    def __init__(self, provider_name: str, model_name: str, api_key: str, base_url: str, timeout: int = 30, retries: int = 2):
        self.provider_name = provider_name
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def generate_structured(self, system_prompt: str, user_prompt: str, context_bundle: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Question: {user_prompt}\n\nRetrieved Ground-Truth JSON:\n{json.dumps(context_bundle)}"},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    usage = data.get("usage", {})
                    parsed["usage"] = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "cost_usd": 0.0,
                    }
                    return parsed
            except Exception as exc:
                last_exc = exc
                time.sleep(0.25 * (attempt + 1))
        raise RuntimeError(f"AI provider {self.provider_name} failed: {last_exc}")


def get_active_provider(provider_name: str | None = None, model_name: str | None = None):
    pname = (provider_name or settings.AI_PROVIDER or "deterministic").lower()
    mname = model_name or settings.AI_MODEL or "deterministic-v1"
    api_key = settings.AI_API_KEY or os.environ.get("AI_API_KEY", "")
    if pname in ("openai", "openai_compatible") and api_key:
        return OpenAICompatibleProvider(
            provider_name=pname,
            model_name=mname,
            api_key=api_key,
            base_url=os.environ.get("AI_API_BASE_URL", "https://api.openai.com/v1"),
            timeout=settings.AI_TIMEOUT_SECONDS,
            retries=settings.AI_MAX_RETRIES,
        )
    return DeterministicGroundedProvider()
