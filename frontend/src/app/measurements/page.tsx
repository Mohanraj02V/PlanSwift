"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { MeasurementRecord, PaginatedResponse } from "@/types/api";

export default function MeasurementsPage() {
  const { selectedProjectId } = useProjectContext();
  const [items, setItems] = useState<MeasurementRecord[]>([]);
  const [search, setSearch] = useState("");
  const [propFilter, setPropFilter] = useState("Qty");

  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedProjectId) params.set("project_version__project", selectedProjectId);
    if (propFilter) params.set("property_name", propFilter);
    if (search) params.set("search", search);
    apiRequest<PaginatedResponse<MeasurementRecord>>(`/measurements/?${params.toString()}`)
      .then((res) => setItems(res.results || []))
      .catch(() => {});
  }, [selectedProjectId, propFilter, search]);

  return (
    <AppShell title="Measurement Explorer">
      <div className="mb-4 flex flex-wrap gap-3">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search object name or formula..."
          className="w-full max-w-sm rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
        />
        <select
          value={propFilter}
          onChange={(e) => setPropFilter(e.target.value)}
          className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
        >
          <option value="Qty">Qty (Primary Takeoff)</option>
          <option value="DigitizerData">Section DigitizerData</option>
          <option value="">All Measurement Properties</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
          <thead className="bg-slate-50 font-semibold text-slate-600">
            <tr>
              <th className="px-3 py-2">Object</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Property</th>
              <th className="px-3 py-2">Raw Formula</th>
              <th className="px-3 py-2">Reconstructed (Geom)</th>
              <th className="px-3 py-2">Calculated (Formula)</th>
              <th className="px-3 py-2">Unit</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((m) => (
              <tr key={m.id} className="hover:bg-slate-50">
                <td className="px-3 py-2 font-medium">
                  <div>{m.object_name}</div>
                  <div className="font-mono text-[10px] text-slate-400">{m.object_guid}</div>
                </td>
                <td className="px-3 py-2 font-mono">{m.measurement_type}</td>
                <td className="px-3 py-2">{m.property_name}</td>
                <td className="px-3 py-2 font-mono text-slate-700">{m.raw_formula || m.native_stored_value || "—"}</td>
                <td className="px-3 py-2 font-mono">{m.reconstructed_quantity ?? "—"}</td>
                <td className="px-3 py-2 font-mono font-semibold text-teal-800">{m.calculated_quantity ?? m.derived_quantity ?? "—"}</td>
                <td className="px-3 py-2">{m.unit || m.normalized_unit || "—"}</td>
                <td className="px-3 py-2">
                  <ProvenanceBadge status={m.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}
