"use client";

import React, { useEffect, useState } from "react";
import { GeometryDataViewer } from "@/components/geometry-data-viewer/GeometryDataViewer";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { GeometryFeature, PaginatedResponse } from "@/types/api";

export default function GeometryPage() {
  const { selectedProjectId } = useProjectContext();
  const [features, setFeatures] = useState<GeometryFeature[]>([]);
  const [selected, setSelected] = useState<GeometryFeature | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedProjectId) params.set("project_version__project", selectedProjectId);
    if (search) params.set("search", search);
    apiRequest<PaginatedResponse<GeometryFeature>>(`/geometry/?${params.toString()}`)
      .then((res) => setFeatures(res.results || []))
      .catch(() => {});
  }, [selectedProjectId, search]);

  const inspectGeometry = async (id: string) => {
    const detail = await apiRequest<GeometryFeature>(`/geometry/${id}/`);
    setSelected(detail);
  };

  return (
    <AppShell title="Geometry Data Explorer (Structured Coordinates Only)">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search section GUID, parent object GUID, or page GUID..."
          className="w-full max-w-md rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
        />
        <span className="text-xs text-slate-500">
          Native DigitizerData coordinate sequences (no drawing rasterization)
        </span>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white lg:col-span-5">
          <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
            <thead className="bg-slate-50 font-semibold text-slate-600">
              <tr>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Points</th>
                <th className="px-3 py-2">Calibrated</th>
                <th className="px-3 py-2">Section GUID</th>
                <th className="px-3 py-2">Provenance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {features.map((f) => (
                <tr key={f.id} onClick={() => inspectGeometry(f.id)} className="cursor-pointer hover:bg-blue-50">
                  <td className="px-3 py-2 font-medium">{f.geometry_type}</td>
                  <td className="px-3 py-2 font-mono font-semibold">{f.point_count}</td>
                  <td className="px-3 py-2 font-mono text-xs text-emerald-700">
                    {f.is_calibrated
                      ? f.calibrated_area != null
                        ? `${f.calibrated_area.toFixed(1)} ${f.calibrated_unit || ""}`
                        : f.calibrated_length != null
                          ? `${f.calibrated_length.toFixed(1)} ${f.scale_unit || ""}`
                          : "Yes"
                      : "Raw px"}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-slate-600">{f.section_guid}</td>
                  <td className="px-3 py-2">
                    <ProvenanceBadge status={f.provenance} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="lg:col-span-7">
          {selected ? (
            <GeometryDataViewer feature={selected} />
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
              Select a geometry feature to inspect raw coordinate points, bounding boxes, and page references.
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
