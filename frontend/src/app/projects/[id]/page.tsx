"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { apiRequest, downloadExportFile } from "@/services/api-client/client";
import type { PaginatedResponse, Project } from "@/types/api";

interface PageRow {
  id: string;
  native_guid: string;
  name: string;
  page_type: string;
  scale_units: string;
  tiff_archive_path: string;
  tiff_size_bytes: number | null;
  section_count: number;
}

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [pages, setPages] = useState<PageRow[]>([]);

  useEffect(() => {
    if (!params.id) return;
    apiRequest<Project>(`/projects/${params.id}/`).then(setProject).catch(() => {});
    apiRequest<PaginatedResponse<PageRow>>(`/projects/${params.id}/pages/`)
      .then((d) => setPages(d.results || []))
      .catch(() => {});
  }, [params.id]);

  const handleExport = async (fmt: string) => {
    if (!params.id) return;
    const blob = await downloadExportFile(params.id, fmt);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project?.name || "project"}.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AppShell title={project ? `Project: ${project.name}` : "Project Details"}>
      {project && (
        <div className="space-y-6">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold">{project.name}</h2>
                <p className="font-mono text-xs text-slate-500">
                  GUID: {project.native_guid || "—"} | SHA-256:{" "}
                  {project.current_version?.source_sha256 || "—"}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {["json", "jsonl", "csv", "xlsx", "geojson"].map((fmt) => (
                  <button
                    key={fmt}
                    type="button"
                    onClick={() => handleExport(fmt)}
                    className="rounded border border-slate-300 bg-slate-50 px-2.5 py-1 text-xs font-semibold uppercase hover:bg-slate-100"
                  >
                    Export {fmt}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 font-semibold text-slate-600">
                <tr>
                  <th className="px-3 py-2">Page Name</th>
                  <th className="px-3 py-2">Native GUID</th>
                  <th className="px-3 py-2">Scale Units</th>
                  <th className="px-3 py-2">Matched Archive TIFF Asset</th>
                  <th className="px-3 py-2">Sections</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {pages.map((pg) => (
                  <tr key={pg.id}>
                    <td className="px-3 py-2 font-medium">{pg.name}</td>
                    <td className="px-3 py-2 font-mono text-[11px]">{pg.native_guid}</td>
                    <td className="px-3 py-2">{pg.scale_units || "—"}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-600">{pg.tiff_archive_path || "—"}</td>
                    <td className="px-3 py-2 font-mono">{pg.section_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </AppShell>
  );
}
