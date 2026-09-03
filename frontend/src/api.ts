// fetch wrapper: 拆 Result 包，错误抛 ApiError
import type { Result } from "./types";

const BASE = ""; // dev 走 vite proxy，prod 走 nginx 同源

export class ApiError extends Error {
  code: number;
  data: unknown;
  constructor(code: number, message: string, data: unknown = null) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(BASE + path, {
    method,
    headers,
    body: payload,
    ...init,
  });
  let json: Result<T>;
  try {
    json = (await res.json()) as Result<T>;
  } catch (e) {
    throw new ApiError(-1, `响应解析失败: ${e}`);
  }
  if (json.code !== 0) {
    throw new ApiError(json.code, json.message, json.data);
  }
  return json.data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<T>("POST", path, fd);
  },
  download: async (path: string, filename: string) => {
    const res = await fetch(BASE + path);
    if (!res.ok) throw new ApiError(-1, `下载失败: HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
  downloadPdf: async (id: number) => {
    const res = await fetch(`${BASE}/api/customizations/${id}/pdf`);
    if (!res.ok) throw new ApiError(-1, `PDF 下载失败: HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `customization_${id}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  },
};
