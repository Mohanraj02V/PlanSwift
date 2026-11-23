"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { FormulaRecord, PaginatedResponse } from "@/types/api";

type CategoryPreset = "all" | "cost" | "calc" | "page_ref" | "pascal" | "page_dims";

export default function FormulasPage() {
  const { selectedProjectId } = useProjectContext();
  const [formulas, setFormulas] = useState<FormulaRecord[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [preset, setPreset] = useState<CategoryPreset>("all");
  const [statusFilter, setStatusFilter] = useState("");
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams();
    params.set("page", String(page));
    if (selectedProjectId) params.set("project_version__project", selectedProjectId);
    if (statusFilter) params.set("evaluation_status", statusFilter);

    if (preset === "cost" || preset === "calc" || preset === "page_ref" || preset === "page_dims") {
      params.set("category", preset);
    } else if (preset === "pascal") {
      params.set("is_pascal_script", "true");
    }

    if (search) {
      params.set("search", search);
    }

    apiRequest<PaginatedResponse<FormulaRecord>>(`/formulas/?${params.toString()}`)
      .then((res) => {
        setFormulas(res.results || []);
        setTotalCount(res.count || 0);
        setHasNext(Boolean(res.next));
        setHasPrev(Boolean(res.previous));
      })
      .catch(() => {});
  }, [selectedProjectId, page, search, preset, statusFilter]);

  const applyPreset = (next: CategoryPreset) => {
    setPreset(next);
    setPage(1);
  };

  return (
    <AppShell title="Formula & Dependency Explorer">
      <div className="mb-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search property name, object, GUID, or expression..."
            className="w-full max-w-md rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
          />
          <select
            aria-label="Formula Evaluation Status"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
          >
            <option value="">All Statuses</option>
            <option value="computed_by_planswift">computed_by_planswift</option>
            <option value="unresolved">unresolved</option>
          </select>
          <span className="text-xs text-slate-500">{totalCount.toLocaleString()} matching formulas</span>
        </div>

        <div className="flex flex-wrap gap-2 text-xs">
          {(
            [
              ["all", "All Formulas"],
              ["cost", "Cost & Pricing ([Qty] * [Cost Each])"],
              ["calc", "Takeoff & Math ([Takeoff], [Point Count], ...)"],
              ["page_ref", "Page & Parent Lookups"],
              ["pascal", "PascalScript"],
              ["page_dims", "Page System Vars ([!PageWidth]/[Height])"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => applyPreset(key)}
              className={`rounded-full border px-3 py-1 font-medium transition ${
                preset === key
                  ? "border-blue-600 bg-blue-600 text-white"
                  : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {formulas.map((f) => (
          <div key={f.id} className="rounded-lg border border-slate-200 bg-white p-4 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-semibold text-slate-900">{f.object_name}</span>
                <span className="mx-1.5 text-slate-400">/</span>
                <span className="font-mono text-blue-700">{f.property_name}</span>
              </div>
              <div className="flex items-center gap-2">
                {f.formula_key.includes(":COM:") && (
                  <span className="rounded bg-indigo-50 px-2 py-0.5 font-mono font-medium text-indigo-700">
                    COM runtime
                  </span>
                )}
                {f.planswift_evaluated_value && (
                  <span className="rounded bg-teal-100 px-2 py-0.5 font-mono font-semibold text-teal-800">
                    Evaluated: {f.planswift_evaluated_value}
                  </span>
                )}
                {f.is_pascal_script && <span className="rounded bg-slate-100 px-2 py-0.5 font-mono">PascalScript</span>}
                {f.has_circular_dependency && (
                  <span className="rounded bg-rose-100 px-2 py-0.5 font-semibold text-rose-700">Circular Ref</span>
                )}
                <ProvenanceBadge status={f.evaluation_status} />
              </div>
            </div>
            <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-2.5 font-mono text-[11px] text-slate-100">
              {f.raw_expression}
            </pre>
            {f.dependencies.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {f.dependencies.map((d, i) => (
                  <span key={i} className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11px]">
                    {d.reference_kind}: {d.raw_token}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between text-xs text-slate-600">
        <button
          type="button"
          disabled={!hasPrev}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          className="rounded border border-slate-300 bg-white px-3 py-1.5 font-medium disabled:opacity-40"
        >
          Previous
        </button>
        <span>Page {page}</span>
        <button
          type="button"
          disabled={!hasNext}
          onClick={() => setPage((p) => p + 1)}
          className="rounded border border-slate-300 bg-white px-3 py-1.5 font-medium disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </AppShell>
  );
}
