"use client";

import React from "react";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { PropertyViewer } from "@/components/property-viewer/PropertyViewer";
import type { FormulaRecord, MeasurementRecord, ProjectObject } from "@/types/api";

export function ObjectInspector({
  object,
  measurements = [],
  formulas = [],
}: {
  object: ProjectObject;
  measurements?: MeasurementRecord[];
  formulas?: FormulaRecord[];
}) {
  return (
    <div className="space-y-6">
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
      </div>

      {measurements.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-900">Native Measurements & Quantities</h3>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 font-semibold text-slate-600">
                <tr>
                  <th className="px-3 py-2">Property</th>
                  <th className="px-3 py-2">Raw Formula</th>
                  <th className="px-3 py-2">Derived Qty</th>
                  <th className="px-3 py-2">PlanSwift Computed</th>
                  <th className="px-3 py-2">Unit</th>
                  <th className="px-3 py-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {measurements.map((m) => (
                  <tr key={m.id}>
                    <td className="px-3 py-2 font-medium">{m.property_name}</td>
                    <td className="px-3 py-2 font-mono">{m.raw_formula || m.native_stored_value || "—"}</td>
                    <td className="px-3 py-2 font-mono font-semibold">{m.derived_quantity ?? "—"}</td>
                    <td className="px-3 py-2 font-mono">{m.planswift_computed_quantity ?? "—"}</td>
                    <td className="px-3 py-2">{m.normalized_unit || m.unit || "—"}</td>
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

      {formulas.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-slate-900">Formulas & Dependency Graph</h3>
          <div className="space-y-2">
            {formulas.map((f) => (
              <div key={f.id} className="rounded border border-slate-200 p-3 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-800">{f.property_name}</span>
                  <div className="flex items-center gap-2">
                    {f.planswift_evaluated_value && (
                      <span className="rounded bg-teal-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-teal-800">
                        Evaluated: {f.planswift_evaluated_value}
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

      {object.properties && <PropertyViewer properties={object.properties} />}
    </div>
  );
}
