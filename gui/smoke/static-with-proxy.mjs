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

createServer((req, res) => {
  const u = req.url ?? "/";
  const isAsset = u.startsWith("/assets/") || u.startsWith("/clips/")
    || u.startsWith("/tracks/") || u.startsWith("/selection/")
    || u.startsWith("/preview/") || u.startsWith("/project")
    || u.startsWith("/ui/") || u.startsWith("/operations")
    || u.startsWith("/lease/") || u.startsWith("/history/")
    || u.startsWith("/mutation/") || u.startsWith("/audit/")
    || u.startsWith("/keyboard/") || u.startsWith("/assets")
    || u.startsWith("/preview.mp4");
  if (isAsset) {
    proxyTo(req, res);
    return;
  }

  let path = u === "/" ? "/index.html" : u.split("?")[0];
  path = normalize(join(ROOT, path));
  if (!path.startsWith(ROOT)) {
    res.writeHead(403); res.end("forbidden"); return;
  }
  if (!existsSync(path)) {
    res.writeHead(404); res.end("not found"); return;
  }
  const ext = extname(path).toLowerCase();
  res.setHeader("Content-Type", MIME[ext] ?? "application/octet-stream");
  createReadStream(path).pipe(res);
}).listen(STATIC_PORT, "127.0.0.1", () => {
  console.log("URL: http://127.0.0.1:" + STATIC_PORT + "/");
});