// fetch wrapper: 拆 Result 包，错误抛 ApiError
import type { Result } from "./types";
import { DemoUnsupported, demoRequest, demoWriteBlocked, isStaticDemo } from "./demoData";

// 后端地址：
//   - 本地开发：留空 → 走 vite proxy（/api、/health 代理到 127.0.0.1:8000）
//   - 部署到 GitHub Pages：必须填绝对 URL（跨域），由构建时注入
//       VITE_API_BASE=https://your-backend.example.com npm run build
//   - 纯静态演示（无后端）：设 VITE_STATIC_DEMO=true，请求改由 demoData 本地应答
const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  code: number;
  data: unknown;
  constructor(code: number, message: string, data: unknown = null) {
    super(message);
    this.code = code;
    this.data = data;
  }
}

/** 把离线数据源抛出的错误统一包成 ApiError，页面侧的展示逻辑不用改 */
async function requestDemo<T>(method: string, path: string): Promise<T> {
  if (method !== "GET") demoWriteBlocked();
  try {
    return (await demoRequest(path)) as T;
  } catch (e) {
    if (e instanceof DemoUnsupported) throw new ApiError(-1, e.message);
    throw e;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  if (isStaticDemo()) return requestDemo<T>(method, path);

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

  if (res.status === 204) return undefined as T;

  const contentType = res.headers.get("content-type") || "";
  const text = await res.text();
  if (!contentType.includes("application/json")) {
    throw new ApiError(
      res.status || -1,
      `接口返回了非 JSON 内容 (HTTP ${res.status})`,
      text.slice(0, 200),
    );
  }

  if (!text.trim()) {
    throw new ApiError(res.status || -1, `接口返回空内容 (HTTP ${res.status})`);
  }

  let json: Result<T>;
  try {
    json = JSON.parse(text) as Result<T>;
  } catch (e) {
    throw new ApiError(-1, `响应解析失败: ${e}`);
  }
  if (!res.ok) {
    throw new ApiError(res.status, json.message || `请求失败 (HTTP ${res.status})`, json.data);
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
  download: async (path: string, fallbackName: string) => {
    if (isStaticDemo()) {
      throw new ApiError(-1, "静态演示站不提供文件下载，请克隆仓库本地运行。");
    }
    const res = await fetch(BASE + path);
    const ct = res.headers.get("content-type") || "";
    // 后端把业务异常也包成 HTTP 200 + Result JSON，
    // 不判断 content-type 就会把错误信息当成文件下载下来。
    if (!res.ok || ct.includes("application/json")) {
      const text = await res.text();
      let msg = `下载失败: HTTP ${res.status}`;
      try {
        const j = JSON.parse(text) as { message?: string };
        if (j.message) msg = j.message;
      } catch {
        /* 非 JSON，保留默认信息 */
      }
      throw new ApiError(res.status || -1, msg);
    }
    // 文件名优先用后端给的（中文岗位名已按 RFC 5987 编码）
    let filename = fallbackName;
    const cd = res.headers.get("content-disposition") || "";
    const m = /filename\*=UTF-8''([^;]+)/i.exec(cd);
    if (m) {
      try {
        filename = decodeURIComponent(m[1]);
      } catch {
        /* 解码失败则用兜底名 */
      }
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  /** 简历 PDF —— 可直接投递（未确认的建议会带「未证实·待确认」标记） */
  downloadResumePdf: (id: number) =>
    api.download(`/api/customizations/${id}/pdf`, `定制简历_${id}.pdf`),
  /** 简历 DOCX —— 可继续用 Word / WPS 编辑 */
  downloadResumeDocx: (id: number) =>
    api.download(`/api/customizations/${id}/docx`, `定制简历_${id}.docx`),
  /** 分析报告 PDF —— 差距分析 / 定制说明 / 面试押题 / 召回指标 */
  downloadReportPdf: (id: number) =>
    api.download(`/api/customizations/${id}/report.pdf`, `定制分析报告_${id}.pdf`),
};
