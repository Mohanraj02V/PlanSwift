"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { PaginatedResponse, ValidationResult } from "@/types/api";

export default function ValidationPage() {
  const { selectedProjectId } = useProjectContext();
  const [reports, setReports] = useState<ValidationResult[]>([]);
  const [recs, setRecs] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    const q = selectedProjectId ? `?project_version__project=${selectedProjectId}` : "";
    apiRequest<PaginatedResponse<ValidationResult>>(`/validation/${q}`)
      .then((res) => setReports(res.results || []))
      .catch(() => {});
    apiRequest<PaginatedResponse<Record<string, unknown>>>(`/reconciliation/${q}`)
      .then((res) => setRecs(res.results || []))
      .catch(() => {});
  }, [selectedProjectId]);

  const latest = reports[0];

  return (
    <AppShell title="Validation & Source Reconciliation">
      {latest ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="text-xs text-slate-500">Verified Accuracy</div>
              <div className="mt-1 text-2xl font-bold text-emerald-700">{latest.overall_verified_accuracy_pct}%</div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="text-xs text-slate-500">Objects Extracted</div>
              <div className="mt-1 font-mono text-2xl font-bold">
                {latest.objects_extracted}/{latest.objects_discovered}
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="text-xs text-slate-500">Pages Matched to TIFF</div>
              <div className="mt-1 font-mono text-2xl font-bold">
                {latest.pages_matched_to_tiff}/{latest.pages_discovered}
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="text-xs text-slate-500">Unresolved Formulas</div>
              <div className="mt-1 font-mono text-2xl font-bold text-amber-700">{latest.unresolved_formulas}</div>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 font-semibold text-slate-600">
                <tr>
                  <th className="px-3 py-2">Validation Check</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Discovered / Extracted</th>
                  <th className="px-3 py-2">Accuracy</th>
                  <th className="px-3 py-2">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {latest.checks_json.map((chk) => (
                  <tr key={chk.check_name}>
                    <td className="px-3 py-2 font-semibold">{chk.check_name}</td>
                    <td className="px-3 py-2 font-mono">{chk.status}</td>
                    <td className="px-3 py-2 font-mono">
                      {chk.discovered_count} / {chk.extracted_count}
                    </td>
                    <td className="px-3 py-2 font-mono">{chk.accuracy_pct !== null ? `${chk.accuracy_pct}%` : "—"}</td>
                    <td className="px-3 py-2 text-slate-600">{chk.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {recs[0] && (
            <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs">
              <h2 className="mb-2 text-sm font-semibold">Latest COM-vs-Package Reconciliation</h2>
              <div className="font-mono">
                Mode: {String(recs[0].mode)} | COM Available: {String(recs[0].com_available)} | Matched Objects:{" "}
                {String(recs[0].matched_objects)} | Computed Values Applied: {String(recs[0].computed_values_applied)}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500">
          No validation reports found for the selected project.
        </div>
      )}
    </AppShell>
  );
}
