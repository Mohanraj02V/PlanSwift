"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ObjectInspector } from "@/components/object-inspector/ObjectInspector";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { PaginatedResponse, ProjectObject } from "@/types/api";

export default function ObjectsPage() {
  const { selectedProjectId } = useProjectContext();
  const [search, setSearch] = useState("");
  const [nativeClass, setNativeClass] = useState("");
  const [items, setItems] = useState<ProjectObject[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<ProjectObject | null>(null);

  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedProjectId) params.set("project_version__project", selectedProjectId);
    if (search) params.set("search", search);
    if (nativeClass) params.set("native_class", nativeClass);
    apiRequest<PaginatedResponse<ProjectObject>>(`/objects/?${params.toString()}`)
      .then((res) => {
        setItems(res.results || []);
        setTotal(res.count || 0);
      })
      .catch(() => {});
  }, [selectedProjectId, search, nativeClass]);

  const inspectObject = async (id: string) => {
    const detail = await apiRequest<ProjectObject>(`/objects/${id}/`);
    setSelected(detail);
  };

  return (
    <AppShell title="Objects Explorer">
      <div className="mb-4 flex flex-wrap gap-3">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search object name or GUID..."
          className="w-full max-w-sm rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
        />
        <select
          value={nativeClass}
          onChange={(e) => setNativeClass(e.target.value)}
          className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="">All Native Classes</option>
          <option value="Count">Count</option>
          <option value="Count Section">Count Section</option>
          <option value="Segment">Segment</option>
          <option value="Page">Page</option>
          <option value="Folder">Folder</option>
          <option value="Item">Item</option>
        </select>
        <span className="self-center text-xs text-slate-500">{total.toLocaleString()} matching objects</span>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white lg:col-span-5">
          <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
            <thead className="bg-slate-50 font-semibold text-slate-600">
              <tr>
                <th className="px-3 py-2">Class</th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Provenance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((o) => (
                <tr key={o.id} onClick={() => inspectObject(o.id)} className="cursor-pointer hover:bg-blue-50">
                  <td className="px-3 py-2 font-mono text-blue-700">{o.native_class}</td>
                  <td className="px-3 py-2 font-medium">{o.name || o.native_guid}</td>
                  <td className="px-3 py-2">
                    <ProvenanceBadge status={o.provenance} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="lg:col-span-7">
          {selected ? (
            <ObjectInspector object={selected} />
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
              Click any row to inspect full native attributes and properties.
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
