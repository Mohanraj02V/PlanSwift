"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { EstimationSession, PaginatedResponse } from "@/types/api";

export default function EstimationPage() {
  const { selectedProjectId } = useProjectContext();
  const [sessions, setSessions] = useState<EstimationSession[]>([]);
  const [error, setError] = useState("");

  const loadSessions = () => {
    const q = selectedProjectId ? `?project=${selectedProjectId}` : "";
    apiRequest<PaginatedResponse<EstimationSession>>(`/estimation/sessions/${q}`)
      .then((res) => setSessions(res.results || []))
      .catch(() => {});
  };

  useEffect(() => {
    loadSessions();
  }, [selectedProjectId]);

  const handleGenerate = async () => {
    if (!selectedProjectId) return;
    setError("");
    try {
      await apiRequest("/estimation/sessions/", {
        method: "POST",
        body: JSON.stringify({ project: selectedProjectId }),
      });
      loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate estimation.");
    }
  };

  const handleApprove = async (id: string) => {
    await apiRequest(`/estimation/sessions/${id}/approve/`, { method: "POST" });
    loadSessions();
  };

  const active = sessions[0];

  return (
    <AppShell title="Estimation Rollups & Approvals">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={handleGenerate}
          className="rounded bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700"
        >
          Generate Deterministic Takeoff Rollup
        </button>
        {active && active.status !== "approved" && (
          <button
            type="button"
            onClick={() => handleApprove(active.id)}
            className="rounded border border-emerald-600 px-3 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-50"
          >
            Approve Estimation ({active.name})
          </button>
        )}
      </div>

      {error && <div className="mb-4 rounded bg-rose-50 p-3 text-xs text-rose-700">{error}</div>}

      {active ? (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
            <thead className="bg-slate-50 font-semibold text-slate-600">
              <tr>
                <th className="px-3 py-2">Takeoff Object</th>
                <th className="px-3 py-2">Class</th>
                <th className="px-3 py-2">Sections</th>
                <th className="px-3 py-2">Quantity</th>
                <th className="px-3 py-2">Unit</th>
                <th className="px-3 py-2">Raw Formula</th>
                <th className="px-3 py-2">Provenance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {active.results.map((r) => (
                <tr key={r.id}>
                  <td className="px-3 py-2 font-medium">{r.object_name}</td>
                  <td className="px-3 py-2 font-mono">{r.native_class}</td>
                  <td className="px-3 py-2 font-mono">{r.section_count}</td>
                  <td className="px-3 py-2 font-mono font-bold">{r.quantity}</td>
                  <td className="px-3 py-2">{r.unit}</td>
                  <td className="px-3 py-2 font-mono">{r.formula_raw || "—"}</td>
                  <td className="px-3 py-2">
                    <ProvenanceBadge status={r.source_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500">
          Click Generate Deterministic Takeoff Rollup to compute SQL-verified quantities.
        </div>
      )}
    </AppShell>
  );
}
