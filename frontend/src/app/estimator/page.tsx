"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Box,
  CheckCircle2,
  FileSpreadsheet,
  Layers,
  Lock,
  Play,
  RefreshCw,
  Search,
  UploadCloud,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest, uploadProjectZipWithProgress } from "@/services/api-client/client";
import type {
  BIMElementRecord,
  CADBlockRecord,
  CADDocumentRecord,
  CADEntityRecord,
  CADLayerRecord,
  ExtractionRun,
  MeasurementRecord,
  PaginatedResponse,
  ProjectObject,
  ProjectSource,
  ValidationResult,
} from "@/types/api";

const ALLOWED_EXTENSIONS = [".zip", ".swiftjob", ".swift", ".xml", ".dxf", ".ifc"];

type WorkspaceTab = "files" | "planswift" | "dxf" | "ifc" | "validation";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default function EstimatorWorkspacePage() {
  const { user, role, capabilities, projects, selectedProjectId, selectedProject, refreshContext } =
    useProjectContext();

  const [tab, setTab] = useState<WorkspaceTab>("files");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [autoExtract, setAutoExtract] = useState(true);
  const [extractGeometry, setExtractGeometry] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [triggeringId, setTriggeringId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [searchText, setSearchText] = useState("");

  // Extracted read-only workspace datasets
  const [loadingData, setLoadingData] = useState(false);
  const [sources, setSources] = useState<ProjectSource[]>([]);
  const [runs, setRuns] = useState<ExtractionRun[]>([]);
  const [objects, setObjects] = useState<ProjectObject[]>([]);
  const [measurements, setMeasurements] = useState<MeasurementRecord[]>([]);
  const [cadDocs, setCadDocs] = useState<CADDocumentRecord[]>([]);
  const [cadLayers, setCadLayers] = useState<CADLayerRecord[]>([]);
  const [cadBlocks, setCadBlocks] = useState<CADBlockRecord[]>([]);
  const [cadEntities, setCadEntities] = useState<CADEntityRecord[]>([]);
  const [bimElements, setBimElements] = useState<BIMElementRecord[]>([]);
  const [validations, setValidations] = useState<ValidationResult[]>([]);
  const [unsupportedObjects, setUnsupportedObjects] = useState<ProjectObject[]>([]);

  const loadWorkspaceData = useCallback(async () => {
    if (!user || !selectedProjectId) return;
    setLoadingData(true);
    try {
      const qProj = `?project=${selectedProjectId}`;
      const qVerProj = `?project_version__project=${selectedProjectId}`;
      const qCadProj = `?cad_document__project_version__project=${selectedProjectId}`;

      const [
        srcRes,
        runRes,
        objRes,
        measRes,
        docRes,
        lyrRes,
        blkRes,
        entRes,
        bimRes,
        valRes,
        unsupRes,
      ] = await Promise.all([
        apiRequest<PaginatedResponse<ProjectSource>>(`/project-sources/${qProj}`),
        apiRequest<PaginatedResponse<ExtractionRun>>(`/extraction/${qProj}`),
        apiRequest<PaginatedResponse<ProjectObject>>(`/objects/${qVerProj}&page_size=100`),
        apiRequest<PaginatedResponse<MeasurementRecord>>(`/measurements/${qVerProj}&page_size=100`),
        apiRequest<PaginatedResponse<CADDocumentRecord>>(`/cad-bim/documents/${qVerProj}`),
        apiRequest<PaginatedResponse<CADLayerRecord>>(`/cad-bim/layers/${qCadProj}&page_size=100`),
        apiRequest<PaginatedResponse<CADBlockRecord>>(`/cad-bim/blocks/${qCadProj}&page_size=100`),
        apiRequest<PaginatedResponse<CADEntityRecord>>(`/cad-bim/entities/${qCadProj}&page_size=100`),
        apiRequest<PaginatedResponse<BIMElementRecord>>(`/cad-bim/elements/${qCadProj}&page_size=100`),
        apiRequest<PaginatedResponse<ValidationResult>>(`/validation/${qVerProj}`),
        apiRequest<PaginatedResponse<ProjectObject>>(`/objects/unsupported/${qVerProj}&page_size=50`),
      ]);

      setSources(srcRes.results || []);
      setRuns(runRes.results || []);
      setObjects(objRes.results || []);
      setMeasurements(measRes.results || []);
      setCadDocs(docRes.results || []);
      setCadLayers(lyrRes.results || []);
      setCadBlocks(blkRes.results || []);
      setCadEntities(entRes.results || []);
      setBimElements(bimRes.results || []);
      setValidations(valRes.results || []);
      setUnsupportedObjects(unsupRes.results || []);
    } catch {
      // Errors surface gracefully on individual actions
    } finally {
      setLoadingData(false);
    }
  }, [user, selectedProjectId]);

  useEffect(() => {
    loadWorkspaceData();
  }, [loadWorkspaceData]);

  const validateFile = (file: File | null) => {
    setError("");
    setMessage("");
    if (!file) {
      setSelectedFile(null);
      return;
    }
    const lower = file.name.toLowerCase();
    if (!ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      setError(`Unsupported file '${file.name}'. Allowed: .SwiftJob.zip, .zip, .xml, .dxf, .ifc.`);
      return;
    }
    if (file.size === 0) {
      setError(`File '${file.name}' is empty (0 bytes).`);
      return;
    }
    setSelectedFile(file);
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!capabilities.can_upload_source) return;
    setError("");
    setMessage("");
    const pid = selectedProjectId || projects[0]?.id;
    if (!pid) {
      setError("Select an organization project first (ask your Admin if no projects exist).");
      return;
    }
    if (!selectedFile) {
      setError("Select or drop a supported PlanSwift, DXF, or IFC file.");
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
        setMessage(
          `Processed bundle '${res.bundle_name || selectedFile.name}': ${res.processed_count ?? res.sources?.length ?? 0} file(s) queued/extracted.`
        );
      } else {
        setMessage(
          `Uploaded '${res.source.source_name}' (${formatBytes(res.source.file_size_bytes)})` +
            (res.extraction_run ? ` — Extraction ${res.extraction_run.status}` : "")
        );
      }
      setSelectedFile(null);
      await Promise.all([loadWorkspaceData(), refreshContext()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const handleRunExtraction = async (src: ProjectSource) => {
    if (!capabilities.can_start_extraction) return;
    setError("");
    setMessage("");
    setTriggeringId(src.id);
    try {
      const run = await apiRequest<ExtractionRun>("/extraction/", {
        method: "POST",
        body: JSON.stringify({ project: src.project, project_source: src.id }),
      });
      setMessage(`Extraction run completed/queued for '${src.source_name}': ${run.status}`);
      await Promise.all([loadWorkspaceData(), refreshContext()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction start failed.");
    } finally {
      setTriggeringId(null);
    }
  };

  const latestRun = runs[0];
  const latestVal = validations[0];
  const qLower = searchText.trim().toLowerCase();

  const filteredObjects = useMemo(
    () =>
      !qLower
        ? objects
        : objects.filter(
            (o) =>
              o.name.toLowerCase().includes(qLower) ||
              o.native_class.toLowerCase().includes(qLower) ||
              o.native_guid.toLowerCase().includes(qLower)
          ),
    [objects, qLower]
  );

  const filteredEntities = useMemo(
    () =>
      !qLower
        ? cadEntities
        : cadEntities.filter(
            (e) =>
              e.entity_type.toLowerCase().includes(qLower) ||
              e.layer_name.toLowerCase().includes(qLower) ||
              e.handle.toLowerCase().includes(qLower)
          ),
    [cadEntities, qLower]
  );

  const filteredBim = useMemo(
    () =>
      !qLower
        ? bimElements
        : bimElements.filter(
            (b) =>
              b.ifc_class.toLowerCase().includes(qLower) ||
              b.name.toLowerCase().includes(qLower) ||
              b.storey_name.toLowerCase().includes(qLower)
          ),
    [bimElements, qLower]
  );

  return (
    <AppShell title="Vortexen Estimator Workspace">
      {/* Project Header & Role Scope Banner */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[#e2e8f0] bg-white p-4 shadow-xs">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[#0052cc]">
              {selectedProject?.organization_name || "Organization Workspace"}
            </span>
            {selectedProject?.source_format && (
              <span className="rounded bg-[#eff6ff] px-2 py-0.5 font-mono text-[10px] font-semibold uppercase text-[#0052cc]">
                {selectedProject.source_format}
              </span>
            )}
          </div>
          <h2 className="mt-1 text-lg font-extrabold text-[#0f172a]">
            {selectedProject ? selectedProject.name : "No Project Selected"}
          </h2>
          <p className="mt-0.5 font-mono text-[11px] text-[#64748b]">
            {selectedProject?.current_version?.deterministic_digest_sha256
              ? `Version v${selectedProject.current_version.version_number} • SHA-256: ${selectedProject.current_version.deterministic_digest_sha256.slice(0, 16)}...`
              : "Upload or select a project to inspect extracted quantities and model records."}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {role === "user" ? (
            <div className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-[#475569]">
              <Lock className="h-3.5 w-3.5" /> Read-Only User Access
            </div>
          ) : (
            <div className="inline-flex items-center gap-1.5 rounded-lg border border-[#0052cc]/25 bg-[#eff6ff] px-3 py-1.5 text-xs font-semibold text-[#0052cc]">
              <UploadCloud className="h-3.5 w-3.5" />
              {role === "admin" ? "Admin Preview (Full Control in Admin Modules)" : "Estimator Upload & Extraction Mode"}
            </div>
          )}
          <button
            type="button"
            onClick={() => loadWorkspaceData()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#e2e8f0] bg-white px-3 py-1.5 text-xs font-semibold text-[#334155] hover:bg-[#f1f5f9]"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loadingData ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      {/* KPI Summary Strip */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-[#e2e8f0] bg-white p-4">
          <div className="flex items-center justify-between text-xs font-semibold text-[#64748b]">
            <span>Source Files &amp; Runs</span>
            <UploadCloud className="h-4 w-4 text-[#0052cc]" />
          </div>
          <div className="mt-1.5 font-mono text-2xl font-extrabold text-[#0f172a]">{sources.length} files</div>
          <div className="mt-1 text-xs text-[#64748b]">
            Latest Run: <b>{latestRun ? `${latestRun.status} (${latestRun.duration_seconds}s)` : "None yet"}</b>
          </div>
        </div>

        <div className="rounded-xl border border-[#e2e8f0] bg-white p-4">
          <div className="flex items-center justify-between text-xs font-semibold text-[#64748b]">
            <span>PlanSwift Takeoff Items</span>
            <Box className="h-4 w-4 text-[#0052cc]" />
          </div>
          <div className="mt-1.5 font-mono text-2xl font-extrabold text-[#0f172a]">
            {objects.length.toLocaleString()}
          </div>
          <div className="mt-1 text-xs text-[#64748b]">{measurements.length} extracted measurement rows</div>
        </div>

        <div className="rounded-xl border border-[#e2e8f0] bg-white p-4">
          <div className="flex items-center justify-between text-xs font-semibold text-[#64748b]">
            <span>CAD &amp; BIM Records</span>
            <Layers className="h-4 w-4 text-[#29a9ea]" />
          </div>
          <div className="mt-1.5 font-mono text-2xl font-extrabold text-[#0f172a]">
            {(cadEntities.length + bimElements.length).toLocaleString()}
          </div>
          <div className="mt-1 text-xs text-[#64748b]">
            {cadEntities.length} DXF entities • {bimElements.length} IFC elements
          </div>
        </div>

        <div className="rounded-xl border border-[#e2e8f0] bg-white p-4">
          <div className="flex items-center justify-between text-xs font-semibold text-[#64748b]">
            <span>Verified Accuracy</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-1.5 font-mono text-2xl font-extrabold text-emerald-700">
            {latestVal ? `${latestVal.overall_verified_accuracy_pct}%` : "—"}
          </div>
          <div className="mt-1 text-xs text-[#64748b]">
            {latestVal
              ? `${latestVal.unknown_class_objects} unsupported • ${latestVal.unresolved_formulas} unresolved`
              : "Awaiting validation"}
          </div>
        </div>
      </div>

      {/* Main Content Grid: Upload Column (Estimator/Admin only) + Results Explorer */}
      <div className={`grid grid-cols-1 gap-6 ${capabilities.can_upload_source ? "lg:grid-cols-3" : ""}`}>
        {capabilities.can_upload_source && (
          <div className="space-y-4">
            <div className="rounded-xl border border-[#e2e8f0] bg-white p-5">
              <div className="flex items-center gap-2">
                <UploadCloud className="h-4 w-4 text-[#0052cc]" />
                <h3 className="text-sm font-bold text-[#0f172a]">Upload &amp; Extract Drawing</h3>
              </div>
              <p className="mt-1 text-xs text-[#64748b]">
                Upload PlanSwift (<code>.SwiftJob.zip</code>, <code>.zip</code>, <code>.xml</code>), AutoCAD (<code>.dxf</code>), or BIM (<code>.ifc</code>) packages directly into the selected project.
              </p>

              {error && (
                <div role="alert" className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-2.5 text-xs text-rose-700">
                  {error}
                </div>
              )}
              {message && (
                <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-2.5 text-xs text-emerald-800">
                  {message}
                </div>
              )}

              <form onSubmit={handleUpload} className="mt-4 space-y-3">
                <div
                  onDragOver={(ev) => {
                    ev.preventDefault();
                    setDragActive(true);
                  }}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={(ev) => {
                    ev.preventDefault();
                    setDragActive(false);
                    validateFile(ev.dataTransfer.files?.[0] || null);
                  }}
                  className={`rounded-xl border-2 border-dashed p-5 text-center transition ${
                    dragActive ? "border-[#0052cc] bg-[#eff6ff]" : "border-[#cbd5e1] bg-[#f8fafc]"
                  }`}
                >
                  <p className="text-xs font-semibold text-[#334155]">
                    Drag &amp; drop CAD / BIM / PlanSwift file here
                  </p>
                  <input
                    type="file"
                    aria-label="Upload project source file"
                    accept=".zip,.SwiftJob,.swift,.xml,.dxf,.ifc"
                    onChange={(e) => validateFile(e.target.files?.[0] || null)}
                    className="mt-3 block w-full text-xs text-[#475569]"
                  />
                  {selectedFile && (
                    <div className="mt-3 rounded-lg border border-[#e2e8f0] bg-white p-2.5 text-left text-xs">
                      <div className="truncate font-bold text-[#0f172a]">{selectedFile.name}</div>
                      <div className="font-mono text-[11px] text-[#64748b]">
                        {formatBytes(selectedFile.size)}
                      </div>
                    </div>
                  )}
                </div>

                <label className="flex items-center gap-2 text-xs font-medium text-[#334155]">
                  <input
                    type="checkbox"
                    checked={autoExtract}
                    onChange={(e) => setAutoExtract(e.target.checked)}
                  />
                  Start extraction &amp; calculations automatically
                </label>

                <label className="flex items-start gap-2 rounded-lg border border-[#e2e8f0] bg-[#f8fafc] p-2.5 text-xs text-[#475569]">
                  <input
                    type="checkbox"
                    checked={extractGeometry}
                    onChange={(e) => setExtractGeometry(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>Enable 3D IFC geometry iterator (surface area &amp; watertight volume)</span>
                </label>

                {uploading && uploadPct !== null && (
                  <div className="space-y-1">
                    <div className="flex justify-between font-mono text-[11px] text-[#475569]">
                      <span>Streaming upload...</span>
                      <span>{uploadPct}%</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                      <div className="h-full bg-[#0052cc] transition-all" style={{ width: `${uploadPct}%` }} />
                    </div>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={!selectedFile || uploading || !selectedProjectId}
                  className="w-full rounded-lg bg-[#0052cc] px-4 py-2.5 text-xs font-bold text-white transition hover:bg-[#003d99] disabled:opacity-50"
                >
                  {uploading ? `Uploading (${uploadPct ?? 0}%)...` : "Upload & Process File"}
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Extracted Results Explorer */}
        <div className={capabilities.can_upload_source ? "lg:col-span-2" : "w-full"}>
          <div className="rounded-xl border border-[#e2e8f0] bg-white">
            {/* Tabs + Search Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e2e8f0] px-4 py-3">
              <div className="flex flex-wrap gap-1.5">
                {[
                  { id: "files" as const, label: `Files & Runs (${sources.length})`, icon: Activity },
                  { id: "planswift" as const, label: `PlanSwift (${objects.length})`, icon: FileSpreadsheet },
                  { id: "dxf" as const, label: `DXF CAD (${cadEntities.length})`, icon: Layers },
                  { id: "ifc" as const, label: `IFC BIM (${bimElements.length})`, icon: Box },
                  { id: "validation" as const, label: `Validation (${validations.length})`, icon: AlertTriangle },
                ].map((t) => {
                  const Icon = t.icon;
                  const active = tab === t.id;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setTab(t.id)}
                      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        active
                          ? "bg-[#0052cc] text-white"
                          : "bg-[#f1f5f9] text-[#475569] hover:bg-slate-200"
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {t.label}
                    </button>
                  );
                })}
              </div>

              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
                <input
                  type="text"
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  placeholder="Filter extracted items..."
                  className="w-48 rounded-lg border border-[#cbd5e1] py-1.5 pl-8 pr-3 text-xs focus:border-[#0052cc] focus:outline-none sm:w-56"
                />
              </div>
            </div>

            <div className="p-4">
              {tab === "files" && (
                <div className="space-y-5">
                  <div>
                    <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-[#475569]">
                      Uploaded Project Files
                    </h4>
                    <div className="space-y-2">
                      {sources.map((s) => (
                        <div
                          key={s.id}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#e2e8f0] bg-[#fafbfd] p-3 text-xs"
                        >
                          <div className="min-w-0">
                            <div className="truncate font-bold text-[#0f172a]">{s.source_name}</div>
                            <div className="font-mono text-[11px] text-[#64748b]">
                              {s.source_format || s.container_format} • {formatBytes(s.file_size_bytes)} • SHA-256:{" "}
                              {s.source_sha256.slice(0, 12)}...
                            </div>
                          </div>
                          {capabilities.can_start_extraction && (
                            <button
                              type="button"
                              disabled={triggeringId === s.id}
                              onClick={() => handleRunExtraction(s)}
                              className="inline-flex items-center gap-1 rounded-md border border-[#0052cc] px-2.5 py-1 text-xs font-semibold text-[#0052cc] hover:bg-[#eff6ff] disabled:opacity-50"
                            >
                              <Play className="h-3 w-3" />
                              {triggeringId === s.id ? "Running..." : "Extract / Re-Run"}
                            </button>
                          )}
                        </div>
                      ))}
                      {sources.length === 0 && (
                        <p className="text-xs text-[#64748b]">No uploaded files for this project yet.</p>
                      )}
                    </div>
                  </div>

                  <div>
                    <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-[#475569]">
                      Extraction Runs &amp; Status
                    </h4>
                    <div className="space-y-2">
                      {runs.map((r) => (
                        <div key={r.id} className="rounded-lg border border-[#e2e8f0] p-3 text-xs">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-bold text-[#0f172a]">
                              {r.adapter_used || "Extraction Run"}
                            </span>
                            <span className="rounded-full bg-[#eff6ff] px-2.5 py-0.5 font-mono text-[11px] font-semibold text-[#0052cc]">
                              {r.status} ({r.progress_pct}%)
                            </span>
                          </div>
                          <div className="mt-1 font-mono text-[11px] text-[#64748b]">
                            Duration: {r.duration_seconds}s • Peak Memory: {r.peak_memory_mb} MB
                          </div>
                        </div>
                      ))}
                      {runs.length === 0 && (
                        <p className="text-xs text-[#64748b]">No extraction runs recorded yet.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {tab === "planswift" && (
                <div className="space-y-5">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-[#e2e8f0] text-left text-xs">
                      <thead className="bg-[#f8fafc] font-semibold text-[#475569]">
                        <tr>
                          <th className="px-3 py-2">Object</th>
                          <th className="px-3 py-2">Class</th>
                          <th className="px-3 py-2">Depth</th>
                          <th className="px-3 py-2">Properties</th>
                          <th className="px-3 py-2">Provenance</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#f1f5f9]">
                        {filteredObjects.slice(0, 60).map((o) => (
                          <tr key={o.id} className="hover:bg-[#fafbfd]">
                            <td className="px-3 py-2 font-semibold text-[#0f172a]">{o.name || "(unnamed)"}</td>
                            <td className="px-3 py-2 font-mono text-[11px] text-[#475569]">{o.native_class}</td>
                            <td className="px-3 py-2 font-mono text-[11px]">{o.depth}</td>
                            <td className="px-3 py-2 font-mono text-[11px]">{o.property_count}</td>
                            <td className="px-3 py-2">
                              <ProvenanceBadge status={o.provenance} />
                            </td>
                          </tr>
                        ))}
                        {filteredObjects.length === 0 && (
                          <tr>
                            <td colSpan={5} className="px-3 py-6 text-center text-[#64748b]">
                              No extracted PlanSwift objects match the filter.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {measurements.length > 0 && (
                    <div>
                      <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-[#475569]">
                        Extracted Measurements
                      </h4>
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-[#e2e8f0] text-left text-xs">
                          <thead className="bg-[#f8fafc] font-semibold text-[#475569]">
                            <tr>
                              <th className="px-3 py-2">Item</th>
                              <th className="px-3 py-2">Property</th>
                              <th className="px-3 py-2">Quantity</th>
                              <th className="px-3 py-2">Unit</th>
                              <th className="px-3 py-2">Status</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[#f1f5f9]">
                            {measurements.slice(0, 50).map((m) => (
                              <tr key={m.id}>
                                <td className="px-3 py-2 font-semibold text-[#0f172a]">{m.object_name}</td>
                                <td className="px-3 py-2 font-mono text-[11px]">{m.property_name}</td>
                                <td className="px-3 py-2 font-mono font-bold text-[#0052cc]">
                                  {m.calculated_quantity ?? m.reconstructed_quantity ?? m.derived_quantity ?? m.native_stored_value}
                                </td>
                                <td className="px-3 py-2 font-mono text-[11px]">{m.unit || "—"}</td>
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
                </div>
              )}

              {tab === "dxf" && (
                <div className="space-y-4 text-xs">
                  {cadDocs.filter((d) => d.source_format.startsWith("dxf")).length > 0 && (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                      {cadDocs
                        .filter((d) => d.source_format.startsWith("dxf"))
                        .map((d) => (
                          <div key={d.id} className="rounded-lg border border-[#e2e8f0] bg-[#fafbfd] p-3">
                            <div className="truncate font-bold text-[#0f172a]">{d.source_name}</div>
                            <div className="mt-1 font-mono text-[11px] text-[#64748b]">
                              {d.file_version} • Units: {d.source_units}
                            </div>
                            <div className="mt-1 font-mono text-[11px] text-[#0052cc]">
                              {d.entity_count} entities • {d.layer_count} layers • {d.block_count} blocks
                            </div>
                          </div>
                        ))}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2">
                    {cadLayers.slice(0, 12).map((l) => (
                      <span
                        key={l.id}
                        className="rounded border border-[#e2e8f0] bg-[#f8fafc] px-2 py-1 font-mono text-[11px]"
                      >
                        {l.name} ({l.entity_count})
                      </span>
                    ))}
                    {cadBlocks.slice(0, 6).map((b) => (
                      <span
                        key={b.id}
                        className="rounded border border-[#29a9ea]/30 bg-sky-50 px-2 py-1 font-mono text-[11px] text-sky-900"
                      >
                        BLK: {b.name}
                      </span>
                    ))}
                  </div>
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-[#e2e8f0] text-left text-xs">
                      <thead className="bg-[#f8fafc] font-semibold text-[#475569]">
                        <tr>
                          <th className="px-3 py-2">Handle</th>
                          <th className="px-3 py-2">Entity Type</th>
                          <th className="px-3 py-2">Layer</th>
                          <th className="px-3 py-2">Supported</th>
                          <th className="px-3 py-2">Provenance</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#f1f5f9]">
                        {filteredEntities.slice(0, 60).map((ent) => (
                          <tr key={ent.id}>
                            <td className="px-3 py-2 font-mono text-[11px]">{ent.handle}</td>
                            <td className="px-3 py-2 font-semibold text-[#0f172a]">{ent.entity_type}</td>
                            <td className="px-3 py-2 font-mono text-[11px]">{ent.layer_name}</td>
                            <td className="px-3 py-2">{ent.is_supported ? "Yes" : "Preserved Raw"}</td>
                            <td className="px-3 py-2">
                              <ProvenanceBadge status={ent.provenance} />
                            </td>
                          </tr>
                        ))}
                        {filteredEntities.length === 0 && (
                          <tr>
                            <td colSpan={5} className="px-3 py-6 text-center text-[#64748b]">
                              No DXF entities extracted for this project.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {tab === "ifc" && (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-[#e2e8f0] text-left text-xs">
                    <thead className="bg-[#f8fafc] font-semibold text-[#475569]">
                      <tr>
                        <th className="px-3 py-2">IFC Class</th>
                        <th className="px-3 py-2">Name</th>
                        <th className="px-3 py-2">Storey</th>
                        <th className="px-3 py-2">Qty Sets / 3D Geo</th>
                        <th className="px-3 py-2">Provenance</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#f1f5f9]">
                      {filteredBim.slice(0, 60).map((b) => (
                        <tr key={b.id}>
                          <td className="px-3 py-2 font-mono font-semibold text-[#0052cc]">{b.ifc_class}</td>
                          <td className="px-3 py-2 font-semibold text-[#0f172a]">{b.name || b.global_id}</td>
                          <td className="px-3 py-2 text-[#475569]">{b.storey_name || "—"}</td>
                          <td className="px-3 py-2 font-mono text-[11px]">
                            {b.quantity_sets_json.length} Qto • {b.geometry_summary_json?.status || "none"}
                          </td>
                          <td className="px-3 py-2">
                            <ProvenanceBadge status={b.provenance} />
                          </td>
                        </tr>
                      ))}
                      {filteredBim.length === 0 && (
                        <tr>
                          <td colSpan={5} className="px-3 py-6 text-center text-[#64748b]">
                            No IFC BIM elements extracted for this project.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}

              {tab === "validation" && (
                <div className="space-y-4 text-xs">
                  {latestVal ? (
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-[#e2e8f0] text-left text-xs">
                        <thead className="bg-[#f8fafc] font-semibold text-[#475569]">
                          <tr>
                            <th className="px-3 py-2">Check</th>
                            <th className="px-3 py-2">Category</th>
                            <th className="px-3 py-2">Discovered / Extracted</th>
                            <th className="px-3 py-2">Accuracy</th>
                            <th className="px-3 py-2">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#f1f5f9]">
                          {latestVal.checks_json.map((chk, idx) => (
                            <tr key={`${chk.check_name}-${idx}`}>
                              <td className="px-3 py-2 font-semibold text-[#0f172a]">{chk.check_name}</td>
                              <td className="px-3 py-2 font-mono text-[11px]">{chk.category}</td>
                              <td className="px-3 py-2 font-mono">
                                {chk.discovered_count} / {chk.extracted_count}
                              </td>
                              <td className="px-3 py-2 font-mono">
                                {chk.accuracy_pct !== null ? `${chk.accuracy_pct}%` : "—"}
                              </td>
                              <td className="px-3 py-2 font-mono font-semibold text-[#0052cc]">{chk.status}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-[#64748b]">No validation report available yet.</p>
                  )}

                  {unsupportedObjects.length > 0 && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <h4 className="font-bold text-amber-900">
                        Unsupported / Preserved Objects ({unsupportedObjects.length})
                      </h4>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {unsupportedObjects.slice(0, 20).map((u) => (
                          <span
                            key={u.id}
                            className="rounded border border-amber-300 bg-white px-2 py-0.5 font-mono text-[11px] text-amber-900"
                          >
                            {u.native_class}: {u.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
