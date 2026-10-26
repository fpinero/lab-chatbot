import type { components } from "../generated/api";

export type LoginInfo = components["schemas"]["LoginInfo"];
export type SessionInfo = components["schemas"]["SessionInfo"];
type PreviewResult = components["schemas"]["PreviewResult"];
let csrfToken = "";

export class ApiError extends Error {
  constructor(public status: number) {
    super("request_failed");
  }
}

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) throw new ApiError(response.status);
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export function loginInfo() {
  return request<LoginInfo>("/auth/login");
}
export async function session() {
  const result = await request<SessionInfo>("/auth/session");
  csrfToken = result.csrf_token;
  return result;
}
export async function login(password: string, code: string) {
  const result = await request<SessionInfo>("/auth/login", "POST", {
    password,
    code,
  });
  csrfToken = result.csrf_token;
  return result;
}
export async function logout() {
  await request<void>("/auth/logout", "POST");
  csrfToken = "";
}
export function preview(prompt: string) {
  return request<PreviewResult>("/dev/preview", "POST", { prompt });
}
