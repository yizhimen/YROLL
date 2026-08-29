// GUI-01 smoke harness: static-file server + Playwright driver.
//
// We can't use scripts/serve_gui.py because the SimpleHTTPRequestHandler
// happily hangs on 304 responses (a real bug, but out of GUI-01's scope).
// Here we serve gui/dist over a tiny Node http server and let Playwright
// rewrite API paths to the live backend. The whole thing takes <50 lines
// and dies as soon as the test exits.

import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { resolve, extname, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const DIST = resolve(HERE, "..", "dist");
const PORT = 5180;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js":   "application/javascript; charset=utf-8",
  ".css":  "text/css; charset=utf-8",
  ".png":  "image/png",
  ".svg":  "image/svg+xml",
  ".ico":  "image/x-icon",
  ".json": "application/json",
};

createServer(async (req, res) => {
  let p = req.url === "/" ? "/index.html" : req.url.split("?")[0];
  const file = resolve(DIST + p);
  if (!file.startsWith(DIST)) { res.statusCode = 403; res.end(); return; }
  try {
    const s = await stat(file);
    if (s.isDirectory()) { res.statusCode = 404; res.end(); return; }
    const data = await readFile(file);
    res.setHeader("Content-Type", MIME[extname(file)] ?? "application/octet-stream");
    res.setHeader("Cache-Control", "no-store");
    res.end(data);
  } catch {
    res.statusCode = 404; res.end();
  }
}).listen(PORT, "127.0.0.1", () => {
  console.log(`[smoke-srv] http://127.0.0.1:${PORT}/`);
});
