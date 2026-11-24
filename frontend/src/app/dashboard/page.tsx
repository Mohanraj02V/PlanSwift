"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { ExtractionRun, PaginatedResponse, ValidationResult } from "@/types/api";

export default function DashboardPage() {
  const { projects, selectedProject } = useProjectContext();
  const [runs, setRuns] = useState<ExtractionRun[]>([]);
  const [validations, setValidations] = useState<ValidationResult[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiRequest<PaginatedResponse<ExtractionRun>>("/extraction/"),
      apiRequest<PaginatedResponse<ValidationResult>>("/validation/"),
    ])
      .then(([r, v]) => {
        setRuns(r.results || []);
        setValidations(v.results || []);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load dashboard."));
  }, []);

  const totalObjects = projects.reduce((acc, p) => acc + (p.object_count || 0), 0);
  const completedRuns = runs.filter((r) => r.status === "COMPLETED").length;
  const failedRuns = runs.filter((r) => r.status === "FAILED").length;
  const latestVal = validations[0];

  return (
    <AppShell title="Platform Dashboard">
      {error && (
        <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          {error} — <Link href="/login" className="underline">Sign in</Link> to inspect live project metrics.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs font-medium text-slate-500">Total Projects</div>
          <div className="mt-1 text-2xl font-bold text-slate-900">{projects.length}</div>
          <div className="mt-1 text-xs text-slate-500">
            Active: {selectedProject ? selectedProject.name : "None selected"}
          </div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs font-medium text-slate-500">Total Native Objects</div>
          <div className="mt-1 text-2xl font-bold text-slate-900">{totalObjects.toLocaleString()}</div>
          <div className="mt-1 text-xs text-slate-500">Extracted without rasterization</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs font-medium text-slate-500">Extraction Jobs</div>
          <div className="mt-1 text-2xl font-bold text-emerald-700">{completedRuns} completed</div>
          <div className="mt-1 text-xs text-rose-600">{failedRuns} failed</div>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs font-medium text-slate-500">Latest Validation</div>
          <div className="mt-1 text-2xl font-bold text-blue-700">
            {latestVal ? `${latestVal.overall_verified_accuracy_pct}%` : "—"}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {latestVal ? `${latestVal.unresolved_formulas} unresolved / ${latestVal.unknown_class_objects} unsupported` : "No runs validated yet"}
          </div>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Recent Extraction Runs</h2>
            <Link href="/extraction" className="text-xs text-blue-600 hover:underline">
              Manage extractions
            </Link>
          </div>
          <div className="space-y-2">
            {runs.slice(0, 6).map((run) => (
              <div key={run.id} className="flex items-center justify-between rounded border border-slate-100 p-2.5 text-xs">
                <div>
                  <div className="font-semibold text-slate-900">{run.project_name}</div>
                  <div className="font-mono text-[11px] text-slate-500">
                    {run.adapter_used || "pending"} • {run.duration_seconds}s • {run.peak_memory_mb} MB
                  </div>
                </div>
                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 font-mono text-[11px] font-semibold">
                  {run.status}
                </span>
              </div>
            ))}
            {runs.length === 0 && <p className="text-xs text-slate-500">No extraction runs recorded yet.</p>}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-900">Validation &amp; Provenance Summary</h2>
            <Link href="/validation" className="text-xs text-blue-600 hover:underline">
              Full report
            </Link>
          </div>
          {latestVal ? (
            <dl className="grid grid-cols-2 gap-3 text-xs">
              <div className="rounded bg-slate-50 p-2">
                <dt className="text-slate-500">Objects Discovered / Extracted</dt>
                <dd className="font-mono text-sm font-bold">
                  {latestVal.objects_discovered} / {latestVal.objects_extracted}
                </dd>
              </div>
              <div className="rounded bg-slate-50 p-2">
                <dt className="text-slate-500">Properties (Empty Names)</dt>
                <dd className="font-mono text-sm font-bold">
                  {latestVal.properties_extracted} ({latestVal.empty_name_properties})
                </dd>
              </div>
              <div className="rounded bg-slate-50 p-2">
                <dt className="text-slate-500">Pages Matched to TIFF</dt>
                <dd className="font-mono text-sm font-bold">
                  {latestVal.pages_matched_to_tiff} / {latestVal.pages_discovered}
                </dd>
              </div>
              <div className="rounded bg-slate-50 p-2">
                <dt className="text-slate-500">Native Digitizer Points</dt>
                <dd className="font-mono text-sm font-bold">
                  {latestVal.points_extracted} ({latestVal.sections_extracted} sections)
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-xs text-slate-500">Run an extraction to inspect validation metrics.</p>
          )}
        </div>
      </div>
    </AppShell>
  );
}
