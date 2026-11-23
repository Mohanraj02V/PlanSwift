"use client";

import React, { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { AIQueryResponse } from "@/types/api";

export default function AIAssistantPage() {
  const { selectedProjectId, selectedProject } = useProjectContext();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<Array<{ q: string; res: AIQueryResponse }>>([]);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProjectId || !question.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await apiRequest<AIQueryResponse>("/ai/query/", {
        method: "POST",
        body: JSON.stringify({ project_id: selectedProjectId, question }),
      });
      setHistory((prev) => [...prev, { q: question, res }]);
      setQuestion("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI query failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell title="Provenance-Aware AI Estimation Assistant">
      <div className="space-y-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-600">
          Retrieves exact SQL objects, measurements, formulas, and geometry first before consulting knowledge text.
          Every answer cites original PlanSwift object GUIDs and labels derived vs original vs unresolved status.
        </div>

        <form onSubmit={handleAsk} className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={
              selectedProject
                ? `Ask about ${selectedProject.name} (e.g. What is the quantity of Duct 350x200mm?)`
                : "Select an extracted project first..."
            }
            className="flex-1 rounded border border-slate-300 bg-white px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={loading || !selectedProjectId}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {loading ? "Querying..." : "Ask AI"}
          </button>
        </form>

        {error && <div className="rounded bg-rose-50 p-3 text-xs text-rose-700">{error}</div>}

        <div className="space-y-4">
          {history.map((item, idx) => (
            <div key={idx} className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
              <div className="text-xs font-semibold text-slate-500">Question: {item.q}</div>
              <pre className="whitespace-pre-wrap font-sans text-sm text-slate-900">{item.res.answer}</pre>
              <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-2 text-xs">
                <ProvenanceBadge status={item.res.data_status} />
                <span className="rounded bg-slate-100 px-2 py-0.5 font-mono">
                  inference_used: {String(item.res.inference_used)}
                </span>
                <span className="rounded bg-slate-100 px-2 py-0.5 font-mono">
                  provider: {item.res.provider_used}
                </span>
              </div>
              {item.res.source_objects.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[11px] font-semibold uppercase text-slate-500">Cited Source Objects</div>
                  <div className="flex flex-wrap gap-1.5">
                    {item.res.source_objects.map((src, sidx) => (
                      <span
                        key={sidx}
                        className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px]"
                      >
                        [{src.native_class}] {src.object_guid} ({src.source_property}: {src.provenance})
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
