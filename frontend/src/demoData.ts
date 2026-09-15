/**
 * 静态演示数据源（GitHub Pages 上没有后端时用）
 *
 * 背景：GitHub Pages 只能托管静态文件。为了让演示站也能看到完整界面，
 * `scripts/export_static_demo.py` 把后端数据预导出成 `public/demo-data/*.json`，
 * 这里实现一个**与后端接口语义一致**的本地数据源：
 *   - GET 请求：读 JSON，筛选/排序/分页在客户端做（逻辑照抄 app/services/jd_service.py）
 *   - 写请求：一律抛出友好错误（与后端 DEMO_MODE 的提示保持一致）
 *
 * 启用方式：构建时注入 `VITE_STATIC_DEMO=true`（见 .github/workflows/deploy.yml）。
 * 本地开发不设该变量，仍走真实后端。
 */
import type {
  Customization,
  CustomizationDetail,
  Jd,
  JdFacets,
  LlmProvider,
  PageResp,
  Resume,
  ResumeContent,
  ResumeDetail,
} from "./types";

const ENABLED =
  import.meta.env.VITE_STATIC_DEMO === "true" ||
  import.meta.env.VITE_STATIC_DEMO === "1";

export const isStaticDemo = () => ENABLED;

/** 静态演示下写操作的统一提示（有意与后端 DEMO_MODE 的文案接近） */
const WRITE_BLOCKED =
  "这是在线演示站点（纯静态，无后端），为避免误导，抓取岗位 / 上传简历 / 删除 / " +
  "发起新的定制化等写操作已关闭。完整功能请克隆仓库本地运行（见 README）。";

export class DemoUnsupported extends Error {}

const DATA_DIR = `${import.meta.env.BASE_URL}demo-data/`;

async function loadJson<T>(name: string): Promise<T> {
  const url = `${DATA_DIR}${name}`;
  let res: Response;
  try {
    res = await fetch(url);
  } catch (e) {
    throw new DemoUnsupported(`演示数据请求失败：${url}（${String(e)}）`);
  }
  if (!res.ok) {
    throw new DemoUnsupported(`演示数据缺失：${name}（HTTP ${res.status}）`);
  }
  return (await res.json()) as T;
}

// ---------- 懒加载 + 缓存 ----------
interface JobsFile {
  items: Jd[];
  total: number;
}
interface ResumesFile {
  list: PageResp<Resume>;
  details: Record<string, ResumeDetail>;
  /** 结构化内容（编辑器表单用）：id -> ResumeContent */
  contents?: Record<string, ResumeContent>;
}
interface CustomsFile {
  list: PageResp<Customization>;
  details: Record<string, CustomizationDetail>;
}

let jobsP: Promise<JobsFile> | null = null;
let facetsP: Promise<JdFacets> | null = null;
let resumesP: Promise<ResumesFile> | null = null;
let customsP: Promise<CustomsFile> | null = null;
let providersP: Promise<LlmProvider[]> | null = null;
let healthP: Promise<Record<string, unknown>> | null = null;

const loadJobs = () => (jobsP ??= loadJson<JobsFile>("jobs.json"));
const loadFacets = () => (facetsP ??= loadJson<JdFacets>("facets.json"));
const loadResumes = () => (resumesP ??= loadJson<ResumesFile>("resumes.json"));
const loadCustoms = () => (customsP ??= loadJson<CustomsFile>("customizations.json"));
const loadProviders = () => (providersP ??= loadJson<LlmProvider[]>("llm-providers.json"));
const loadHealth = () =>
  (healthP ??= loadJson<Record<string, unknown>>("health.json"));

// ---------- 岗位筛选：与后端 JdService._build_conditions 保持一致 ----------
function filterJobs(all: Jd[], p: URLSearchParams): Jd[] {
  const kw = (p.get("keyword") ?? "").trim().toLowerCase();
  const city = (p.get("city") ?? "").trim();
  const edu = (p.get("education") ?? "").trim();
  const source = (p.get("source") ?? "").trim().toUpperCase();
  const salaryOnly = p.get("salary_only") === "true";
  const rawMin = p.get("salary_min");
  const rawMax = p.get("salary_max");
  const min = rawMin ? Number(rawMin) : null;
  const max = rawMax ? Number(rawMax) : null;

  return all.filter((j) => {
    if (kw) {
      const hay = [j.position, j.company, j.city, j.raw_text]
        .filter(Boolean)
        .join("\n")
        .toLowerCase();
      if (!hay.includes(kw)) return false;
    }
    if (city && !(j.city ?? "").includes(city)) return false;
    if (edu && !(j.education ?? "").includes(edu)) return false;
    if (source && (j.source ?? "").toUpperCase() !== source) return false;
    if (salaryOnly && j.salary_min == null) return false;
    // 与后端一致：按区间重叠匹配
    if (min != null && !(j.salary_max != null && j.salary_max >= min)) return false;
    if (max != null && !(j.salary_min != null && j.salary_min <= max)) return false;
    return true;
  });
}

