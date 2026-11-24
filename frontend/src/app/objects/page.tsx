"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ObjectInspector } from "@/components/object-inspector/ObjectInspector";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { FormulaRecord, GeometryFeature, MeasurementRecord, PaginatedResponse, ProjectObject } from "@/types/api";

export default function ObjectsPage() {
  const { selectedProjectId } = useProjectContext();
  const [search, setSearch] = useState("");
  const [nativeClass, setNativeClass] = useState("");
  const [onlyUnsupported, setOnlyUnsupported] = useState(false);
  const [items, setItems] = useState<ProjectObject[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<ProjectObject | null>(null);
  const [selMeas, setSelMeas] = useState<MeasurementRecord[]>([]);
  const [selFormulas, setSelFormulas] = useState<FormulaRecord[]>([]);
  const [selGeoms, setSelGeoms] = useState<GeometryFeature[]>([]);
  const [selRels, setSelRels] = useState<Array<{ relationship_type: string; source_guid: string; target_guid: string }>>([]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedProjectId) params.set("project_version__project", selectedProjectId);
    if (search) params.set("search", search);
    if (nativeClass) params.set("native_class", nativeClass);
    const endpoint = onlyUnsupported ? `/objects/unsupported/?${params.toString()}` : `/objects/?${params.toString()}`;
    apiRequest<PaginatedResponse<ProjectObject>>(endpoint)
      .then((res) => {
        setItems(res.results || []);
        setTotal(res.count || 0);
      })
      .catch(() => {});
  }, [selectedProjectId, search, nativeClass, onlyUnsupported]);

  const inspectObject = async (obj: ProjectObject) => {
    const geomFilter = obj.is_measurement_section
      ? `section_guid=${encodeURIComponent(obj.native_guid)}`
      : `parent_object_guid=${encodeURIComponent(obj.native_guid)}`;
    const [detail, measRes, formRes, geomRes, relRes] = await Promise.all([
      apiRequest<ProjectObject>(`/objects/${obj.id}/`),
      apiRequest<PaginatedResponse<MeasurementRecord>>(`/measurements/?search=${encodeURIComponent(obj.native_guid)}`),
      apiRequest<PaginatedResponse<FormulaRecord>>(`/formulas/?search=${encodeURIComponent(obj.native_guid)}`),
      apiRequest<PaginatedResponse<GeometryFeature>>(`/geometry/?${geomFilter}`),
      apiRequest<PaginatedResponse<{ relationship_type: string; source_guid: string; target_guid: string }>>(
        `/hierarchy/relationships/?source_guid=${encodeURIComponent(obj.native_guid)}`
      ),
    ]);
    setSelected(detail);
    setSelMeas((measRes.results || []).filter((m) => m.object_guid === obj.native_guid));
    setSelFormulas((formRes.results || []).filter((f) => f.object_guid === obj.native_guid));
    setSelGeoms(geomRes.results || []);
    setSelRels(relRes.results || []);
  };

  return (
    <AppShell title="Objects Explorer">
      <div className="mb-4 flex flex-wrap items-center gap-3">
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
          <option value="Area">Area</option>
          <option value="Linear">Linear</option>
          <option value="Count">Count</option>
          <option value="Segment">Segment</option>
          <option value="Count Section">Count Section</option>
          <option value="Area Section">Area Section</option>
          <option value="Linear Section">Linear Section</option>
          <option value="Page">Page</option>
          <option value="Folder">Folder</option>
          <option value="Item">Item</option>
        </select>
        <label className="flex items-center gap-1.5 text-xs text-slate-700">
          <input
            type="checkbox"
            checked={onlyUnsupported}
            onChange={(e) => setOnlyUnsupported(e.target.checked)}
          />
          Unsupported / Unknown classes only
        </label>
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
                <tr key={o.id} onClick={() => inspectObject(o)} className="cursor-pointer hover:bg-blue-50">
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
            <ObjectInspector
              object={selected}
              measurements={selMeas}
              formulas={selFormulas}
              geometries={selGeoms}
              relationships={selRels}
            />
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
              Click any row to inspect Overview, Native Properties, Geometry, Measurements, Formulas, Calculations, Relationships, Raw Data, Provenance &amp; Validation.
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
