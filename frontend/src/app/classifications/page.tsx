"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { PaginatedResponse } from "@/types/api";

interface ClassificationRow {
  id: string;
  object_guid: string;
  object_name: string;
  family: string;
  category: string;
  division: string;
  cost_code: string;
  provenance: string;
}

export default function ClassificationsPage() {
  const { selectedProjectId } = useProjectContext();
  const [rows, setRows] = useState<ClassificationRow[]>([]);

  useEffect(() => {
    const q = selectedProjectId ? `?project_version__project=${selectedProjectId}` : "";
    apiRequest<PaginatedResponse<ClassificationRow>>(`/classifications/${q}`)
      .then((res) => setRows(res.results || []))
      .catch(() => {});
  }, [selectedProjectId]);

  return (
    <AppShell title="Work Breakdown & Classifications">
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
          <thead className="bg-slate-50 font-semibold text-slate-600">
            <tr>
              <th className="px-3 py-2">Object</th>
              <th className="px-3 py-2">Family</th>
              <th className="px-3 py-2">Division</th>
              <th className="px-3 py-2">Cost Code</th>
              <th className="px-3 py-2">Provenance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="px-3 py-2 font-medium">{r.object_name}</td>
                <td className="px-3 py-2">{r.family}</td>
                <td className="px-3 py-2">{r.division || "—"}</td>
                <td className="px-3 py-2">{r.cost_code || "—"}</td>
                <td className="px-3 py-2">
                  <ProvenanceBadge status={r.provenance} />
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                  No explicit native WBS Division/Cost Code values populated in the selected project.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
