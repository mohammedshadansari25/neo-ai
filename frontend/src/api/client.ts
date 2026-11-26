import type { components } from "./schema";

export type AuthRequest = components["schemas"]["AuthRequest"];
export type TokenResponse = components["schemas"]["TokenResponse"];
export type UserProfileResponse = components["schemas"]["UserProfileResponse"];
export type LogoutResponse = components["schemas"]["LogoutResponse"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  code: string;
  details: Array<Record<string, unknown>>;

  constructor(
    status: number,
    message: string,
    code = "api_error",
    details: Array<Record<string, unknown>> = [],
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let inMemoryToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export function setAccessToken(token: string | null): void {
  inMemoryToken = token;
}

export function getAccessToken(): string | null {
  return inMemoryToken;
}

async function parseErrorResponse(res: Response): Promise<ApiError> {
  try {
    const data = (await res.json()) as Partial<ErrorEnvelope>;
    if (data && data.error) {
      return new ApiError(
        res.status,
        data.error.message,
        data.error.code,
        data.error.details ?? [],
      );
    }
  } catch {
    // Fallback to HTTP status text
  }
  return new ApiError(res.status, res.statusText || "Request failed");
}

export async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) {
    return refreshInFlight;
  }

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        setAccessToken(null);
        return null;
      }
      const data = (await res.json()) as TokenResponse;
      setAccessToken(data.access_token);
      return data.access_token;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  retryOn401 = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (inMemoryToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${inMemoryToken}`);
  }
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (res.status === 401 && retryOn401 && !path.startsWith("/api/auth/")) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      headers.set("Authorization", `Bearer ${newToken}`);
      const retryRes = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        headers,
        credentials: "include",
      });
      if (!retryRes.ok) {
        throw await parseErrorResponse(retryRes);
      }
      return (await retryRes.json()) as T;
    }
  }

  if (!res.ok) {
    throw await parseErrorResponse(res);
  }

  return (await res.json()) as T;
}
