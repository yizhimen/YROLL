import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发时代理到 yroll serve（FastAPI）
const apiPaths = ["/project", "/operations", "/versions", "/clips", "/revert", "/render", "/chat", "/preview.mp4", "/problems", "/solutions", "/links"];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Listen on both IPv4 and IPv6 so browsers that resolve
    // `localhost` to 127.0.0.1 (IPv4) can reach the dev server.
    host: true,
    proxy: {
      ...Object.fromEntries(
        apiPaths.map((p) => [p, { target: "http://127.0.0.1:8765", changeOrigin: true }])
      ),
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
});
