"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ObjectInspector } from "@/components/object-inspector/ObjectInspector";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { FormulaRecord, HierarchyNode, MeasurementRecord, PaginatedResponse, ProjectObject } from "@/types/api";

export default function ProjectExplorerPage() {
  const { selectedProjectId } = useProjectContext();
  const [nodes, setNodes] = useState<HierarchyNode[]>([]);
  const [selectedObject, setSelectedObject] = useState<ProjectObject | null>(null);
  const [measurements, setMeasurements] = useState<MeasurementRecord[]>([]);
  const [formulas, setFormulas] = useState<FormulaRecord[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!selectedProjectId) return;
    apiRequest<{ nodes: HierarchyNode[] }>(`/hierarchy/tree/${selectedProjectId}/?max_depth=3`)
      .then((res) => setNodes(res.nodes || []))
      .catch(() => {});
  }, [selectedProjectId]);

  const handleSelectNode = async (node: HierarchyNode) => {
    try {
      const projParam = selectedProjectId ? `project_version__project=${encodeURIComponent(selectedProjectId)}&` : "";
      const [detail, measResp, formResp] = await Promise.all([
        apiRequest<ProjectObject>(`/objects/${node.id}/`),
        apiRequest<PaginatedResponse<MeasurementRecord>>(
          `/measurements/?${projParam}search=${encodeURIComponent(node.native_guid)}`
        ),
        apiRequest<PaginatedResponse<FormulaRecord>>(
          `/formulas/?${projParam}search=${encodeURIComponent(node.native_guid)}`
        ),
      ]);
      setSelectedObject(detail);
      setMeasurements(measResp.results || []);
      setFormulas((formResp.results || []).filter((f) => f.object_guid === node.native_guid));
    } catch {
      // ignore
    }
  };

  const toggleExpand = async (node: HierarchyNode) => {
    const isNowOpen = !expanded[node.native_guid];
    setExpanded((prev) => ({ ...prev, [node.native_guid]: isNowOpen }));
    if (isNowOpen && !nodes.some((n) => n.parent_guid === node.native_guid)) {
      const childResp = await apiRequest<{ nodes: HierarchyNode[] }>(
        `/hierarchy/tree/${selectedProjectId}/?parent_guid=${encodeURIComponent(node.native_guid)}`
      );
      if (childResp.nodes?.length) {
        setNodes((prev) => {
          const seen = new Set(prev.map((p) => p.native_guid));
          return [...prev, ...childResp.nodes.filter((c) => !seen.has(c.native_guid))];
        });
      }
    }
  };

  const renderTree = (parentGuid: string | null) => {
    const children = nodes.filter((n) => (n.parent_guid || null) === parentGuid);
    if (!children.length) return null;
    return (
      <ul className="space-y-1 border-l border-slate-200 pl-3">
        {children.map((node) => (
          <li key={node.native_guid}>
            <div className="flex items-center gap-1.5 rounded px-1.5 py-1 text-xs hover:bg-slate-100">
              <button
                type="button"
                onClick={() => toggleExpand(node)}
                className="w-4 font-mono text-slate-500"
                aria-label={`Expand ${node.name}`}
              >
                {expanded[node.native_guid] ? "▾" : "▸"}
              </button>
              <button
                type="button"
                onClick={() => handleSelectNode(node)}
                className="flex flex-1 items-center justify-between gap-2 text-left"
              >
                <span className="truncate font-medium text-slate-900">
                  <span className="mr-1.5 font-mono text-[11px] text-blue-700">[{node.native_class}]</span>
                  {node.name || node.native_guid}
                </span>
                <ProvenanceBadge status={node.provenance} />
              </button>
            </div>
            {expanded[node.native_guid] && renderTree(node.native_guid)}
          </li>
        ))}
      </ul>
    );
  };

  return (
    <AppShell title="Native Project Hierarchy Explorer">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="max-h-[78vh] overflow-y-auto rounded-lg border border-slate-200 bg-white p-3 lg:col-span-5">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            PlanSwift Tree ({nodes.length} loaded nodes)
          </h2>
          {nodes.length > 0 ? renderTree(null) : <p className="text-xs text-slate-500">Select an extracted project.</p>}
        </div>
        <div className="lg:col-span-7">
          {selectedObject ? (
            <ObjectInspector object={selectedObject} measurements={measurements} formulas={formulas} />
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
              Select any PlanSwift item, page, folder, takeoff object, or section to inspect its native GUID,
              properties, formulas, and provenance.
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
