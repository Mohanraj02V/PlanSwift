"use client";

import React, { useState } from "react";
import { GeometryDataViewer } from "@/components/geometry-data-viewer/GeometryDataViewer";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { PropertyViewer } from "@/components/property-viewer/PropertyViewer";
import type { FormulaRecord, GeometryFeature, MeasurementRecord, ProjectObject } from "@/types/api";

type InspectorTab =
  | "all"
  | "overview"
  | "properties"
  | "geometry"
  | "measurements"
  | "formulas"
  | "calculations"
  | "relationships"
  | "raw"
  | "provenance"
  | "validation";

export function ObjectInspector({
  object,
  measurements = [],
  formulas = [],
  geometries = [],
  relationships = [],
}: {
  object: ProjectObject;
  measurements?: MeasurementRecord[];
  formulas?: FormulaRecord[];
  geometries?: GeometryFeature[];
  relationships?: Array<{ relationship_type: string; source_guid: string; target_guid: string }>;
}) {
  const [tab, setTab] = useState<InspectorTab>("all");

  const show = (section: InspectorTab) => tab === "all" || tab === section;

  const emptyNamedProps = (object.properties || []).filter((p) => p.name === "").length;
  const unresolvedFormulas = formulas.filter((f) => f.evaluation_status === "unresolved").length;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-blue-700">{object.native_class}</div>
            <h2 className="text-lg font-bold text-slate-900">{object.name || "(Unnamed Object)"}</h2>
            <p className="mt-1 font-mono text-xs text-slate-500">
              Native GUID: {object.native_guid} | Parent: {object.parent_guid || "Root"}
            </p>
            <p className="mt-0.5 text-xs text-slate-600">Path: {object.root_path}</p>
          </div>
          <ProvenanceBadge status={object.provenance} />
        </div>

        <div className="mt-4 flex flex-wrap gap-1.5 border-t border-slate-100 pt-3 text-xs">
          {(
            [
              ["all", "All Sections"],
              ["overview", "Overview"],
              ["properties", `Native Properties (${object.properties?.length ?? object.property_count ?? 0})`],
              ["geometry", `Geometry (${geometries.length})`],
              ["measurements", `Measurements (${measurements.length})`],
              ["formulas", `Formulas (${formulas.length})`],
              ["calculations", "Calculations"],
              ["relationships", `Relationships (${relationships.length})`],
              ["raw", "Raw Native Data"],
              ["provenance", "Provenance"],
              ["validation", "Validation"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`rounded border px-2.5 py-1 font-medium transition ${
                tab === key
                  ? "border-blue-600 bg-blue-600 text-white"
                  : "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {show("overview") && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Overview</h3>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded bg-slate-50 p-2">
              <dt className="text-slate-500">Native Class / Type</dt>
              <dd className="font-mono font-semibold">{object.native_class} / {object.native_type || "—"}</dd>
            </div>
            <div className="rounded bg-slate-50 p-2">
              <dt className="text-slate-500">Hierarchy Depth / Order</dt>
              <dd className="font-mono font-semibold">{object.depth} / {object.order_index ?? "—"}</dd>
            </div>
            <div className="rounded bg-slate-50 p-2">
              <dt className="text-slate-500">Page GUID Link</dt>
              <dd className="truncate font-mono">{object.page_guid || "—"}</dd>
            </div>
            <div className="rounded bg-slate-50 p-2">
              <dt className="text-slate-500">Division / Cost Code</dt>
              <dd className="font-mono">{object.division || "—"} / {object.cost_code || "—"}</dd>
            </div>
          </dl>
          {!object.is_known_class && (
            <div className="mt-3 rounded border border-rose-200 bg-rose-50 p-2 text-rose-800">
              Unsupported or custom native class preserved intact in canonical raw storage.
            </div>
          )}
        </div>
      )}

      {show("measurements") && measurements.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-900">Native Measurements & Quantities</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 font-semibold text-slate-600">
                <tr>
                  <th className="px-3 py-2">Property</th>
                  <th className="px-3 py-2">Raw Formula / Value</th>
                  <th className="px-3 py-2">Reconstructed (Geom)</th>
                  <th className="px-3 py-2">Calculated (Formula)</th>
                  <th className="px-3 py-2">Unit</th>
                  <th className="px-3 py-2">Provenance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {measurements.map((m) => (
                  <tr key={m.id}>
                    <td className="px-3 py-2 font-medium">{m.property_name}</td>
                    <td className="px-3 py-2 font-mono">{m.raw_formula || m.native_stored_value || "—"}</td>
                    <td className="px-3 py-2 font-mono">{m.reconstructed_quantity ?? "—"}</td>
                    <td className="px-3 py-2 font-mono font-semibold text-teal-800">
                      {m.calculated_quantity ?? m.derived_quantity ?? "—"}
                    </td>
                    <td className="px-3 py-2">{m.unit || m.normalized_unit || "—"}</td>
                    <td className="px-3 py-2">
                      <ProvenanceBadge status={m.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {show("geometry") && geometries.length > 0 && (
        <div className="space-y-3">
          {geometries.map((g) => (
            <GeometryDataViewer key={g.id} feature={g} />
          ))}
        </div>
      )}

      {show("formulas") && formulas.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-900">Formulas &amp; Dependency Graph</h3>
          <div className="space-y-2">
            {formulas.map((f) => (
              <div key={f.id} className="rounded border border-slate-200 p-3 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold text-slate-800">{f.property_name}</span>
                  <div className="flex items-center gap-2">
                    {f.calculated_value && (
                      <span className="rounded bg-teal-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-teal-800">
                        Calculated: {f.calculated_value} {f.calculation_unit || ""}
                      </span>
                    )}
                    {f.is_pascal_script && (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
                        PascalScript
                      </span>
                    )}
                    <ProvenanceBadge status={f.evaluation_status} />
                  </div>
                </div>
                <pre className="mt-1.5 overflow-x-auto rounded bg-slate-900 p-2 font-mono text-[11px] text-slate-100">
                  {f.raw_expression}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}

      {show("calculations") && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Independent Calculation Audit</h3>
          {formulas.length > 0 ? (
            <div className="space-y-2">
              {formulas.map((f) => (
                <div key={`calc-${f.id}`} className="rounded border border-slate-100 bg-slate-50 p-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{f.property_name}</span>
                    <ProvenanceBadge status={f.evaluation_status} />
                  </div>
                  <div className="mt-1 font-mono text-slate-700">
                    Result: {f.calculated_value || "null"} {f.calculation_unit || ""}{" "}
                    {f.calculation_reason ? `(reason: ${f.calculation_reason})` : ""}
                  </div>
                  {f.calculation_inputs_json && Object.keys(f.calculation_inputs_json).length > 0 && (
                    <div className="mt-1 font-mono text-[11px] text-slate-500">
                      Inputs: {JSON.stringify(f.calculation_inputs_json)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500">No formula calculations attached to this object.</p>
          )}
        </div>
      )}

      {show("relationships") && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Relationships</h3>
          {relationships.length > 0 ? (
            <div className="space-y-1 font-mono">
              {relationships.map((r, i) => (
                <div key={i} className="rounded bg-slate-50 px-2 py-1">
                  [{r.relationship_type}] {r.source_guid} -&gt; {r.target_guid}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500">Parent GUID: {object.parent_guid || "Root"}</p>
          )}
        </div>
      )}

      {show("properties") && object.properties && <PropertyViewer properties={object.properties} />}

      {show("raw") && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Raw Native XML Attributes</h3>
          <pre className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-[11px] text-slate-100">
            {JSON.stringify(object.raw_attributes || {}, null, 2)}
          </pre>
        </div>
      )}

      {show("provenance") && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Provenance &amp; Lineage</h3>
          <div className="flex items-center gap-2">
            <span>Object classification:</span>
            <ProvenanceBadge status={object.provenance} />
            <span className="text-slate-500">| Extracted cleanly from native XML without COM or rasterization.</span>
          </div>
        </div>
      )}

      {show("validation") && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-xs">
          <h3 className="mb-2 text-sm font-semibold text-slate-900">Object Validation</h3>
          <ul className="list-disc space-y-1 pl-4 text-slate-700">
            <li>Known native class: {object.is_known_class ? "Yes" : "No (preserved raw in unsupported store)"}</li>
            <li>Empty-name properties preserved: {emptyNamedProps}</li>
            <li>Formulas unresolved/unsupported: {unresolvedFormulas} / {formulas.length}</li>
          </ul>
        </div>
      )}
    </div>
  );
}
