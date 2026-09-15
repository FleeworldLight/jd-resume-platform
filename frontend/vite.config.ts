import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 子路径部署（GitHub Pages 的 https://<user>.github.io/<repo>/）需要设 base：
//   VITE_BASE=/jd-resume-platform/ npm run build
// 本地开发留空即可（默认 "/"）。
const base = process.env.VITE_BASE || "/";

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/health": {
        target: process.env.VITE_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/api": {
        target: process.env.VITE_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    // 公开仓库不必把 TypeScript 源码一起发出去
    sourcemap: false,
  },
});
