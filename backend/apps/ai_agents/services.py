"""Estimation QA, Quantity Audit, and Missing-Data Agents (strictly separated from extraction_engine)."""

from __future__ import annotations

import time
from typing import Any

from apps.ai_prompts.models import StructuredAIResponseContract
from apps.ai_providers.models import AIUsageRecord
from apps.ai_providers.services import DeterministicGroundedProvider, get_active_provider
from apps.projects.models import Project
from apps.retrieval.services import HybridRetrievalService

SYSTEM_PROMPT = (
    "You are an engineering construction estimator assistant. Answer ONLY using the provided "
    "native PlanSwift project records. Always return JSON matching {answer, source_objects, data_status, inference_used}. "
    "Never present derived or ai_inferred numbers as original PlanSwift values."
)


class EstimationQAAgent:
    def __init__(self, retrieval_service: HybridRetrievalService | None = None) -> None:
        self.retrieval = retrieval_service or HybridRetrievalService()

    def answer_question(
        self,
        project: Project,
        question: str,
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        context_bundle = self.retrieval.retrieve(project, question)
        provider = get_active_provider(provider_name, model_name)
        t0 = time.perf_counter()
        succeeded = True
        err_msg = ""

        try:
            raw_resp = provider.generate_structured(SYSTEM_PROMPT, question, context_bundle)
            validated = StructuredAIResponseContract.model_validate(raw_resp)
            usage = raw_resp.get("usage", {})
        except Exception as exc:
            # Safe fallback to offline deterministic grounded provider if external LLM fails
            succeeded = False
            err_msg = str(exc)
            fallback = DeterministicGroundedProvider()
            raw_resp = fallback.generate_structured(SYSTEM_PROMPT, question, context_bundle)
            validated = StructuredAIResponseContract.model_validate(raw_resp)
            usage = raw_resp.get("usage", {})

        latency_ms = int((time.perf_counter() - t0) * 1000)
        AIUsageRecord.objects.create(
            organization=project.organization,
            project=project,
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            estimated_cost_usd=usage.get("cost_usd", 0.0),
            latency_ms=latency_ms,
            succeeded=succeeded,
            error_message=err_msg,
        )

        result = validated.model_dump()
        result["provider_used"] = provider.provider_name if succeeded else "deterministic_fallback"
        result["retrieval_stats"] = {
            "matched_objects": len(context_bundle.get("objects", [])),
            "relationships": len(context_bundle.get("relationships", [])),
            "knowledge_snippets": len(context_bundle.get("knowledge_snippets", [])),
        }
        return result
