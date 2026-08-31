// GUI-03R3-W-D: static server for dist/ with /api/* proxy to the
// live yroll serve. Mirrors gui/smoke/serve-with-proxy.mjs (W-C).
// Used by the W-D smoke script.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.resolve(__dirname, '..', 'dist');
const PORT = Number(process.env.PORT ?? 5180);
const API = process.env.API ?? 'http://127.0.0.1:8765';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json; charset=utf-8',
  '.ico': 'image/x-icon',
};

const proxyToApi = (req, res) => {
  const opts = new URL(req.url, API);
  const proxyReq = http.request({
    hostname: opts.hostname,
    port: opts.port,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: opts.host },
  }, (proxyRes) => {
    res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
    proxyRes.pipe(res);
  });
  proxyReq.on('error', (e) => {
    res.writeHead(502);
    res.end(`proxy error: ${e.message}`);
  });
  req.pipe(proxyReq);
};

const serveStatic = (req, res) => {
  let p = req.url.split('?')[0];
  if (p === '/' || p === '') p = '/index.html';
  const file = path.join(DIST, p);
  if (!file.startsWith(DIST)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, data) => {
    if (err) {
      // SPA fallback
      fs.readFile(path.join(DIST, 'index.html'), (err2, idx) => {
        if (err2) { res.writeHead(404).end('not found'); return; }
        res.writeHead(200, { 'content-type': MIME['.html'] });
        res.end(idx);
      });
      return;
    }
    const ext = path.extname(file).toLowerCase();
    res.writeHead(200, { 'content-type': MIME[ext] ?? 'application/octet-stream' });
    res.end(data);
  });
};

const server = http.createServer((req, res) => {
  // Anything under /api/* or non-asset requests with the JSON content-type
  // go to the live yroll server. Everything else → dist.
  if (req.url?.startsWith('/api/')) {
    proxyToApi(req, res);
    return;
  }
  // The GUI calls /project /sequence /keyboard/keymap directly
  // (no /api prefix); proxy those too.
  if (
    req.url?.startsWith('/project') ||
    req.url?.startsWith('/sequence') ||
    req.url?.startsWith('/keyboard') ||
    req.url?.startsWith('/snap') ||
    req.url?.startsWith('/ui/') ||
    req.url?.startsWith('/lease') ||
    req.url?.startsWith('/session') ||
    req.url?.startsWith('/mutation') ||
    req.url?.startsWith('/chat') ||
    req.url?.startsWith('/assets/') ||
    req.url?.startsWith('/clips/') ||
    req.url?.startsWith('/tracks/') ||
    req.url?.startsWith('/subtitles/') ||
    req.url?.startsWith('/selection/') ||
    req.url?.startsWith('/audit') ||
    req.url?.startsWith('/presets') ||
    req.url?.startsWith('/reality-test') ||
    req.url?.startsWith('/search') ||
    req.url?.startsWith('/render') ||
    req.url?.startsWith('/export') ||
    req.url?.startsWith('/import')
  ) {
    proxyToApi(req, res);
    return;
  }
  serveStatic(req, res);
});

server.listen(PORT, () => {
  console.log(`[W-D:serve] http://localhost:${PORT, 10} → ${DIST}`);
  console.log(`[W-D:serve] proxy /api/* + a handful of top-level paths → ${API}`);
});