"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest, downloadExportFile } from "@/services/api-client/client";
import type {
  BIMElementRecord,
  CADBlockRecord,
  CADDocumentRecord,
  CADEntityRecord,
  CADLayerRecord,
  PaginatedResponse,
} from "@/types/api";

type DxfTab = "entities" | "layers" | "blocks" | "dimensions" | "unsupported";
type IfcTab = "elements" | "psets" | "qsets" | "geometry" | "unsupported";

export default function CadBimExplorerPage() {
  const { selectedProjectId } = useProjectContext();
  const [docs, setDocs] = useState<CADDocumentRecord[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [doc, setDoc] = useState<CADDocumentRecord | null>(null);
  const [layers, setLayers] = useState<CADLayerRecord[]>([]);
  const [blocks, setBlocks] = useState<CADBlockRecord[]>([]);
  const [entities, setEntities] = useState<CADEntityRecord[]>([]);
  const [elements, setElements] = useState<BIMElementRecord[]>([]);
  const [selectedEl, setSelectedEl] = useState<BIMElementRecord | null>(null);
  const [dxfTab, setDxfTab] = useState<DxfTab>("entities");
  const [ifcTab, setIfcTab] = useState<IfcTab>("elements");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const loadDocumentChildren = async (activeDoc: CADDocumentRecord | null) => {
    setDoc(activeDoc);
    if (!activeDoc) {
      setLayers([]);
      setBlocks([]);
      setEntities([]);
      setElements([]);
      setSelectedEl(null);
      return;
    }
    const docQ = `cad_document=${activeDoc.id}`;
    if (activeDoc.source_format.startsWith("dxf")) {
      const [lyrRes, blkRes, entRes] = await Promise.all([
        apiRequest<PaginatedResponse<CADLayerRecord>>(`/cad-bim/layers/?${docQ}`),
        apiRequest<PaginatedResponse<CADBlockRecord>>(`/cad-bim/blocks/?${docQ}`),
        apiRequest<PaginatedResponse<CADEntityRecord>>(`/cad-bim/entities/?${docQ}`),
      ]);
      setLayers(lyrRes.results || []);
      setBlocks(blkRes.results || []);
      setEntities(entRes.results || []);
      setElements([]);
      setSelectedEl(null);
    } else {
      const elRes = await apiRequest<PaginatedResponse<BIMElementRecord>>(`/cad-bim/elements/?${docQ}`);
      const list = elRes.results || [];
      setElements(list);
      setSelectedEl(list[0] || null);
      setLayers([]);
      setBlocks([]);
      setEntities([]);
    }
  };

  useEffect(() => {
    if (!selectedProjectId) {
      setDocs([]);
      setSelectedDocId("");
      setDoc(null);
      return;
    }
    setLoading(true);
    apiRequest<PaginatedResponse<CADDocumentRecord>>(`/cad-bim/documents/?project_version__project=${selectedProjectId}`)
      .then(async (res) => {
        const list = res.results || [];
        setDocs(list);
        const activeDoc = list[0] || null;
        setSelectedDocId(activeDoc?.id || "");
        await loadDocumentChildren(activeDoc);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedProjectId]);

  const handleSelectDoc = async (docId: string) => {
    setSelectedDocId(docId);
    const chosen = docs.find((d) => d.id === docId) || null;
    setLoading(true);
    try {
      await loadDocumentChildren(chosen);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (fmt: string) => {
    if (!selectedProjectId) return;
    const blob = await downloadExportFile(selectedProjectId, fmt);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `cad_bim_export_${selectedProjectId}.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const qLower = search.trim().toLowerCase();
  const filteredEntities = entities.filter(
    (e) =>
      !qLower ||
      e.handle.toLowerCase().includes(qLower) ||
      e.entity_type.toLowerCase().includes(qLower) ||
      e.layer_name.toLowerCase().includes(qLower)
  );
  const filteredElements = elements.filter(
    (e) =>
      !qLower ||
      e.global_id.toLowerCase().includes(qLower) ||
      e.ifc_class.toLowerCase().includes(qLower) ||
      e.name.toLowerCase().includes(qLower) ||
      e.storey_name.toLowerCase().includes(qLower)
  );

  return (
    <AppShell title="CAD (DXF) & BIM (IFC) Explorer">
      {loading && <p className="text-xs text-slate-500">Loading CAD/BIM document metadata...</p>}

      {!loading && !doc && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-600">
          The active project has no DXF or IFC document attached yet. Upload a <code>.dxf</code> or <code>.ifc</code> file on{" "}
          <span className="font-semibold">Source &amp; Extraction</span>, or switch to a DXF/IFC project in the header selector.
        </div>
      )}

      {doc && (
        <div className="space-y-5">
          {docs.length > 1 && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-200 bg-blue-50/70 px-4 py-2.5 text-xs">
              <span className="font-semibold text-blue-900">
                Extracted CAD / BIM Files in Project ({docs.length}):
              </span>
              <select
                value={selectedDocId}
                onChange={(e) => handleSelectDoc(e.target.value)}
                className="min-w-[260px] rounded border border-blue-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-800"
              >
                {docs.map((d) => (
                  <option key={d.id} value={d.id}>
                    v{d.version_number} — {d.source_name || d.project_name} ({d.source_format.toUpperCase()},{" "}
                    {d.source_format.startsWith("dxf") ? `${d.entity_count} entities` : `${d.ifc_element_count} elements`})
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4">
            <div className="space-y-1 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-slate-900">{doc.source_name || doc.project_name}</span>
                <span className="rounded bg-indigo-50 px-2 py-0.5 font-mono font-semibold text-indigo-700">
                  {doc.source_format.toUpperCase()}
                </span>
                <ProvenanceBadge status="native" />
              </div>
              <div className="font-mono text-slate-600">
                Library: {doc.library_name} {doc.library_version} | Version/Schema: {doc.file_version || doc.schema_name} | Units:{" "}
                {doc.source_units || "unspecified"}
              </div>
              <div className="flex flex-wrap gap-4 text-slate-600">
                {doc.source_format.startsWith("dxf") ? (
                  <>
                    <span>Entities: <b>{doc.entity_count}</b></span>
                    <span>Layers: <b>{doc.layer_count}</b></span>
                    <span>Blocks: <b>{doc.block_count}</b></span>
                  </>
                ) : (
                  <>
                    <span>IFC Elements: <b>{doc.ifc_element_count}</b></span>
                    <span>3D Geometry: <b>{doc.extraction_options_json?.ifc_extract_geometry ? "Enabled" : "Property/Qto Only"}</b></span>
                  </>
                )}
                <span>Unsupported: <b>{doc.unsupported_count}</b></span>
                <span>Peak RSS: <b>{doc.peak_rss_mb} MB</b></span>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => handleExport("json")}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Export JSON
              </button>
              <button
                type="button"
                onClick={() => handleExport("csv")}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Export CSV
              </button>
              <button
                type="button"
                onClick={() => handleExport("xlsx")}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                Export XLSX
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={
                doc.source_format.startsWith("dxf")
                  ? "Filter by handle, entity type, or layer..."
                  : "Filter by GlobalId, IFC class, name, or storey..."
              }
              className="w-full max-w-md rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
            />
            {doc.source_format.startsWith("dxf") ? (
              <div className="flex flex-wrap gap-1.5">
                {(["entities", "layers", "blocks", "dimensions", "unsupported"] as DxfTab[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setDxfTab(t)}
                    className={`rounded px-3 py-1 text-xs font-medium capitalize ${
                      dxfTab === t ? "bg-blue-600 text-white" : "border border-slate-300 bg-white text-slate-700"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {(["elements", "psets", "qsets", "geometry", "unsupported"] as IfcTab[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setIfcTab(t)}
                    className={`rounded px-3 py-1 text-xs font-medium capitalize ${
                      ifcTab === t ? "bg-blue-600 text-white" : "border border-slate-300 bg-white text-slate-700"
                    }`}
                  >
                    {t === "psets" ? "Property Sets" : t === "qsets" ? "Quantity Sets (Qto)" : t}
                  </button>
                ))}
              </div>
            )}
          </div>

          {doc.source_format.startsWith("dxf") && (
            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
              {dxfTab === "entities" && (
                <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                  <thead className="bg-slate-50 font-semibold text-slate-600">
                    <tr>
                      <th className="px-3 py-2">Handle</th>
                      <th className="px-3 py-2">Entity Type</th>
                      <th className="px-3 py-2">Layer</th>
                      <th className="px-3 py-2">Layout / Block</th>
                      <th className="px-3 py-2">Length / Area ({doc.source_units || "raw"})</th>
                      <th className="px-3 py-2">Classification</th>
                      <th className="px-3 py-2">Provenance</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredEntities.map((ent) => {
                      const len = ent.geometry_metrics_json?.length as number | null | undefined;
                      const area = ent.geometry_metrics_json?.area as number | null | undefined;
                      const clsCat = (ent.classification_json?.rule_based_category as string) || "";
                      const clsProv = (ent.classification_json?.classification_provenance as string) || "native";
                      return (
                        <tr key={ent.id} className="hover:bg-slate-50">
                          <td className="px-3 py-2 font-mono">{ent.handle}</td>
                          <td className="px-3 py-2 font-mono font-semibold text-blue-700">{ent.entity_type}</td>
                          <td className="px-3 py-2">{ent.layer_name}</td>
                          <td className="px-3 py-2 font-mono text-slate-500">{ent.layout_name || ent.block_name}</td>
                          <td className="px-3 py-2 font-mono">
                            {area != null ? `A=${area.toFixed(4)}` : len != null ? `L=${len.toFixed(4)}` : "—"}
                          </td>
                          <td className="px-3 py-2">
                            {clsCat ? (
                              <span className="inline-flex items-center gap-1">
                                <span>{clsCat}</span>
                                <ProvenanceBadge status={clsProv} />
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="px-3 py-2">
                            <ProvenanceBadge status={ent.provenance} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}

              {dxfTab === "layers" && (
                <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                  <thead className="bg-slate-50 font-semibold text-slate-600">
                    <tr>
                      <th className="px-3 py-2">Name</th>
                      <th className="px-3 py-2">Color</th>
                      <th className="px-3 py-2">Linetype</th>
                      <th className="px-3 py-2">State</th>
                      <th className="px-3 py-2">Placed Entities</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {layers.map((l) => (
                      <tr key={l.id}>
                        <td className="px-3 py-2 font-medium">{l.name}</td>
                        <td className="px-3 py-2 font-mono">{l.color ?? "—"}</td>
                        <td className="px-3 py-2 font-mono">{l.linetype}</td>
                        <td className="px-3 py-2">
                          {l.is_on ? "ON" : "OFF"} / {l.is_frozen ? "FROZEN" : "THAWED"} / {l.is_locked ? "LOCKED" : "OPEN"}
                        </td>
                        <td className="px-3 py-2 font-mono">{l.entity_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {dxfTab === "blocks" && (
                <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                  <thead className="bg-slate-50 font-semibold text-slate-600">
                    <tr>
                      <th className="px-3 py-2">Block Name</th>
                      <th className="px-3 py-2">Base Point</th>
                      <th className="px-3 py-2">Entities</th>
                      <th className="px-3 py-2">Nested Blocks</th>
                      <th className="px-3 py-2">XREF</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {blocks.map((b) => (
                      <tr key={b.id}>
                        <td className="px-3 py-2 font-mono font-medium">{b.name}</td>
                        <td className="px-3 py-2 font-mono">{JSON.stringify(b.base_point_json)}</td>
                        <td className="px-3 py-2 font-mono">{b.entity_count}</td>
                        <td className="px-3 py-2 font-mono">{b.nested_blocks_json.join(", ") || "—"}</td>
                        <td className="px-3 py-2">{b.is_xref ? `XREF (unloaded: ${b.xref_path})` : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {dxfTab === "dimensions" && (
                <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                  <thead className="bg-slate-50 font-semibold text-slate-600">
                    <tr>
                      <th className="px-3 py-2">Handle</th>
                      <th className="px-3 py-2">Kind</th>
                      <th className="px-3 py-2">Native Actual Measurement</th>
                      <th className="px-3 py-2">Calculated Geometry</th>
                      <th className="px-3 py-2">Text Override (Separate)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredEntities
                      .filter((e) => e.dimension_data_json && Object.keys(e.dimension_data_json).length > 0)
                      .map((e) => (
                        <tr key={e.id}>
                          <td className="px-3 py-2 font-mono">{e.handle}</td>
                          <td className="px-3 py-2">{String(e.dimension_data_json.dimension_kind || "")}</td>
                          <td className="px-3 py-2 font-mono">
                            {e.dimension_data_json.actual_measurement != null
                              ? String(e.dimension_data_json.actual_measurement)
                              : "—"}
                          </td>
                          <td className="px-3 py-2 font-mono text-teal-700">
                            {e.dimension_data_json.geometry_measured != null
                              ? Number(e.dimension_data_json.geometry_measured).toFixed(4)
                              : "—"}
                          </td>
                          <td className="px-3 py-2 font-mono text-amber-700">
                            {e.dimension_data_json.has_text_override
                              ? String(e.dimension_data_json.text_override)
                              : "None (<>)"}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              )}

              {dxfTab === "unsupported" && (
                <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                  <thead className="bg-slate-50 font-semibold text-slate-600">
                    <tr>
                      <th className="px-3 py-2">Handle</th>
                      <th className="px-3 py-2">Type</th>
                      <th className="px-3 py-2">Layer</th>
                      <th className="px-3 py-2">Warnings</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredEntities
                      .filter((e) => !e.is_supported || e.warnings_json.length > 0)
                      .map((e) => (
                        <tr key={e.id}>
                          <td className="px-3 py-2 font-mono">{e.handle}</td>
                          <td className="px-3 py-2 font-mono">{e.entity_type}</td>
                          <td className="px-3 py-2">{e.layer_name}</td>
                          <td className="px-3 py-2 text-orange-800">{e.warnings_json.join("; ")}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {doc.source_format === "ifc_step" && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white lg:col-span-6">
                <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
                  <thead className="bg-slate-50 font-semibold text-slate-600">
                    <tr>
                      <th className="px-3 py-2">STEP</th>
                      <th className="px-3 py-2">IFC Class</th>
                      <th className="px-3 py-2">Name</th>
                      <th className="px-3 py-2">Storey</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredElements.map((el) => (
                      <tr
                        key={el.id}
                        onClick={() => setSelectedEl(el)}
                        className={`cursor-pointer hover:bg-blue-50 ${selectedEl?.id === el.id ? "bg-blue-50" : ""}`}
                      >
                        <td className="px-3 py-2 font-mono text-slate-500">#{el.step_id}</td>
                        <td className="px-3 py-2 font-mono font-semibold text-blue-700">{el.ifc_class}</td>
                        <td className="px-3 py-2">{el.name || el.global_id}</td>
                        <td className="px-3 py-2 text-slate-600">{el.storey_name || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs lg:col-span-6">
                {!selectedEl ? (
                  <p className="text-slate-500">Select an IFC element to inspect properties, quantities, materials, and geometry.</p>
                ) : (
                  <div className="space-y-4">
                    <div className="border-b border-slate-100 pb-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-slate-900">
                          [{selectedEl.ifc_class}] {selectedEl.name || "(unnamed)"}
                        </span>
                        <ProvenanceBadge status={selectedEl.provenance} />
                      </div>
                      <div className="mt-1 font-mono text-[11px] text-slate-500">
                        GlobalId: {selectedEl.global_id} | STEP #{selectedEl.step_id}
                        {selectedEl.object_type ? ` | ObjectType: ${selectedEl.object_type}` : ""}
                      </div>
                    </div>

                    {ifcTab === "elements" && (
                      <div className="space-y-2">
                        <div>
                          <span className="font-semibold">Spatial Parent GUID:</span>{" "}
                          <span className="font-mono">{selectedEl.spatial_parent_guid || "Root"}</span>
                        </div>
                        <div>
                          <span className="font-semibold">PredefinedType:</span> {selectedEl.predefined_type || "—"}
                        </div>
                        <div>
                          <span className="font-semibold">Materials:</span>{" "}
                          {selectedEl.materials_json.length > 0 ? JSON.stringify(selectedEl.materials_json) : "—"}
                        </div>
                        <div>
                          <span className="font-semibold">World Origin:</span>{" "}
                          <span className="font-mono">
                            {JSON.stringify(selectedEl.placement_json?.world_origin || null)}
                          </span>
                        </div>
                      </div>
                    )}

                    {ifcTab === "psets" && (
                      <div className="space-y-3">
                        {selectedEl.property_sets_json.map((ps, idx) => (
                          <div key={idx} className="rounded border border-slate-200 p-2">
                            <div className="mb-1 flex items-center justify-between font-semibold">
                              <span>{ps.name}</span>
                              <span className="font-mono text-[10px] text-slate-500">
                                {ps.is_type_inherited ? "Type-Inherited" : "Instance"}
                              </span>
                            </div>
                            <pre className="overflow-x-auto text-[11px] text-slate-700">
                              {JSON.stringify(ps.properties, null, 2)}
                            </pre>
                          </div>
                        ))}
                        {selectedEl.property_sets_json.length === 0 && (
                          <p className="text-slate-500">No PropertySets attached to this element.</p>
                        )}
                      </div>
                    )}

                    {ifcTab === "qsets" && (
                      <div className="space-y-3">
                        <div className="font-semibold text-slate-700">Native IfcElementQuantity (Qto_*)</div>
                        {selectedEl.quantity_sets_json.map((qs, idx) => (
                          <div key={idx} className="rounded border border-emerald-200 bg-emerald-50/40 p-2">
                            <div className="mb-1 flex items-center justify-between font-semibold">
                              <span>{qs.name}</span>
                              <ProvenanceBadge status="native" />
                            </div>
                            {qs.quantities.map((q, qidx) => (
                              <div key={qidx} className="flex justify-between font-mono text-[11px]">
                                <span>{q.name} ({q.quantity_type})</span>
                                <span>
                                  {q.raw_value} {q.raw_unit}
                                  {q.normalized_value != null ? ` (${q.normalized_value.toFixed(4)} ${q.normalized_unit})` : ""}
                                </span>
                              </div>
                            ))}
                          </div>
                        ))}
                        {selectedEl.quantity_sets_json.length === 0 && (
                          <p className="text-slate-500">No native Qto_* quantity sets on this element.</p>
                        )}
                      </div>
                    )}

                    {ifcTab === "geometry" && (
                      <div className="space-y-2 rounded border border-slate-200 p-3">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold">Calculated 3D Mesh Summary</span>
                          <ProvenanceBadge status={selectedEl.geometry_summary_json.provenance || "calculated"} />
                        </div>
                        <div className="font-mono text-[11px]">
                          Status: {selectedEl.geometry_summary_json.status}
                        </div>
                        {selectedEl.geometry_summary_json.status === "calculated" && (
                          <div className="space-y-1 font-mono text-[11px]">
                            <div>BBox Dimensions (X,Y,Z): {JSON.stringify(selectedEl.geometry_summary_json.dimensions_xyz)}</div>
                            <div>Surface Area: {selectedEl.geometry_summary_json.surface_area?.toFixed(4)} m²</div>
                            <div>
                              Volume:{" "}
                              {selectedEl.geometry_summary_json.volume != null
                                ? `${selectedEl.geometry_summary_json.volume.toFixed(4)} m³ (watertight)`
                                : "None (open/non-manifold mesh)"}
                            </div>
                            <div>
                              Vertices: {selectedEl.geometry_summary_json.vertex_count} | Faces:{" "}
                              {selectedEl.geometry_summary_json.face_count}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {ifcTab === "unsupported" && (
                      <div className="space-y-2">
                        <div>Warnings: {selectedEl.warnings_json.join("; ") || "None"}</div>
                        <div>Geometry status: {selectedEl.geometry_summary_json.status}</div>
                        {selectedEl.geometry_summary_json.error && (
                          <div className="text-rose-700">{selectedEl.geometry_summary_json.error}</div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
