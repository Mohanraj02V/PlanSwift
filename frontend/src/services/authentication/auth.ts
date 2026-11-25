import { API_BASE_URL } from "@/services/api-client/client";

export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const cookies = document.cookie ? document.cookie.split(";") : [];
  for (const raw of cookies) {
    const idx = raw.indexOf("=");
    if (idx === -1) continue;
    const name = raw.slice(0, idx).trim();
    if (name === "csrftoken") {
      return decodeURIComponent(raw.slice(idx + 1).trim());
    }
  }
  return null;
}

let csrfPromise: Promise<string | null> | null = null;

export async function ensureCsrfCookie(): Promise<string | null> {
  const existing = getCsrfToken();
  if (existing) return existing;
  if (csrfPromise) return csrfPromise;
  csrfPromise = (async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/auth/csrf/`, {
        method: "GET",
        credentials: "include",
      });
      if (!resp.ok) return null;
      const data = await resp.json().catch(() => ({}));
      return getCsrfToken() || (typeof data?.csrfToken === "string" ? data.csrfToken : null);
    } catch {
      return null;
    } finally {
      csrfPromise = null;
    }
  })();
  return csrfPromise;
}
