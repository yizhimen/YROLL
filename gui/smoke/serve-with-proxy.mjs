// Static dist server with /api/* proxy to FastAPI on :8765.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';

const DIST = process.argv[2] || 'D:/cc/YROLL/gui/dist';
const PORT = Number(process.argv[3] || 5180);
const API = process.argv[4] || 'http://127.0.0.1:8765';
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
  '.json': 'application/json',
  '.map':  'application/json',
};

const STATIC_PREFIXES = ['/assets/', '/favicon'];
const isStatic = (url) => STATIC_PREFIXES.some((p) => url.startsWith(p));

const serveStatic = async (res, url) => {
  let p = resolve(DIST, '.' + url);
  if (url === '/' || url === '') p = resolve(DIST, 'index.html');
  // SPA fallback: any non-asset path that isn't a real file falls
  // back to index.html so client-side routes still load.
  try { await readFile(p); }
  catch {
    if (isStatic(url)) { res.writeHead(404); res.end('not found'); return; }
    p = resolve(DIST, 'index.html');
  }
  const data = await readFile(p);
  res.writeHead(200, { 'content-type': MIME[extname(p)] || 'application/octet-stream' });
  res.end(data);
};

createServer(async (req, res) => {
  const url = (req.url || '/').split('?')[0];
  if (isStatic(url) || url === '/' || url === '') {
    await serveStatic(res, url);
    return;
  }
  // Proxy everything else (API + /ws) to FastAPI.
  const target = API + req.url;
  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers: req.headers,
      body: req.method === 'GET' || req.method === 'HEAD' ? undefined : req,
      duplex: 'half',
    });
    res.writeHead(upstream.status, Object.fromEntries(upstream.headers));
    if (upstream.body) {
      const reader = upstream.body.getReader();
      const pump = async () => {
        const { value, done } = await reader.read();
        if (done) { res.end(); return; }
        res.write(Buffer.from(value));
        await pump();
      };
      await pump();
    } else {
      res.end();
    }
  } catch (e) {
    res.writeHead(502); res.end(`proxy error: ${e}`);
  }
}).listen(PORT, () => console.log(`serving ${DIST} on :${PORT}, proxying non-static to ${API}`));
