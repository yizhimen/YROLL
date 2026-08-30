import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发时代理到 yroll serve（FastAPI）。
//
// 历史问题：每个新端点要手动加入 apiPaths 数组，否则 Vite 会
// 返回自己的 HTML SPA shell，浏览器收到 JSON.parse 失败
// ("Unexpected token '<'")。改用正则把"任何不命中本地资源的
// 请求"代理到 FastAPI，新端点无需再改这里。
const apiProxyTarget = "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Listen on both IPv4 and IPv6 so browsers that resolve
    // `localhost` to 127.0.0.1 (IPv4) can reach the dev server.
    host: true,
    proxy: {
      // /ws 是 WebSocket，必须显式声明（正则不会透传 ws）
      "/ws": { target: apiProxyTarget, ws: true },
      // Catch-all: most non-source requests go to FastAPI. Vite's
      // own middleware serves files it can match (e.g. /@vite/...)
      // before this proxy runs, so the SPA shell only falls through
      // when nothing else matched — i.e. an API request. The root
      // `/` is bypassed so Vite serves its own index.html (with
      // /src/main.tsx). Without this bypass the catch-all forwards
      // `/` to FastAPI which returns 404.
      //
      // 03R fix: do NOT exclude `/assets/*` here. The /assets/import
      // endpoint (and friends) lives under that prefix; excluding
      // the whole prefix would make Vite proxy POST /assets/import
      // to its SPA fallback (HTML) and the browser would JSON.parse
      // fail. Vite-served static assets live under /@vite/... and
      // /node_modules/...; there is no gui/public/ or gui/src/assets/
      // directory, so excluding `assets/` from the proxy was always
      // wrong — it was just coincidence that the few existing
      // /assets/{id}/file etc. endpoints happened to work via the
      // FastAPI direct connection. Now they proxy through correctly.
      "^/(?!(@vite|@react-refresh|node_modules|src/|favicon))": {
        target: apiProxyTarget,
        changeOrigin: true,
        bypass: (req) => {
          // Let Vite serve the SPA shell itself for the root path.
          if (req.url === "/" || req.url === "") return req.url;
          return undefined;
        },
      },
    },
  },
});
