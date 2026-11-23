"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";
import type { ExtractionRun, PaginatedResponse, ProjectSource } from "@/types/api";

export default function ExtractionPage() {
  const { projects, selectedProjectId, refreshContext } = useProjectContext();
  const [sourcePath, setSourcePath] = useState("");
  const [sources, setSources] = useState<ProjectSource[]>([]);
  const [runs, setRuns] = useState<ExtractionRun[]>([]);
  const [comEnv, setComEnv] = useState<Record<string, unknown> | null>(null);
  const [comFile, setComFile] = useState<File | null>(null);
  const [comStatusMsg, setComStatusMsg] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadData = async () => {
    try {
      const [srcRes, runRes, envRes] = await Promise.all([
        apiRequest<PaginatedResponse<ProjectSource>>("/project-sources/"),
        apiRequest<PaginatedResponse<ExtractionRun>>("/extraction/"),
        apiRequest<Record<string, unknown>>("/planswift/environment/"),
      ]);
      setSources(srcRes.results || []);
      setRuns(runRes.results || []);
      setComEnv(envRes);
    } catch {
      // Ignore until signed in
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleRegisterAndExtract = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");
    const pid = selectedProjectId || projects[0]?.id;
    if (!pid) {
      setError("Create or select a project first.");
      return;
    }
    try {
      const src = await apiRequest<ProjectSource>("/project-sources/", {
        method: "POST",
        body: JSON.stringify({ project: pid, source_path: sourcePath }),
      });
      const run = await apiRequest<ExtractionRun>("/extraction/", {
        method: "POST",
        body: JSON.stringify({ project: pid, project_source: src.id }),
      });
      setMessage(`Extraction ${run.status}: ${JSON.stringify(run.summary)}`);
      await Promise.all([loadData(), refreshContext()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed.");
    }
  };

  const handleComUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setComStatusMsg("");
    const pid = selectedProjectId || projects[0]?.id;
    if (!pid || !comFile) {
      setError("Select an active project and a COM snapshot JSON file.");
      return;
    }
    try {
      const text = await comFile.text();
      const parsed = JSON.parse(text);
      const res = await apiRequest<Record<string, unknown>>("/planswift/ingest/", {
        method: "POST",
        body: JSON.stringify({
          project_id: pid,
          agent_name: "WebManualUpload",
          auto_reconcile: true,
          payload: parsed,
        }),
      });
      setComStatusMsg(
        `COM snapshot ingested (${String(res.object_count)} objects). Reconciliation: ${JSON.stringify(res.reconciliation)}`
      );
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "COM snapshot upload failed.");
    }
  };

  return (
    <AppShell title="Source Import & Native Extraction">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6">
          <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Register Local PlanSwift Source</h2>
            <p className="text-xs text-slate-500">
              Streams native archive structure safely read-only (never sends 525+ MB archives through browser memory).
            </p>
            {error && <div className="rounded bg-rose-50 p-2 text-xs text-rose-700">{error}</div>}
            {message && <div className="rounded bg-emerald-50 p-2 text-xs text-emerald-800">{message}</div>}

            <form onSubmit={handleRegisterAndExtract} className="space-y-3">
              <input
                type="text"
                value={sourcePath}
                onChange={(e) => setSourcePath(e.target.value)}
                placeholder="Leave blank for PLANSWIFT_SOURCE_PATH or enter local path"
                className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
              />
              <button type="submit" className="w-full rounded bg-blue-600 px-3 py-2 text-sm font-semibold text-white">
                Inspect &amp; Run Native Extraction
              </button>
            </form>

            {comEnv && (
              <div className="rounded border border-slate-200 bg-slate-50 p-3 text-xs">
                <div className="font-semibold text-slate-800">Host PlanSwift COM Status</div>
                <div className="mt-1 text-slate-600">{String(comEnv.reason || "")}</div>
              </div>
            )}
          </div>

          <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Upload COM Snapshot JSON</h2>
            <p className="text-xs text-slate-500">
              Upload <code>com_snapshot.json</code> generated by <code>VortexenPlanSwiftConnector.exe</code> to resolve
              runtime formulas (<code>[!PageWidth]</code>, <code>[!PageHeight]</code>, <code>[Takeoff]</code>) as{" "}
              <code>computed_by_planswift</code>.
            </p>
            {comStatusMsg && <div className="rounded bg-teal-50 p-2 text-xs text-teal-800">{comStatusMsg}</div>}
            <form onSubmit={handleComUpload} className="space-y-3">
              <input
                type="file"
                accept=".json,application/json"
                onChange={(e) => setComFile(e.target.files?.[0] || null)}
                className="w-full text-xs text-slate-700"
              />
              <button
                type="submit"
                disabled={!comFile}
                className="w-full rounded border border-teal-600 bg-teal-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Ingest &amp; Reconcile COM Snapshot
              </button>
            </form>
          </div>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-900">Registered Source Packages</h2>
            <div className="space-y-2 text-xs">
              {sources.map((s) => (
                <div key={s.id} className="rounded border border-slate-100 p-3">
                  <div className="font-semibold">{s.source_name}</div>
                  <div className="font-mono text-[11px] text-slate-500">
                    Format: {s.container_format} | Magic: {s.magic_bytes_hex} | Size:{" "}
                    {(s.file_size_bytes / (1024 * 1024)).toFixed(2)} MiB
                  </div>
                  <div className="truncate font-mono text-[11px] text-slate-400">SHA-256: {s.source_sha256}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-900">Extraction Runs &amp; Stage Checkpoints</h2>
            <div className="space-y-3">
              {runs.map((r) => (
                <div key={r.id} className="rounded border border-slate-200 p-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{r.project_name}</span>
                    <span className="rounded bg-blue-50 px-2 py-0.5 font-mono font-semibold text-blue-700">
                      {r.status} ({r.progress_pct}%)
                    </span>
                  </div>
                  <div className="mt-1 text-slate-500">
                    Duration: {r.duration_seconds}s | Peak RAM: {r.peak_memory_mb} MB | Adapter: {r.adapter_used}
                  </div>
                  {r.events.length > 0 && (
                    <div className="mt-2 max-h-28 overflow-y-auto rounded bg-slate-50 p-2 font-mono text-[11px]">
                      {r.events.map((ev) => (
                        <div key={ev.id}>
                          [{ev.progress_pct}%] {ev.stage}: {ev.message}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
