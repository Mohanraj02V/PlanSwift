"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { apiRequest } from "@/services/api-client/client";
import type { AuditLogEntry, PaginatedResponse } from "@/types/api";

const CATEGORIES = [
  { id: "", label: "All Logs" },
  { id: "uploads", label: "File Uploads" },
  { id: "auth", label: "Auth & Logins" },
  { id: "users", label: "User Admin" },
  { id: "estimation", label: "Estimation & Exports" },
  { id: "extraction", label: "Extraction Runs" },
];

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const loadLogs = async (cat: string, q: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (cat) params.set("category", cat);
      if (q.trim()) params.set("search", q.trim());
      const query = params.toString() ? `?${params.toString()}` : "";
      const res = await apiRequest<PaginatedResponse<AuditLogEntry>>(`/audit/${query}`);
      setLogs(res.results || []);
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs(category, search);
  }, [category]);

  return (
    <AppShell title="Immutable Activity & File Upload Audit Trail">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((c) => (
            <button
              key={c.id || "all"}
              type="button"
              onClick={() => setCategory(c.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                category === c.id ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadLogs(category, search)}
            placeholder="Filter by email, action, or resource..."
            className="w-64 rounded border border-slate-300 px-3 py-1.5 text-xs"
          />
          <button
            type="button"
            onClick={() => loadLogs(category, search)}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            Search
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
          <thead className="bg-slate-50 font-semibold text-slate-600">
            <tr>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Time (UTC)</th>
              <th className="px-3 py-2">User</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">IP</th>
              <th className="px-3 py-2">File / Resource Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {logs.map((l) => {
              const meta = l.metadata || {};
              const fileName = meta.file_name || meta.bundle_name;
              const fileSize = typeof meta.file_size_bytes === "number" ? meta.file_size_bytes : null;
              return (
                <tr key={l.id} className="hover:bg-slate-50">
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] font-medium text-slate-800">
                    {l.date || l.created_at.slice(0, 10)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-slate-600">
                    {l.time || l.created_at.slice(11, 19)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-medium text-slate-900">{l.actor_name || l.actor_email || "system"}</div>
                    {l.actor_email && <div className="font-mono text-[10px] text-slate-500">{l.actor_email}</div>}
                  </td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-blue-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-blue-700">
                      {l.action}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-slate-500">
                    {l.ip_address || "—"}
                  </td>
                  <td className="px-3 py-2 text-[11px]">
                    {fileName ? (
                      <div className="space-y-0.5">
                        <div className="font-semibold text-slate-900">
                          File: <span className="font-mono">{String(fileName)}</span>
                          {fileSize !== null && (
                            <span className="ml-2 text-slate-500">({(fileSize / 1024).toFixed(1)} KB)</span>
                          )}
                        </div>
                        {Boolean(meta.source_format) && (
                          <span className="inline-block rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-700">
                            {String(meta.source_format)}
                          </span>
                        )}
                        {Boolean(meta.project_name) && (
                          <span className="ml-2 text-slate-600">Project: {String(meta.project_name)}</span>
                        )}
                      </div>
                    ) : (
                      <div className="max-w-md truncate font-mono text-slate-600">
                        {l.resource_type} {l.resource_id} {Object.keys(meta).length ? JSON.stringify(meta) : ""}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
            {!loading && logs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                  No audit events match the selected filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
