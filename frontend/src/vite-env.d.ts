/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端绝对地址。本地开发留空（走 vite proxy）；部署时由构建注入。 */
  readonly VITE_API_BASE?: string;
  /** 子路径部署的 base，例如 /jd-resume-platform/ */
  readonly VITE_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
