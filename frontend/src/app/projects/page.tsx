"use client";

import React, { useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";

export default function ProjectsPage() {
  const { organizations, projects, refreshContext } = useProjectContext();
  const [name, setName] = useState("");
  const [orgId, setOrgId] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const activeOrg = orgId || organizations[0]?.id || "";

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await apiRequest("/projects/", {
        method: "POST",
        body: JSON.stringify({ organization: activeOrg, name, description }),
      });
      setName("");
      setDescription("");
      await refreshContext();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project.");
    }
  };

  return (
    <AppShell title="Projects">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <form onSubmit={handleCreate} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-900">New Project</h2>
          {error && <div className="rounded bg-rose-50 p-2 text-xs text-rose-700">{error}</div>}
          <select
            value={activeOrg}
            onChange={(e) => setOrgId(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
          >
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
          <input
            type="text"
            required
            placeholder="Project Name (e.g. project 4)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
          <textarea
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
          <button type="submit" className="w-full rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white">
            Create Project
          </button>
        </form>

        <div className="space-y-3 lg:col-span-2">
          {projects.map((p) => (
            <div key={p.id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <Link href={`/projects/${p.id}`} className="text-base font-semibold text-blue-700 hover:underline">
                    {p.name}
                  </Link>
                  <p className="text-xs text-slate-600">{p.description || "No description"}</p>
                  <p className="mt-1 font-mono text-[11px] text-slate-500">
                    Native GUID: {p.native_guid || "(awaiting extraction)"} | Units: {p.measurement_system || "—"}
                  </p>
                </div>
                <div className="text-right text-xs">
                  <div className="font-mono font-semibold text-slate-800">{p.object_count} objects</div>
                  <div className="font-mono text-slate-500">{p.page_count} pages</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
