import { copy } from "./copy";
import type { components } from "../generated/api";

export type LoginInfo = components["schemas"]["LoginInfo"];
export type SessionInfo = components["schemas"]["SessionInfo"];
type PreviewResult = components["schemas"]["PreviewResult"];
let csrfToken = "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string = copy.chatFailure,
  ) {
    super(message);
  }
}

export async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const multipart = body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      ...(multipart ? {} : { "Content-Type": "application/json" }),
      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
    },
    ...(body === undefined
      ? {}
      : { body: multipart ? body : JSON.stringify(body) }),
  });
  if (!response.ok) {
    let message: string = copy.chatFailure;
    try {
      const body = (await response.json()) as { error?: { message?: unknown } };
      if (typeof body.error?.message === "string") message = body.error.message;
    } catch {
      /* An interrupted response keeps the generic message. */
    }
    throw new ApiError(response.status, message);
  }
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

export type ModelInfo = components["schemas"]["ModelInfo"];
export type CatalogInfo = components["schemas"]["CatalogInfo"];
export type ConversationInfo = components["schemas"]["ConversationInfo"];
export type ConversationDetail = components["schemas"]["ConversationDetail"];
export type RunInfo = components["schemas"]["RunInfo"];
export type RunStart = components["schemas"]["RunStart"];
export type UsageInfo = components["schemas"]["UsageInfo"];
export const chatApi = {
  catalog: () => request<CatalogInfo>("/models"),
  refreshCatalog: () => request<CatalogInfo>("/models/refresh", "POST"),
  history: (q = "") =>
    request<ConversationInfo[]>(`/conversations?q=${encodeURIComponent(q)}`),
  conversation: (id: string) =>
    request<ConversationDetail>(`/conversations/${id}`),
  create: (title: string) =>
    request<ConversationInfo>("/conversations", "POST", { title }),
  rename: (id: string, title: string) =>
    request<ConversationInfo>(`/conversations/${id}`, "PATCH", { title }),
  remove: (id: string) =>
    request<void>(`/conversations/${id}?confirm=true`, "DELETE"),
  submit: (body: RunStart) => request<RunInfo>("/runs", "POST", body),
  run: (id: string) => request<RunInfo>(`/runs/${id}`),
  cancel: (id: string) => request<RunInfo>(`/runs/${id}/cancel`, "POST"),
  reconcile: (id: string) => request<RunInfo>(`/runs/${id}/reconcile`, "POST"),
  usage: () => request<UsageInfo>("/usage"),
  favorites: () => request<{ favorites: string[] }>("/preferences"),
  saveFavorites: (favorites: string[]) =>
    request<{ favorites: string[] }>("/preferences", "PATCH", { favorites }),
};

export type AttachmentInfo = components["schemas"]["AttachmentInfo"];
export type UploadLimits = components["schemas"]["UploadLimits"];
export type ComparisonInfo = components["schemas"]["ComparisonInfo"];
export type ComparisonStart = components["schemas"]["ComparisonStart"];
export type ComparisonSummary = components["schemas"]["ComparisonSummary"];
export const attachmentApi = {
  limits: () => request<UploadLimits>("/attachments/limits"),
  upload: (files: File[]) => {
    const body = new FormData();
    for (const file of files) body.append("files", file);
    return request<AttachmentInfo[]>("/attachments", "POST", body);
  },
};
export const comparisonApi = {
  start: (body: ComparisonStart) =>
    request<ComparisonInfo>("/comparisons", "POST", body),
  get: (id: string) => request<ComparisonInfo>(`/comparisons/${id}`),
  history: (conversation: string) =>
    request<ComparisonSummary[]>(`/conversations/${conversation}/comparisons`),
  fork: (run: string) =>
    request<ConversationDetail>(`/runs/${run}/fork`, "POST"),
};
