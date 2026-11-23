"use client";

import React, { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";

export default function OrganizationsPage() {
  const { organizations, refreshContext } = useProjectContext();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState("");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await apiRequest("/organizations/", { method: "POST", body: JSON.stringify({ name, slug }) });
      setName("");
      setSlug("");
      await refreshContext();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create organization.");
    }
  };

  return (
    <AppShell title="Organizations & Tenant Access">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <form onSubmit={handleCreate} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-900">Create Organization</h2>
          {error && <div className="rounded bg-rose-50 p-2 text-xs text-rose-700">{error}</div>}
          <input
            type="text"
            required
            placeholder="Organization Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
          <input
            type="text"
            required
            placeholder="slug-identifier"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
          <button type="submit" className="w-full rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white">
            Create Tenant
          </button>
        </form>

        <div className="space-y-3 lg:col-span-2">
          {organizations.map((org) => (
            <div key={org.id} className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-4">
              <div>
                <div className="font-semibold text-slate-900">{org.name}</div>
                <div className="font-mono text-xs text-slate-500">
                  slug: {org.slug} | id: {org.id}
                </div>
              </div>
              <span className="rounded-full bg-blue-50 px-3 py-1 font-mono text-xs font-semibold text-blue-700">
                role: {org.my_role || "member"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
