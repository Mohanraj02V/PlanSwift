"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest, uploadProjectZipWithProgress } from "@/services/api-client/client";
import type { ExtractionRun, PaginatedResponse, ProjectSource } from "@/types/api";

const ALLOWED_EXTENSIONS = [".zip", ".swiftjob", ".swift", ".xml", ".dxf", ".ifc"];

function detectUiFormatLabel(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".dxf")) return "DXF CAD (ezdxf)";
  if (lower.endsWith(".ifc")) return "IFC BIM (IfcOpenShell)";
  if (lower.endsWith(".xml")) return "PlanSwift Native XML";
  if (lower.endsWith(".zip")) return "PlanSwift ZIP or DXF/IFC Bundle";
  return "PlanSwift ZIP / SwiftJob";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default function ExtractionPage() {
  const { user, projects, selectedProjectId, refreshContext } = useProjectContext();
  const canUpload = Boolean(
    user?.is_admin || user?.primary_role === "owner" || user?.primary_role === "estimator"
  );
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [autoExtract, setAutoExtract] = useState(true);
  const [extractGeometry, setExtractGeometry] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [sourcePath, setSourcePath] = useState("");
  const [sources, setSources] = useState<ProjectSource[]>([]);
  const [runs, setRuns] = useState<ExtractionRun[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadData = async () => {
    try {
      const q = selectedProjectId ? `?project=${selectedProjectId}` : "";
      const [srcRes, runRes] = await Promise.all([
        apiRequest<PaginatedResponse<ProjectSource>>(`/project-sources/${q}`),
        apiRequest<PaginatedResponse<ExtractionRun>>(`/extraction/${q}`),
      ]);
      setSources(srcRes.results || []);
      setRuns(runRes.results || []);
    } catch {
      // Ignore until signed in
    }
  };

  useEffect(() => {
    loadData();
  }, [selectedProjectId]);

  const validateAndSelectFile = (file: File | null) => {
    setError("");
    setMessage("");
    if (!file) {
      setSelectedFile(null);
      return;
    }
    const lower = file.name.toLowerCase();
    const okExt = ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext));
    if (!okExt) {
      setError(`Unsupported file '${file.name}'. Please upload a .zip, .SwiftJob, .xml, .dxf, or .ifc file.`);
      return;
    }
    if (file.size === 0) {
      setError(`File '${file.name}' is empty (0 bytes).`);
      return;
    }
    setSelectedFile(file);
  };

  const handleZipUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setMessage("");
    const pid = selectedProjectId || projects[0]?.id;
    if (!pid) {
      setError("Create or select a project first.");
      return;
    }
    if (!selectedFile) {
      setError("Select or drop a PlanSwift (.zip/.SwiftJob/.xml), DXF (.dxf), or IFC (.ifc) file first.");
      return;
    }
    setUploading(true);
    setUploadPct(0);
    try {
      const res = await uploadProjectZipWithProgress(
        pid,
        selectedFile,
        autoExtract,
        (pct) => setUploadPct(pct),
        extractGeometry
      );
      if (res.bundle) {
        const skippedNote =
          res.skipped_files && res.skipped_files.length > 0
            ? ` (${res.skipped_files.length} skipped: ${res.skipped_files.map((s) => s.name).join(", ")})`
            : "";
        setMessage(
          `Processed bundle '${res.bundle_name || selectedFile.name}': extracted ${res.processed_count ?? res.sources?.length ?? 1} CAD/BIM file(s)${skippedNote}.`
        );
      } else {
        const runStatus = res.extraction_run ? ` | Extraction: ${res.extraction_run.status}` : "";
        setMessage(`Uploaded '${res.source.source_name}' (${formatBytes(res.source.file_size_bytes)})${runStatus}`);
      }
      setSelectedFile(null);
      await Promise.all([loadData(), refreshContext()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "File upload failed.");
    } finally {
      setUploading(false);
    }
  };

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

  const handleTriggerRun = async (source: ProjectSource) => {
    setError("");
    setMessage("");
    try {
      const run = await apiRequest<ExtractionRun>("/extraction/", {
        method: "POST",
        body: JSON.stringify({ project: source.project, project_source: source.id }),
      });
      setMessage(`Triggered standalone extraction (${run.status})`);
      await Promise.all([loadData(), refreshContext()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed.");
    }
  };

  return (
    <AppShell title="Standalone PlanSwift, DXF & IFC Extraction">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6">
          {!canUpload ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">
              Your role (<b>{user?.primary_role || "viewer"}</b>) has read-only access. Uploading files or running extractions requires Estimator or Admin privileges.
            </div>
          ) : (
          <>
          <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Upload PlanSwift / DXF / IFC File</h2>
            <p className="text-xs text-slate-500">
              100% standalone server-side extraction via native XML, ezdxf, and IfcOpenShell. Zero AutoCAD, Revit, PlanSwift, or OCR required.
            </p>
            {error && <div className="rounded bg-rose-50 p-2 text-xs text-rose-700">{error}</div>}
            {message && <div className="rounded bg-emerald-50 p-2 text-xs text-emerald-800">{message}</div>}

            <form onSubmit={handleZipUpload} className="space-y-3">
              <div
                onDragOver={(ev) => {
                  ev.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(ev) => {
                  ev.preventDefault();
                  setDragActive(false);
                  validateAndSelectFile(ev.dataTransfer.files?.[0] || null);
                }}
                className={`rounded-lg border-2 border-dashed p-5 text-center transition ${
                  dragActive ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-slate-50"
                }`}
              >
                <p className="text-xs font-medium text-slate-700">
                  Drag &amp; drop a <code>.zip</code>, <code>.SwiftJob</code>, <code>.dxf</code>, or <code>.ifc</code> file here
                </p>
                <input
                  type="file"
                  accept=".zip,.SwiftJob,.swift,.xml,.dxf,.ifc"
                  onChange={(e) => validateAndSelectFile(e.target.files?.[0] || null)}
                  className="mt-3 block w-full text-xs text-slate-600"
                />
                {selectedFile && (
                  <div className="mt-2 rounded bg-white px-2.5 py-1.5 text-left text-xs text-slate-800 shadow-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold">{selectedFile.name}</span>
                      <span className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-blue-700">
                        {detectUiFormatLabel(selectedFile.name)}
                      </span>
                    </div>
                    <div className="font-mono text-[11px] text-slate-500">{formatBytes(selectedFile.size)}</div>
                  </div>
                )}
              </div>

              <label className="flex items-center gap-2 text-xs text-slate-700">
                <input
                  type="checkbox"
                  checked={autoExtract}
                  onChange={(e) => setAutoExtract(e.target.checked)}
                />
                Start standalone extraction &amp; calculations automatically
              </label>

              {(selectedFile?.name.toLowerCase().endsWith(".ifc") || selectedFile?.name.toLowerCase().endsWith(".zip")) && (
                <label className="flex items-center gap-2 rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
                  <input
                    type="checkbox"
                    checked={extractGeometry}
                    onChange={(e) => setExtractGeometry(e.target.checked)}
                  />
                  <span>
                    Enable 3D IFC geometry iterator for IFC files (computes BBox, surface area &amp; watertight volume; slower than property-only mode)
                  </span>
                </label>
              )}

              {uploadPct !== null && uploading && (
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px] font-mono text-slate-600">
                    <span>Uploading &amp; streaming archive...</span>
                    <span>{uploadPct}%</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded bg-slate-200">
                    <div className="h-full bg-blue-600 transition-all" style={{ width: `${uploadPct}%` }} />
                  </div>
                </div>
              )}

              <button
                type="submit"
                disabled={!selectedFile || uploading}
                className="w-full rounded bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {uploading ? `Uploading (${uploadPct ?? 0}%)...` : "Upload & Extract Project"}
              </button>
            </form>
          </div>

          <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Import Pre-Staged Server Archive</h2>
            <p className="text-xs text-slate-500">
              Register a read-only package inside configured server source roots without browser transfer.
            </p>
            <form onSubmit={handleRegisterAndExtract} className="space-y-3">
              <input
                type="text"
                value={sourcePath}
                onChange={(e) => setSourcePath(e.target.value)}
                placeholder="Authorized server source path or blank for default"
                className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
              />
              <button type="submit" className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                Inspect &amp; Extract Staged Archive
              </button>
            </form>
          </div>
          </>
          )}
        </div>

        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold text-slate-900">Uploaded &amp; Registered Packages</h2>
            <div className="space-y-2 text-xs">
              {sources.map((s) => (
                <div key={s.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-100 p-3">
                  <div>
                    <div className="font-semibold text-slate-900">{s.source_name}</div>
                    <div className="font-mono text-[11px] text-slate-500">
                      {s.source_kind} | {s.container_format} | {formatBytes(s.file_size_bytes)}
                    </div>
                    <div className="truncate font-mono text-[11px] text-slate-400">SHA-256: {s.source_sha256}</div>
                  </div>
                  {canUpload && (
                    <button
                      type="button"
                      onClick={() => handleTriggerRun(s)}
                      className="rounded border border-blue-600 px-2.5 py-1 text-xs font-medium text-blue-700 hover:bg-blue-50"
                    >
                      Re-Run Extraction
                    </button>
                  )}
                </div>
              ))}
              {sources.length === 0 && <p className="text-slate-500">No PlanSwift ZIP packages uploaded yet.</p>}
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
                    Duration: {r.duration_seconds}s | Peak Heap: {r.peak_memory_mb} MB
                    {r.peak_rss_mb ? ` | Peak RSS: ${r.peak_rss_mb} MB` : ""} | Adapter: {r.adapter_used}
                  </div>
                  {r.summary && Object.keys(r.summary).length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-600">
                      {"entities_extracted" in r.summary && Number(r.summary.entities_extracted) > 0 && (
                        <span>Entities: <b>{String(r.summary.entities_extracted)}</b></span>
                      )}
                      {"layers_extracted" in r.summary && Number(r.summary.layers_extracted) > 0 && (
                        <span>Layers: <b>{String(r.summary.layers_extracted)}</b></span>
                      )}
                      {"blocks_extracted" in r.summary && Number(r.summary.blocks_extracted) > 0 && (
                        <span>Blocks: <b>{String(r.summary.blocks_extracted)}</b></span>
                      )}
                      {"ifc_elements_extracted" in r.summary && Number(r.summary.ifc_elements_extracted) > 0 && (
                        <span>IFC Elements: <b>{String(r.summary.ifc_elements_extracted)}</b></span>
                      )}
                      {"unsupported_objects_count" in r.summary && Number(r.summary.unsupported_objects_count) > 0 && (
                        <span className="text-orange-700">Unsupported: <b>{String(r.summary.unsupported_objects_count)}</b></span>
                      )}
                      {"error" in r.summary && Boolean(r.summary.error) && (
                        <span className="text-rose-700">Error: {String(r.summary.error)}</span>
                      )}
                    </div>
                  )}
                  {r.events.length > 0 && (
                    <div className="mt-2 max-h-36 overflow-y-auto rounded bg-slate-50 p-2 font-mono text-[11px]">
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
