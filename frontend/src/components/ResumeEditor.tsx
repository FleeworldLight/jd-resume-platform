import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Loader2,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { api, ApiError } from "../api";
import type {
  ResumeContent,
  ResumeDetail,
  ResumeEducation,
  ResumeItem,
} from "../types";

/**
 * 结构化简历编辑器：左侧分节表单 + 右侧 A4 实时预览。
 *
 * 数据流：GET /api/resumes/{id}/content → 本地 state → PUT 同一个接口。
 * 保存时后端会把结构渲染回纯文本写入 resume_text，**不覆盖上传的原文件**；
 * 返回的是「落库后重新解析」的结果，所以表单里看到的永远等于真正存下来的。
 */
interface Props {
  resume: ResumeDetail;
  onSaved: () => void;
}

const EMPTY_ITEM = (): ResumeItem => ({
  title: "",
  org: "",
  role: "",
  start: "",
  end: "",
  description: "",
  highlights: [],
  tech_stack: [],
});

const EMPTY_EDU = (): ResumeEducation => ({
  school: "",
  major: "",
  degree: "",
  start: "",
  end: "",
  highlights: [],
});

export default function ResumeEditor({ resume, onSaved }: Props) {
  const [content, setContent] = useState<ResumeContent | null>(null);
  const [baseline, setBaseline] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const c = await api.get<ResumeContent>(`/api/resumes/${resume.id}/content`);
      setContent(c);
      setBaseline(JSON.stringify(c));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [resume.id]);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = content !== null && JSON.stringify(content) !== baseline;

  const patch = (fn: (draft: ResumeContent) => void) => {
    setContent((prev) => {
      if (!prev) return prev;
      const next: ResumeContent = JSON.parse(JSON.stringify(prev));
      fn(next);
      return next;
    });
  };

  const save = async () => {
    if (!content) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const saved = await api.put<ResumeContent>(
        `/api/resumes/${resume.id}/content`,
        content,
      );
      setContent(saved);
      setBaseline(JSON.stringify(saved));
      setNotice("已保存。导出的 PDF / DOCX / TXT 都会用这份内容。");
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <p className="flex items-center gap-2 py-10 text-sm text-slate-500">
        <Loader2 size={15} className="animate-spin" /> 正在解析简历…
      </p>
    );
  }
  if (!content) {
    return (
      <p className="flex items-center gap-2 py-10 text-sm text-red-600">
        <AlertCircle size={15} /> {error || "解析失败"}
      </p>
    );
  }

  const lines = content.extras.length + content.custom_sections.length;

  return (
    <div className="space-y-3">
      {/* ---------- 工具条 ---------- */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-slate-500">
          {content.parse_note}
          {dirty && (
            <span className="ml-2 font-medium text-amber-600">● 有未保存修改</span>
          )}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <button
            onClick={save}
            disabled={saving || !dirty}
            className="btn-primary py-1.5 text-sm"
          >
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            保存
          </button>
        </span>
      </div>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertCircle size={15} className="mt-0.5 shrink-0" />
          {error}
        </div>
      )}
      {notice && (
        <div className="flex items-start gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-brand-800">
          <CheckCircle2 size={15} className="mt-0.5 shrink-0" />
          {notice}
        </div>
      )}

      {/* ---------- 左表单 + 右预览 ---------- */}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* ----- 表单 ----- */}
        <div className="max-h-[calc(100vh-14rem)] space-y-4 overflow-y-auto pr-1">
          {/* 基本信息 */}
          <Panel title="基本信息">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="姓名">
                <input
                  className="input"
                  value={content.basics.name}
                  onChange={(e) => patch((d) => (d.basics.name = e.target.value))}
                />
              </Field>
              <Field label="年龄">
                <input
                  className="input"
                  value={content.basics.age}
                  onChange={(e) => patch((d) => (d.basics.age = e.target.value))}
                  placeholder="22岁"
                />
              </Field>
              <Field label="电话">
                <input
                  className="input"
                  value={content.basics.phone}
                  onChange={(e) => patch((d) => (d.basics.phone = e.target.value))}
                />
              </Field>
              <Field label="邮箱">
                <input
                  className="input"
                  value={content.basics.email}
                  onChange={(e) => patch((d) => (d.basics.email = e.target.value))}
                />
              </Field>
              <Field label="城市">
                <input
                  className="input"
                  value={content.basics.city}
                  onChange={(e) => patch((d) => (d.basics.city = e.target.value))}
                />
              </Field>
              <Field label="求职意向">
                <input
                  className="input"
                  value={content.profile.title}
                  onChange={(e) => patch((d) => (d.profile.title = e.target.value))}
                  placeholder="大数据开发实习"
                />
              </Field>
              <Field label="附加身份（如年级/届别）" span>
                <input
                  className="input"
                  value={content.profile.tagline}
                  onChange={(e) => patch((d) => (d.profile.tagline = e.target.value))}
                  placeholder="大三 · 27届"
                />
              </Field>
            </div>
            <div className="mt-3">
              <ListEditor
                label="代码 / 作品链接"
                items={content.basics.links}
                onChange={(v) => patch((d) => (d.basics.links = v))}
                placeholder="GitHub：https://github.com/xxx"
              />
            </div>
          </Panel>

          {/* 个人简介 */}
          <Panel title="个人简介">
            <textarea
              className="input min-h-[92px] resize-y text-sm leading-6"
              value={content.profile.summary}
              onChange={(e) => patch((d) => (d.profile.summary = e.target.value))}
              placeholder="一两句话说明你的方向与优势"
            />
            <div className="mt-3">
              <ListEditor
                label="简介下的要点"
                items={content.profile.highlights}
                onChange={(v) => patch((d) => (d.profile.highlights = v))}
                placeholder="• 一条要点"
              />
            </div>
          </Panel>

          {/* 教育 */}
          <Panel
            title="教育经历"
            onAdd={() => patch((d) => d.education.push(EMPTY_EDU()))}
          >
            {content.education.length === 0 && <Empty text="还没有教育经历" />}
            {content.education.map((e, i) => (
              <ItemShell
                key={i}
                label={`教育 ${i + 1}`}
                onRemove={() => patch((d) => d.education.splice(i, 1))}
                onUp={i > 0 ? () => patch((d) => swap(d.education, i, i - 1)) : undefined}
                onDown={
                  i < content.education.length - 1
                    ? () => patch((d) => swap(d.education, i, i + 1))
                    : undefined
                }
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="学校">
                    <input
                      className="input"
                      value={e.school}
                      onChange={(ev) => patch((d) => (d.education[i].school = ev.target.value))}
                    />
                  </Field>
                  <Field label="专业">
                    <input
                      className="input"
                      value={e.major}
                      onChange={(ev) => patch((d) => (d.education[i].major = ev.target.value))}
                    />
                  </Field>
                  <Field label="开始">
                    <input
                      className="input"
                      value={e.start}
                      onChange={(ev) => patch((d) => (d.education[i].start = ev.target.value))}
                      placeholder="2023-09"
                    />
                  </Field>
                  <Field label="结束">
                    <input
                      className="input"
                      value={e.end}
                      onChange={(ev) => patch((d) => (d.education[i].end = ev.target.value))}
                      placeholder="2027-06"
                    />
                  </Field>
                </div>
              </ItemShell>
            ))}
          </Panel>

          {/* 经历 / 项目 */}
          <ItemsPanel
            title="团队项目 / 实习经历"
            items={content.experiences}
            content={content}
            patch={patch}
            field="experiences"
          />
          <ItemsPanel
            title="个人项目"
            items={content.projects}
            content={content}
            patch={patch}
            field="projects"
          />

          {/* 技能 / 奖项 */}
          <Panel title="技能">
            <textarea
              className="input min-h-[60px] resize-y text-sm"
              value={content.skills.join("、")}
              onChange={(ev) =>
                patch(
                  (d) =>
                    (d.skills = ev.target.value
                      .split(/[、,，/|]/)
                      .map((s) => s.trim())
                      .filter(Boolean)),
                )
              }
              placeholder="用「、」分隔，例如：Python、SQL、Docker"
            />
          </Panel>

          <Panel title="奖项 / 证书">
            <ListEditor
              label=""
              items={content.awards}
              onChange={(v) => patch((d) => (d.awards = v))}
              placeholder="校级一等奖学金"
            />
          </Panel>

          {/* 兜底区 */}
          {lines > 0 && (
            <Panel title="其他未归类内容">
              <p className="mb-2 text-xs text-slate-500">
                这些内容没有被自动归入上面的小节，<b>保存时会原样写回</b>，不会丢失。
              </p>
              {content.custom_sections.map((s, i) => (
                <ItemShell
                  key={`cs-${i}`}
                  label={s.title}
                  onRemove={() => patch((d) => d.custom_sections.splice(i, 1))}
                >
                  <textarea
                    className="input min-h-[60px] resize-y text-sm"
                    value={s.lines.join("\n")}
                    onChange={(ev) =>
                      patch(
                        (d) =>
                          (d.custom_sections[i].lines = ev.target.value.split("\n")),
                      )
                    }
                  />
                </ItemShell>
              ))}
              {content.extras.length > 0 && (
                <ListEditor
                  label="其它行"
                  items={content.extras}
                  onChange={(v) => patch((d) => (d.extras = v))}
                  placeholder="原文行"
                />
              )}
            </Panel>
          )}
        </div>

        {/* ----- 预览 ----- */}
        <div className="lg:sticky lg:top-24 lg:self-start">
          <div className="mb-2 flex items-center gap-2 text-xs text-slate-400">
            <span className="eyebrow mb-0">PREVIEW</span>
            <span>预览 = 保存后的文本内容</span>
          </div>
          <div className="max-h-[calc(100vh-14rem)] overflow-y-auto rounded-xl bg-white p-7 ring-1 ring-black/[0.06] shadow-[0_1px_3px_rgba(16,40,34,0.06)]">
            <ResumePreview content={content} />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ================= 小组件 ================= */

