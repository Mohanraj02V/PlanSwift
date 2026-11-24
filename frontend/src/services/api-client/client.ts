import { clearAuthTokens, getAccessToken, getRefreshToken, setAuthTokens } from "@/services/authentication/auth";

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

async function tryRefreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  try {
    const resp = await fetch(`${API_BASE_URL}/auth/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!resp.ok) {
      clearAuthTokens();
      return null;
    }
    const data = await resp.json();
    if (data.access) {
      setAuthTokens(data.access, data.refresh);
      return data.access as string;
    }
    return null;
  } catch {
    return null;
  }
}

export async function apiRequest<T>(path: string, options: RequestInit = {}, retryOn401 = true): Promise<T> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (resp.status === 401 && retryOn401 && !path.startsWith("/auth/")) {
    const newAccess = await tryRefreshAccessToken();
    if (newAccess) {
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
  const token = getAccessToken();
  const resp = await fetch(`${API_BASE_URL}/exports/${projectId}/?export_format=${encodeURIComponent(exportFormat)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) {
    throw new ApiClientError(`Export failed (${resp.status})`, resp.status);
  }
  return resp.blob();
}

export interface ZipUploadResult {
  source: import("@/types/api").ProjectSource;
  extraction_run: import("@/types/api").ExtractionRun | null;
}

export function uploadProjectZipWithProgress(
  projectId: string,
  file: File,
  autoExtract: boolean,
  onProgress: (pct: number) => void
): Promise<ZipUploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/project-sources/upload/`);
    const token = getAccessToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
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
    xhr.onerror = () => reject(new ApiClientError("Network error during ZIP upload.", 0));
    const form = new FormData();
    form.append("project", projectId);
    form.append("auto_extract", autoExtract ? "true" : "false");
    form.append("file", file);
    xhr.send(form);
  });
}
