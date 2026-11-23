"use client";

import React, { useState } from "react";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import type { ObjectProperty } from "@/types/api";

export function PropertyViewer({ properties }: { properties: ObjectProperty[] }) {
  const [filter, setFilter] = useState("");
  const filtered = properties.filter((p) => {
    const q = filter.toLowerCase();
    return (
      !q ||
      p.name.toLowerCase().includes(q) ||
      p.group.toLowerCase().includes(q) ||
      p.raw_value.toLowerCase().includes(q) ||
      p.native_property_guid.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <input
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter properties by name, GUID, group, or value..."
          className="w-full max-w-md rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        />
        <span className="text-xs text-slate-500">
          Showing {filtered.length} of {properties.length} native properties
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
          <thead className="bg-slate-50 font-semibold text-slate-600">
            <tr>
              <th className="px-3 py-2">Property Name</th>
              <th className="px-3 py-2">Class</th>
              <th className="px-3 py-2">Group</th>
              <th className="px-3 py-2">Raw Value</th>
              <th className="px-3 py-2">Normalized</th>
              <th className="px-3 py-2">Units</th>
              <th className="px-3 py-2">Provenance</th>
              <th className="px-3 py-2">Property GUID</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((p) => (
              <tr key={p.id} className="hover:bg-slate-50">
                <td className="px-3 py-2 font-medium text-slate-900">
                  {p.name || <span className="italic text-slate-400">(empty Name attribute)</span>}
                </td>
                <td className="px-3 py-2 font-mono text-slate-600">{p.property_class}</td>
                <td className="px-3 py-2 text-slate-600">{p.group || "—"}</td>
                <td className="max-w-xs break-all px-3 py-2 font-mono text-slate-800">{p.raw_value || "—"}</td>
                <td className="px-3 py-2 font-mono text-slate-600">
                  {p.normalized_value_json !== null && p.normalized_value_json !== undefined
                    ? String(p.normalized_value_json)
                    : "—"}
                </td>
                <td className="px-3 py-2 font-mono text-slate-600">{p.normalized_unit || p.units || "—"}</td>
                <td className="px-3 py-2">
                  <ProvenanceBadge status={p.provenance} />
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-slate-500">{p.native_property_guid}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
