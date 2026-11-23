"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { apiRequest } from "@/services/api-client/client";
import type { PaginatedResponse } from "@/types/api";

interface AuditRow {
  id: string;
  actor_email: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditRow[]>([]);

  useEffect(() => {
    apiRequest<PaginatedResponse<AuditRow>>("/audit/")
      .then((res) => setLogs(res.results || []))
      .catch(() => {});
  }, []);

  return (
    <AppShell title="Immutable Audit Trail">
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
          <thead className="bg-slate-50 font-semibold text-slate-600">
            <tr>
              <th className="px-3 py-2">Timestamp</th>
              <th className="px-3 py-2">Actor</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Resource</th>
              <th className="px-3 py-2">Metadata</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {logs.map((l) => (
              <tr key={l.id}>
                <td className="px-3 py-2 font-mono text-[11px]">{l.created_at}</td>
                <td className="px-3 py-2">{l.actor_email || "system"}</td>
                <td className="px-3 py-2 font-mono font-semibold text-blue-700">{l.action}</td>
                <td className="px-3 py-2 font-mono text-[11px]">
                  {l.resource_type} {l.resource_id}
                </td>
                <td className="max-w-md truncate px-3 py-2 font-mono text-[11px]">{JSON.stringify(l.metadata)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
