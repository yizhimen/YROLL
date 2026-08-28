import json, sys, time, urllib.request
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

TOKEN = Path('C:/Users/THUNDEROBOT/.openchatcut/mcp-token').read_text().strip()
URL = 'http://127.0.0.1:5199/api/external-mcp/mcp'


def raw_post(payload_dict, timeout=10):
    body = json.dumps(payload_dict).encode()
    req = urllib.request.Request(URL, data=body, method='POST',
        headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                 'Authorization': 'Bearer ' + TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, dict(r.headers), r.read().decode()


status, headers, text = raw_post({
    'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
    'params': {'protocolVersion': '2024-11-05', 'capabilities': {},
               'clientInfo': {'name': 'yroll-mcp', 'version': '0.1'}}
})
sess = headers.get('mcp-session') or headers.get('Mcp-Session')
print('init: status=' + str(status) + ', session=' + str(sess))
print('  body: ' + text[:200])

status2, _, text2 = raw_post({
    'jsonrpc': '2.0', 'method': 'notifications/initialized', 'params': {}
})
print('init notif: status=' + str(status2) + ', body=' + text2[:200])

time.sleep(0.5)

status3, _, text3 = raw_post({
    'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}
})
print('list: status=' + str(status3) + ', body=' + text3[:300])