/** 与后端 JdService._order_by 保持一致（薪资排序时空值排最后） */
function sortJobs(list: Jd[], sort: string): Jd[] {
  const arr = [...list];
  const nullLast = (v: number | null | undefined) => (v == null ? 1 : 0);
  switch (sort) {
    case "oldest":
      arr.sort((a, b) => a.id - b.id);
      break;
    case "salary_desc":
      arr.sort(
        (a, b) =>
          nullLast(a.salary_max) - nullLast(b.salary_max) ||
          (b.salary_max ?? 0) - (a.salary_max ?? 0) ||
          b.id - a.id,
      );
      break;
    case "salary_asc":
      arr.sort(
        (a, b) =>
          nullLast(a.salary_min) - nullLast(b.salary_min) ||
          (a.salary_min ?? 0) - (b.salary_min ?? 0) ||
          b.id - a.id,
      );
      break;
    case "company":
      arr.sort(
        (a, b) =>
          (a.company ?? "").localeCompare(b.company ?? "", "zh-CN") || b.id - a.id,
      );
      break;
    default:
      arr.sort((a, b) => b.id - a.id);
  }
  return arr;
}

function paginate<T>(items: T[], page: number, pageSize: number): PageResp<T> {
  const p = Math.max(1, page);
  const size = Math.max(1, Math.min(200, pageSize));
  const start = (p - 1) * size;
  return {
    items: items.slice(start, start + size),
    total: items.length,
    page: p,
    page_size: size,
  };
}

function intParam(p: URLSearchParams, key: string, fallback: number): number {
  const v = p.get(key);
  if (!v) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/**
 * 处理一次离线请求，返回「已拆包」的 data（与后端 Result.data 对应）。
 * 不支持的路径抛 DemoUnsupported，由 api.ts 包成 ApiError。
 */
export async function demoRequest(path: string): Promise<unknown> {
  const [rawPath, rawQuery = ""] = path.split("?", 2);
  const p = new URLSearchParams(rawQuery);

  if (rawPath === "/health") return loadHealth();

  if (rawPath === "/api/jds/facets") return loadFacets();

  if (rawPath === "/api/jds") {
    const { items } = await loadJobs();
    const filtered = sortJobs(filterJobs(items, p), p.get("sort") ?? "latest");
    return paginate(filtered, intParam(p, "page", 1), intParam(p, "page_size", 20));
  }

  const jdStatus = rawPath.match(/^\/api\/jds\/(\d+)\/status$/);
  if (jdStatus) {
    const id = Number(jdStatus[1]);
    const { items } = await loadJobs();
    const job = items.find((j) => j.id === id);
    if (!job) throw new DemoUnsupported(`演示数据里没有岗位 #${id}`);
    return {
      id: job.id,
      crawl_status: job.crawl_status,
      crawl_error: job.crawl_error ?? null,
      has_structured: Boolean(job.structured),
    };
  }

  if (rawPath === "/api/llm-providers") return loadProviders();

  if (rawPath === "/api/resumes") {
    const { list } = await loadResumes();
    return paginate(list.items, intParam(p, "page", 1), intParam(p, "page_size", 20));
  }

  const resumeStatus = rawPath.match(/^\/api\/resumes\/(\d+)\/status$/);
  if (resumeStatus) {
    const id = Number(resumeStatus[1]);
    const { details } = await loadResumes();
    const r = details[String(id)];
    if (!r) throw new DemoUnsupported(`演示数据里没有简历 #${id}`);
    return {
      id: r.id,
      parse_status: r.parse_status,
      parse_error: r.parse_error ?? null,
      has_text: Boolean(r.resume_text),
    };
  }

  // 结构化内容（编辑器用）；注意要排在 /{id} 之前匹配更具体的路径
  const resumeContent = rawPath.match(/^\/api\/resumes\/(\d+)\/content$/);
  if (resumeContent) {
    const { contents } = await loadResumes();
    const c = contents?.[resumeContent[1]];
    if (!c) {
      throw new DemoUnsupported(`演示数据里没有简历 #${resumeContent[1]} 的结构化内容`);
    }
    return c;
  }

  const resumeDetail = rawPath.match(/^\/api\/resumes\/(\d+)$/);
  if (resumeDetail) {
    const { details } = await loadResumes();
    const r = details[resumeDetail[1]];
    if (!r) throw new DemoUnsupported(`演示数据里没有简历 #${resumeDetail[1]}`);
    return r;
  }

  if (rawPath === "/api/customizations") {
    const { list } = await loadCustoms();
    const status = p.get("status");
    const filtered = status
      ? list.items.filter((c) => c.status === status)
      : list.items;
    return paginate(filtered, intParam(p, "page", 1), intParam(p, "page_size", 20));
  }

  const customDetail = rawPath.match(/^\/api\/customizations\/(\d+)$/);
  if (customDetail) {
    const { details } = await loadCustoms();
    const c = details[customDetail[1]];
    if (!c) throw new DemoUnsupported(`演示数据里没有定制化 #${customDetail[1]}`);
    return c;
  }

  throw new DemoUnsupported(`静态演示不含该接口：${rawPath}`);
}

/** 写操作在静态演示下一律不可用 */
export function demoWriteBlocked(): never {
  throw new DemoUnsupported(WRITE_BLOCKED);
}
