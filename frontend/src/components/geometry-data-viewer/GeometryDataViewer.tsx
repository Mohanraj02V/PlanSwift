"use client";

import React from "react";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import type { GeometryFeature } from "@/types/api";

export function GeometryDataViewer({ feature }: { feature: GeometryFeature }) {
  const points = feature.points ?? [];
  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">
            Structured Coordinate Geometry ({feature.geometry_type})
          </h3>
          <p className="font-mono text-xs text-slate-500">
            Section: {feature.section_guid} | Coordinate System: {feature.coordinate_system}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ProvenanceBadge status={feature.provenance} />
          <ProvenanceBadge status={feature.derived_metrics_provenance} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <div className="rounded bg-slate-50 p-2">
          <div className="text-slate-500">Point Count</div>
          <div className="font-mono text-sm font-semibold">{feature.point_count}</div>
        </div>
        <div className="rounded bg-slate-50 p-2">
          <div className="text-slate-500">BBox Min (X, Y)</div>
          <div className="font-mono text-xs">
            {feature.bbox_min_x !== null ? `${feature.bbox_min_x.toFixed(2)}, ${feature.bbox_min_y?.toFixed(2)}` : "—"}
          </div>
        </div>
        <div className="rounded bg-slate-50 p-2">
          <div className="text-slate-500">BBox Max (X, Y)</div>
          <div className="font-mono text-xs">
            {feature.bbox_max_x !== null ? `${feature.bbox_max_x.toFixed(2)}, ${feature.bbox_max_y?.toFixed(2)}` : "—"}
          </div>
        </div>
        <div className="rounded bg-slate-50 p-2">
          <div className="text-slate-500">Page Reference GUID</div>
          <div className="truncate font-mono text-xs">{feature.page_guid || "—"}</div>
        </div>
      </div>

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
          <thead className="bg-slate-50 font-semibold text-slate-600">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Raw X</th>
              <th className="px-3 py-2">Raw Y</th>
              <th className="px-3 py-2">PointType</th>
              <th className="px-3 py-2">Normalized (X, Y)</th>
              <th className="px-3 py-2">Provenance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 font-mono">
            {points.map((pt) => (
              <tr key={pt.point_order}>
                <td className="px-3 py-1.5 text-slate-500">{pt.point_order}</td>
                <td className="px-3 py-1.5">{pt.raw_x}</td>
                <td className="px-3 py-1.5">{pt.raw_y}</td>
                <td className="px-3 py-1.5">{pt.point_type}</td>
                <td className="px-3 py-1.5 text-slate-400">
                  {pt.normalized_x !== null ? `${pt.normalized_x}, ${pt.normalized_y}` : "uncalibrated (raw preserved)"}
                </td>
                <td className="px-3 py-1.5">
                  <ProvenanceBadge status={pt.provenance} />
                </td>
              </tr>
            ))}
            {points.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-4 text-center text-slate-500">
                  Empty DigitizerData &lt;Points/&gt; container.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
