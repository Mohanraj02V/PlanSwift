import { ensureCsrfCookie, getCsrfToken } from "@/services/authentication/auth";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000/api/v1";

export class ApiClientError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let inflightRefreshPromise: Promise<boolean> | null = null;

async function tryRefreshSession(): Promise<boolean> {
  if (inflightRefreshPromise) {
    return inflightRefreshPromise;
  }
  inflightRefreshPromise = (async () => {
    try {
      const csrf = (await ensureCsrfCookie()) || "";
      const resp = await fetch(`${API_BASE_URL}/auth/refresh/`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(csrf ? { "X-CSRFToken": csrf } : {}),
        },
        body: JSON.stringify({}),
      });
      return resp.ok;
    } catch {
      return false;
    } finally {
      inflightRefreshPromise = null;
    }
  })();
  return inflightRefreshPromise;
}

export async function apiRequest<T>(path: string, options: RequestInit = {}, retryOn401 = true): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };

  if (UNSAFE_METHODS.has(method)) {
    const csrf = (await ensureCsrfCookie()) || getCsrfToken();
    if (csrf) {
      headers["X-CSRFToken"] = csrf;
    }
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    method,
    credentials: "include",
    headers,
  });

  if (resp.status === 401 && retryOn401 && !path.startsWith("/auth/")) {
    const refreshed = await tryRefreshSession();
    if (refreshed) {
      return apiRequest<T>(path, options, false);
    }
  }

  if (!resp.ok) {
    let body: Record<string, unknown> = {};
    try {
      body = await resp.json();
    } catch {
      body = { detail: resp.statusText };
    }
    const detail = (body.error as Record<string, unknown> | undefined)?.detail ?? body.detail ?? resp.statusText;
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new ApiClientError(msg, resp.status, detail);
  }

  if (resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

export async function downloadExportFile(projectId: string, exportFormat: string): Promise<Blob> {
  let resp = await fetch(`${API_BASE_URL}/exports/${projectId}/?export_format=${encodeURIComponent(exportFormat)}`, {
    credentials: "include",
  });
  if (resp.status === 401) {
    const ok = await tryRefreshSession();
    if (ok) {
      resp = await fetch(`${API_BASE_URL}/exports/${projectId}/?export_format=${encodeURIComponent(exportFormat)}`, {
        credentials: "include",
      });
    }
  }
  if (!resp.ok) {
    throw new ApiClientError(`Export failed (${resp.status})`, resp.status);
  }
  return resp.blob();
}

export async function downloadEstimationDocument(
  sessionId: string,
  kind: "excel" | "pdf",
  quotationOverride?: Record<string, unknown>
): Promise<Blob> {
  const action = kind === "excel" ? "export-excel" : "export-pdf";
  const performFetch = async () => {
    const headers: Record<string, string> = {};
    if (quotationOverride) {
      headers["Content-Type"] = "application/json";
      const csrf = (await ensureCsrfCookie()) || getCsrfToken();
      if (csrf) headers["X-CSRFToken"] = csrf;
    }
    return fetch(`${API_BASE_URL}/estimation/sessions/${sessionId}/${action}/`, {
      method: quotationOverride ? "POST" : "GET",
      credentials: "include",
      headers,
      body: quotationOverride ? JSON.stringify({ quotation: quotationOverride }) : undefined,
    });
  };

  let resp = await performFetch();
  if (resp.status === 401) {
    const ok = await tryRefreshSession();
    if (ok) {
      resp = await performFetch();
    }
  }
  if (!resp.ok) {
    throw new ApiClientError(`Quotation ${kind.toUpperCase()} download failed (${resp.status})`, resp.status);
  }
  return resp.blob();
}

export interface ZipUploadResult {
  source: import("@/types/api").ProjectSource;
  extraction_run: import("@/types/api").ExtractionRun | null;
  bundle?: boolean;
  bundle_name?: string;
  processed_count?: number;
  skipped_files?: Array<{ name: string; reason: string }>;
  sources?: import("@/types/api").ProjectSource[];
  extraction_runs?: import("@/types/api").ExtractionRun[];
}

export async function uploadProjectZipWithProgress(
  projectId: string,
  file: File,
  autoExtract: boolean,
  onProgress: (pct: number) => void,
  extractGeometry = false
): Promise<ZipUploadResult> {
  const csrf = (await ensureCsrfCookie()) || getCsrfToken();
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/project-sources/upload/`);
    xhr.withCredentials = true;
    if (csrf) {
      xhr.setRequestHeader("X-CSRFToken", csrf);
    }
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable && ev.total > 0) {
        onProgress(Math.round((ev.loaded / ev.total) * 100));
      }
    };
    xhr.onload = () => {
      try {
        const parsed = JSON.parse(xhr.responseText || "{}");
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(parsed as ZipUploadResult);
        } else {
          const msg = parsed?.error?.detail ?? parsed?.detail ?? `Upload failed (${xhr.status})`;
          reject(new ApiClientError(typeof msg === "string" ? msg : JSON.stringify(msg), xhr.status, parsed));
        }
      } catch {
        reject(new ApiClientError(`Upload failed (${xhr.status})`, xhr.status));
      }
    };
    xhr.onerror = () => reject(new ApiClientError("Network error during upload.", 0));
    const form = new FormData();
    form.append("project", projectId);
    form.append("auto_extract", autoExtract ? "true" : "false");
    form.append("extract_geometry", extractGeometry ? "true" : "false");
    form.append("file", file);
    xhr.send(form);
  });
}
