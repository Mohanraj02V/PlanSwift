const TOKEN_ACCESS_KEY = "vortexen_access_token";
const TOKEN_REFRESH_KEY = "vortexen_refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_REFRESH_KEY);
}

export function setAuthTokens(access: string, refresh?: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_ACCESS_KEY, access);
  if (refresh) {
    window.localStorage.setItem(TOKEN_REFRESH_KEY, refresh);
  }
}

export function clearAuthTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_ACCESS_KEY);
  window.localStorage.removeItem(TOKEN_REFRESH_KEY);
}