function Panel({
  title,
  onAdd,
  children,
}: {
  title: string;
  onAdd?: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        {onAdd && (
          <button
            onClick={onAdd}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-brand-700 hover:bg-brand-50"
          >
            <Plus size={13} /> 添加
          </button>
        )}
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function ItemsPanel({
  title,
  items,
  content,
  patch,
  field,
}: {
  title: string;
  items: ResumeItem[];
  content: ResumeContent;
  patch: (fn: (d: ResumeContent) => void) => void;
  field: "experiences" | "projects";
}) {
  return (
    <Panel
      title={title}
      onAdd={() =>
        patch((d) => {
          d[field].push(EMPTY_ITEM());
        })
      }
    >
      {items.length === 0 && <Empty text="还没有条目" />}
      {items.map((it, i) => (
        <ItemShell
          key={i}
          label={it.title || it.org || `条目 ${i + 1}`}
          onRemove={() =>
            patch((d) => {
              d[field].splice(i, 1);
            })
          }
          onUp={i > 0 ? () => patch((d) => swap(d[field], i, i - 1)) : undefined}
          onDown={
            i < items.length - 1
              ? () =>
                  patch((d) => {
                    swap(d[field], i, i + 1);
                  })
              : undefined
          }
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="名称 / 标题" span>
              <input
                className="input"
                value={it.title}
                onChange={(e) =>
                  patch((d) => {
                    d[field][i].title = e.target.value;
                  })
                }
                placeholder="短视频平台内容分析系统"
              />
            </Field>
            <Field label="组织（公司 / 课程 / 团队）">
              <input
                className="input"
                value={it.org}
                onChange={(e) =>
                  patch((d) => {
                    d[field][i].org = e.target.value;
                  })
                }
              />
            </Field>
            <Field label="角色">
              <input
                className="input"
                value={it.role}
                onChange={(e) =>
                  patch((d) => {
                    d[field][i].role = e.target.value;
                  })
                }
                placeholder="核心开发"
              />
            </Field>
            <Field label="开始">
              <input
                className="input"
                value={it.start}
                onChange={(e) =>
                  patch((d) => {
                    d[field][i].start = e.target.value;
                  })
                }
                placeholder="2026-03"
              />
            </Field>
            <Field label="结束">
              <input
                className="input"
                value={it.end}
                onChange={(e) =>
                  patch((d) => {
                    d[field][i].end = e.target.value;
                  })
                }
                placeholder="2026-06"
              />
            </Field>
            <Field label="一句话概述" span>
              <textarea
                className="input min-h-[56px] resize-y text-sm"
                value={it.description}
                onChange={(e) =>
                  patch((d) => {
                    d[field][i].description = e.target.value;
                  })
                }
              />
            </Field>
          </div>
          <div className="mt-3 space-y-3">
            <ListEditor
              label="要点"
              items={it.highlights}
              onChange={(v) =>
                patch((d) => {
                  d[field][i].highlights = v;
                })
              }
              placeholder="• 一条成果/职责"
            />
            <ListEditor
              label="技术栈"
              items={it.tech_stack}
              onChange={(v) =>
                patch((d) => {
                  d[field][i].tech_stack = v;
                })
              }
              placeholder="Flink"
            />
          </div>
        </ItemShell>
      ))}
      {content.custom_sections.length === 0 && null}
    </Panel>
  );
}

function ItemShell({
  label,
  onRemove,
  onUp,
  onDown,
  children,
}: {
  label: string;
  onRemove: () => void;
  onUp?: () => void;
  onDown?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-line bg-surface-low/60 p-3">
      <div className="mb-2 flex items-center gap-1">
        <span className="truncate text-xs font-medium text-slate-600">{label}</span>
        <span className="ml-auto flex items-center gap-0.5">
          {onUp && (
            <IconBtn title="上移" onClick={onUp}>
              <ArrowUp size={13} />
            </IconBtn>
          )}
          {onDown && (
            <IconBtn title="下移" onClick={onDown}>
              <ArrowDown size={13} />
            </IconBtn>
          )}
          <IconBtn title="删除" onClick={onRemove} danger>
            <Trash2 size={13} />
          </IconBtn>
        </span>
      </div>
      {children}
    </div>
  );
}

function IconBtn({
  title,
  onClick,
  danger,
  children,
}: {
  title: string;
  onClick: () => void;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={`rounded p-1 ${
        danger
          ? "text-slate-400 hover:bg-red-50 hover:text-red-600"
          : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"
      }`}
    >
      {children}
    </button>
  );
}

function Field({
  label,
  span,
  children,
}: {
  label: string;
  span?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={span ? "sm:col-span-2" : undefined}>
      {label && <label className="label">{label}</label>}
      {children}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="py-2 text-xs text-slate-400">{text}</p>;
}

/** 字符串列表编辑：逐条输入 + 添加/删除 */
function ListEditor({
  label,
  items,
  onChange,
  placeholder,
}: {
  label: string;
  items: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  return (
    <div>
      {label && (
        <div className="mb-1 flex items-center justify-between">
          <span className="label mb-0">{label}</span>
          <button
            onClick={() => onChange([...items, ""])}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-brand-700 hover:bg-brand-50"
          >
            <Plus size={12} /> 添加
          </button>
        </div>
      )}
      {items.length === 0 && !label && (
        <button
          onClick={() => onChange([""])}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-brand-700 hover:bg-brand-50"
        >
          <Plus size={12} /> 添加一行
        </button>
      )}
      <div className="space-y-1.5">
        {items.map((v, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <input
              className="input py-1.5 text-sm"
              value={v}
              placeholder={placeholder}
              onChange={(e) => {
                const next = [...items];
                next[i] = e.target.value;
                onChange(next);
              }}
            />
            <IconBtn title="删除" danger onClick={() => onChange(items.filter((_, j) => j !== i))}>
              <Trash2 size={13} />
            </IconBtn>
          </div>
        ))}
      </div>
    </div>
  );
}

function swap<T>(arr: T[], a: number, b: number) {
  const t = arr[a];
  arr[a] = arr[b];
  arr[b] = t;
}

/* ================= 预览 ================= */

function ResumePreview({ content }: { content: ResumeContent }) {
  const { basics, profile, education, experiences, projects, skills, awards } = content;
  return (
    <article className="text-[13px] leading-6 text-slate-800">
      {basics.name && (
        <h1 className="font-serif text-[26px] font-semibold tracking-tight text-slate-900">
          {basics.name}
        </h1>
      )}
      {(profile.title || profile.tagline) && (
        <p className="mt-1 text-slate-600">
          {profile.title}
          {profile.tagline && ` | ${profile.tagline}`}
        </p>
      )}
      {(basics.phone || basics.email || basics.city || basics.age) && (
        <p className="mt-1 text-[12px] text-slate-500">
          {[
            basics.age,
            basics.phone && `电话 ${basics.phone}`,
            basics.email,
            basics.city,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}
      {basics.links.length > 0 && (
        <p className="mt-1 text-[12px] break-all text-slate-500">
          {basics.links.join(" · ")}
        </p>
      )}

      {profile.summary && (
        <p className="mt-3 whitespace-pre-wrap text-slate-700">{profile.summary}</p>
      )}
      {profile.highlights.length > 0 && (
        <ul className="mt-1 list-inside list-disc text-slate-700">
          {profile.highlights.map((h, i) => (
            <li key={i}>{h}</li>
          ))}
        </ul>
      )}

      {education.length > 0 && (
        <PreviewSection title="学习经历">
          {education.map((e, i) => (
            <div key={i} className="mb-1.5">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[12px] text-slate-500">
                  {e.start}
                  {e.end && ` ~ ${e.end}`}
                </span>
                <span className="font-medium">{e.school}</span>
                <span className="text-slate-600">{e.major}</span>
              </div>
              <Bullets items={e.highlights} />
            </div>
          ))}
        </PreviewSection>
      )}

      <PreviewItems title="团队项目 / 实习经历" items={experiences} />
      <PreviewItems title="个人项目" items={projects} />

      {skills.length > 0 && (
        <PreviewSection title="技能">
          <p className="text-slate-700">{skills.join("、")}</p>
        </PreviewSection>
      )}
      {awards.length > 0 && (
        <PreviewSection title="奖项 / 证书">
          <Bullets items={awards} />
        </PreviewSection>
      )}
      {content.custom_sections.map((s, i) => (
        <PreviewSection key={i} title={s.title}>
          <p className="whitespace-pre-wrap text-slate-700">{s.lines.join("\n")}</p>
        </PreviewSection>
      ))}
      {content.extras.length > 0 && (
        <PreviewSection title="其他">
          <Bullets items={content.extras} />
        </PreviewSection>
      )}
    </article>
  );
}

function PreviewSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-4">
      <h2 className="mb-1.5 border-b border-line pb-1 text-[12px] font-semibold tracking-[0.08em] text-slate-500">
        {title}
      </h2>
      {children}
    </section>
  );
}

function PreviewItems({ title, items }: { title: string; items: ResumeItem[] }) {
  if (items.length === 0) return null;
  return (
    <PreviewSection title={title}>
      {items.map((it, i) => (
        <div key={i} className="mb-2.5">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-[12px] text-slate-500">
              {it.start}
              {it.end && ` ~ ${it.end}`}
            </span>
            <span className="text-slate-600">
              {[it.org, it.role].filter(Boolean).join(" ")}
            </span>
          </div>
          {(it.title || it.org) && (
            <p className="font-medium text-slate-900">{it.title || it.org}</p>
          )}
          {it.description && <p className="text-slate-700">{it.description}</p>}
          <Bullets items={it.highlights} />
          {it.tech_stack.length > 0 && (
            <p className="mt-0.5 text-[12px] text-slate-500">
              技术栈：{it.tech_stack.join("、")}
            </p>
          )}
        </div>
      ))}
    </PreviewSection>
  );
}

function Bullets({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="list-inside list-disc text-slate-700">
      {items.map((h, i) => (
        <li key={i}>{h}</li>
      ))}
    </ul>
  );
}
