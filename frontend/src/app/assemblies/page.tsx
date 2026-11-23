"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { PaginatedResponse } from "@/types/api";

interface AssemblyRow {
  id: string;
  native_guid: string;
  name: string;
  native_class: string;
  assembly_type: string;
  provenance: string;
  components: Array<{ id: string; native_guid: string; name: string; native_class: string; quantity_raw: string; unit: string }>;
}

export default function AssembliesPage() {
  const { selectedProjectId } = useProjectContext();
  const [assemblies, setAssemblies] = useState<AssemblyRow[]>([]);

  useEffect(() => {
    const q = selectedProjectId ? `?project_version__project=${selectedProjectId}` : "";
    apiRequest<PaginatedResponse<AssemblyRow>>(`/assemblies/${q}`)
      .then((res) => setAssemblies(res.results || []))
      .catch(() => {});
  }, [selectedProjectId]);

  return (
    <AppShell title="Native Assemblies & Components">
      {assemblies.length > 0 ? (
        <div className="space-y-4">
          {assemblies.map((a) => (
            <div key={a.id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-slate-900">{a.name}</h2>
                  <p className="font-mono text-xs text-slate-500">{a.native_guid}</p>
                </div>
                <ProvenanceBadge status={a.provenance} />
              </div>
              <div className="mt-3 space-y-1 text-xs">
                {a.components.map((c) => (
                  <div key={c.id} className="flex justify-between rounded bg-slate-50 px-3 py-1.5">
                    <span>{c.name}</span>
                    <span className="font-mono">
                      {c.quantity_raw} {c.unit}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600">
          No native Assembly items exist in the currently selected project (native structure preserved truthfully).
        </div>
      )}
    </AppShell>
  );
}
