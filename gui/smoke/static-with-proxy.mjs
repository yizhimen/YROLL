#!/usr/bin/env node
// GUI-03R5 manual pass: tiny static-file server for the built
// dist/ bundle + a proxy pass-through to the backend on 8770.
//
// Usage:
//   node gui/smoke/static-with-proxy.mjs [staticPort] [backendPort]
// Defaults: static=5173, backend=8770.
//
// This is a minimal alternative to vite preview (which does not
// apply the dev proxy in preview mode). For the manual pass, we
// need /project /preview/at_frame etc. to land on the yroll serve,
// not the SPA shell.

import { createReadStream, existsSync } from "node:fs";
import { extname, join, resolve, normalize } from "node:path";
import { createServer, request as httpRequest } from "node:http";

const ROOT = resolve(process.cwd(), "gui", "dist");
const STATIC_PORT = Number(process.argv[2] ?? 5173);
const BACKEND_PORT = Number(process.argv[3] ?? 8770);
const BACKEND = "http://127.0.0.1:" + BACKEND_PORT;

console.log("=== GUI-03R5 MANUAL PASS STATIC SERVER ===");
console.log("static root: " + ROOT);
console.log("backend:    " + BACKEND);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js":   "text/javascript; charset=utf-8",
  ".css":  "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg":  "image/svg+xml",
  ".png":  "image/png",
  ".ico":  "image/x-icon",
};

function proxyTo(req, res) {
  const url = BACKEND + req.url;
  const proxyReq = httpRequest(url, {
    method: req.method,
    headers: req.headers,
  }, (pr) => {
    res.writeHead(pr.statusCode ?? 502, pr.headers);
    pr.pipe(res);
  });
  proxyReq.on("error", (e) => {
    res.writeHead(502, { "Content-Type": "text/plain" });
    res.end("proxy error: " + e.message);
  });
  req.pipe(proxyReq);
}

// Paths with one of these extensions are served from the gui/dist
// static root; everything else is proxied to the backend. This
// mirrors gui/vite.config.ts's catch-all regex (which excludes only
// @vite/@react-refresh/node_modules/src/favicon). The previous
// explicit-prefix list in this file was incomplete: /clips (no
// trailing slash), /revert, /presets, /costs, /versions, /render,
// /export/package, /fonts/import, /import/jianying, /chat,
// /search-transcripts, /subtitles, /links, /frame/preview, /snap,
// /timelines, /problems, /solutions/execute all fell through to the
// bare-Python "not found" 404 — masking real FastAPI responses
// behind the proxy. GUI-04 04-01: flip to a negative check so the
// route table can never silently drift from the backend again.
const STATIC_EXT = new Set([
  ".html", ".js", ".css", ".json", ".svg", ".png", ".ico",
  ".woff", ".woff2", ".ttf", ".otf", ".map",
]);

createServer((req, res) => {
  const u = req.url ?? "/";
  const pathPart = u.split("?")[0];
  const ext = extname(pathPart).toLowerCase();
  const isSpaRoot = u === "/" || pathPart === "/index.html";
  const isStaticFile = STATIC_EXT.has(ext);

  if (isSpaRoot || isStaticFile) {
    let diskPath = (u === "/" || pathPart === "/index.html")
      ? "/index.html"
      : pathPart;
    diskPath = normalize(join(ROOT, diskPath));
    if (!diskPath.startsWith(ROOT)) {
      res.writeHead(403); res.end("forbidden"); return;
    }
    if (existsSync(diskPath)) {
      res.setHeader("Content-Type", MIME[ext] ?? (isSpaRoot ? "text/html; charset=utf-8" : "application/octet-stream"));
      createReadStream(diskPath).pipe(res);
      return;
    }
    if (isSpaRoot) {
      res.writeHead(404); res.end("index.html not found in dist"); return;
    }
    // Static file requested but not on disk — fall through to proxy.
    // The backend may legitimately serve /assets/index-XXXX.js etc.
    // via its own StaticFiles mount; we don't want to 404 that here.
  }

  // Anything else: API call → proxy to backend. This is the
  // catch-all that replaces the previous incomplete explicit-prefix
  // list. If the backend doesn't know the path, it returns its own
  // proper JSON 4xx — not the bare "not found" this proxy used to
  // emit.
  proxyTo(req, res);
}).listen(STATIC_PORT, "127.0.0.1", () => {
  console.log("URL: http://127.0.0.1:" + STATIC_PORT + "/");
});