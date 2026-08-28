import json, sys, time, urllib.request, urllib.error
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

TOKEN = Path('C:/Users/THUNDEROBOT/.openchatcut/mcp-token').read_text().strip()
URL = 'http://127.0.0.1:5199/api/external-mcp/mcp'

def post(payload, headers_extra=None):
    body = json.dumps(payload).encode()
    h = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', 'Authorization': 'Bearer ' + TOKEN}
    if headers_extra: h.update(headers_extra)
    req = urllib.request.Request(URL, data=body, method='POST', headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()

# init
s, h, t = post({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'yroll-mcp', 'version': '0.1'}}})
print('init', s, list(h.keys())[:5], t[:80])
sess = h.get('mcp-session') or h.get('Mcp-Session')
print('  session:', sess)

# Send initialized as notification (no id, no response)
s, h, t = post({'jsonrpc': '2.0', 'method': 'notifications/initialized', 'params': {}})
print('notif', s, list(h.keys())[:5], t[:200])

time.sleep(0.3)

# tools/list
s, h, t = post({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
print('list', s, t[:400])
