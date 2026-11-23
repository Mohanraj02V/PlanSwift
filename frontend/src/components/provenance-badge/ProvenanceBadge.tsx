"use client";

import React from "react";
import type { ProvenanceStatus } from "@/types/api";

const STATUS_STYLES: Record<ProvenanceStatus, { bg: string; label: string }> = {
  original: { bg: "bg-emerald-100 text-emerald-800 border-emerald-300", label: "original" },
  api_extracted: { bg: "bg-sky-100 text-sky-800 border-sky-300", label: "api_extracted" },
  normalized: { bg: "bg-indigo-100 text-indigo-800 border-indigo-300", label: "normalized" },
  computed_by_planswift: { bg: "bg-teal-100 text-teal-800 border-teal-300", label: "computed_by_planswift" },
  derived: { bg: "bg-amber-100 text-amber-800 border-amber-300", label: "derived" },
  ai_inferred: { bg: "bg-purple-100 text-purple-800 border-purple-300", label: "ai_inferred" },
  unresolved: { bg: "bg-orange-100 text-orange-800 border-orange-300", label: "unresolved" },
  unsupported: { bg: "bg-rose-100 text-rose-800 border-rose-300", label: "unsupported" },
};

export function ProvenanceBadge({ status }: { status: ProvenanceStatus | string }) {
  const cfg = STATUS_STYLES[status as ProvenanceStatus] ?? {
    bg: "bg-slate-100 text-slate-700 border-slate-300",
    label: status || "unknown",
  };
  return (
    <span
      data-testid="provenance-badge"
      className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-xs font-medium ${cfg.bg}`}
    >
      {cfg.label}
    </span>
  );
}
