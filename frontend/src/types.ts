// 与后端 Result[T] 对齐
export interface Result<T> {
  code: number;
  message: string;
  data: T | null;
}

export interface PageResp<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Resume {
  id: number;
  original_filename: string;
  content_hash: string;
  parse_status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  parse_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResumeDetail extends Resume {
  resume_text: string | null;
  storage_path: string | null;
}

/** 结构化简历（编辑器表单的数据契约），与后端 app/schemas/resume_content.py 对应 */
export interface ResumeBasics {
  name: string;
  phone: string;
  email: string;
  city: string;
  age: string;
  links: string[];
}

export interface ResumeProfile {
  title: string;
  tagline: string;
  summary: string;
  highlights: string[];
}

export interface ResumeItem {
  title: string;
  org: string;
  role: string;
  start: string;
  end: string;
  description: string;
  highlights: string[];
  tech_stack: string[];
}

export interface ResumeEducation {
  school: string;
  major: string;
  degree: string;
  start: string;
  end: string;
  highlights: string[];
}

export interface ResumeCustomSection {
  title: string;
  lines: string[];
}

export interface ResumeContent {
  basics: ResumeBasics;
  profile: ResumeProfile;
  education: ResumeEducation[];
  experiences: ResumeItem[];
  projects: ResumeItem[];
  skills: string[];
  awards: string[];
  extras: string[];
  custom_sections: ResumeCustomSection[];
  parse_note: string;
}

export interface ResumeStatus {
  id: number;
  parse_status: string;
  parse_error: string | null;
}

export interface Jd {
  id: number;
  source: string;
  source_url: string | null;
  raw_text: string | null;
  company: string | null;
  position: string | null;
  salary_min: number | null;
  salary_max: number | null;
  city: string | null;
  experience: string | null;
  education: string | null;
  skills: string[] | null;
  responsibilities: string[] | null;
  requirements: string[] | null;
  structured: Record<string, unknown> | null;
  crawl_status: string;
  crawl_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface JdStatus {
  id: number;
  crawl_status: string;
  crawl_error: string | null;
  has_structured: boolean;
}

export interface JdFacetItem {
  value: string;
  count: number;
  min?: number | null;
  max?: number | null;
}

export interface JdFacets {
  total: number;
  with_salary: number;
  companies: number;
  sources: JdFacetItem[];
  cities: JdFacetItem[];
  educations: JdFacetItem[];
  salary_ranges: JdFacetItem[];
}

/** 列表筛选条件（与后端 GET /api/jds 的查询参数一一对应） */
export interface JdQuery {
  page: number;
  page_size: number;
  keyword: string;
  city: string;
  education: string;
  source: string;
  salary_only: boolean;
  sort: string;
  salary_min?: number | null;
  salary_max?: number | null;
}

/** 一次批量抓取的结果摘要 */
export interface JdCrawlSummary {
  scanned: number;
  inserted: number;
  updated: number;
  total: number;
  message: string;
}

export interface Customization {
  id: number;
  jd_id: number;
  base_resume_id: number;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  error_message: string | null;
  retry_count: number;
  provider_used: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomizationDetail extends Customization {
  gap_report: Record<string, unknown> | null;
  customized_resume: Record<string, unknown> | null;
  prediction: Record<string, unknown> | null;
  retrieval_metrics: Record<string, unknown> | null;
  matched_resumes: unknown[] | null;
}

export interface CustomizationStatus {
  id: number;
  status: string;
  error_message: string | null;
  retry_count: number;
  has_gap: boolean;
  has_resume: boolean;
  has_prediction: boolean;
}

export interface LlmProvider {
  id: number;
  name: string;
  provider_type: string;
  base_url: string | null;
  chat_model: string | null;
  embedding_model: string | null;
  is_default: boolean;
  enabled: boolean;
  has_api_key: boolean;
  api_key_masked: string | null;
  created_at: string;
  updated_at: string;
}

export interface HealthData {
  status: "ok" | "degraded";
  app: string;
  version: string;
  db: boolean;
}
