"""OpenChatCut MCP Client (with session management)
"""
from __future__ import annotations
import json, sys, urllib.request
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

TOKEN = Path('C:/Users/THUNDEROBOT/.openchatcut/mcp-token').read_text().strip()
URL = 'http://127.0.0.1:5199/api/external-mcp/mcp'


class MCPClient:
    def __init__(self, url=URL, token=TOKEN):
        self.url = url
        self.token = token
        self.req_id = 0
        self.session_id = None
        self._init_done = False

    def post(self, payload, timeout=10):
        body = json.dumps(payload).encode()
        h = {'Content-Type': 'application/json',
             'Accept': 'application/json, text/event-stream',
             'Authorization': 'Bearer ' + self.token}
        if self.session_id:
            h['mcp-session-id'] = self.session_id
        req = urllib.request.Request(self.url, data=body, method='POST', headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ct = r.headers.get('content-type', '')
                text = r.read().decode()
                sid = r.headers.get('mcp-session-id')
                if sid and not self.session_id:
                    self.session_id = sid
                return ct, text
        except urllib.error.HTTPError as e:
            return 'error', str(e.code) + ' ' + e.read().decode()[:300]

    def call(self, method, params=None):
        self.req_id += 1
        payload = {'jsonrpc': '2.0', 'id': self.req_id, 'method': method, 'params': params or {}}
        ct, text = self.post(payload)
        if ct == 'error':
            return {'error': text}
        for line in text.split(chr(10)):
            if line.startswith('data: '):
                try:
                    return json.loads(line[6:])
                except Exception:
                    return {'raw': line[6:]}
        return {'raw': text}

    def notify(self, method, params=None):
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
        self.post(payload)

    def initialize(self):
        if self._init_done:
            return
        r = self.call('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'yroll-monitor', 'version': '0.1.0'}})
        self.notify('notifications/initialized')
        self._init_done = True
        return r

    def list_tools(self):
        self.initialize()
        return self.call('tools/list', {}).get('result', {}).get('tools', [])

    def list_prompts(self):
        self.initialize()
        return self.call('prompts/list', {}).get('result', {}).get('prompts', [])

    def call_tool(self, name, args):
        self.initialize()
        return self.call('tools/call', {'name': name, 'arguments': args or {}})


def main():
    c = MCPClient()
    print('[*] Initializing...')
    init = c.initialize()
    print('    session: ' + str(c.session_id)[:40])
    inst = init['result'].get('instructions', '')
    print('    instructions: ' + inst[:200])
    print()
    print('[*] Tools: ' + str(len(c.list_tools())))
    for t in c.list_tools():
        desc = (t.get('description', '') or '')[:80]
        print('    ' + t['name'].ljust(35) + ' ' + desc)
    print()
    print('[*] Prompts: ' + str(len(c.list_prompts())))
    for p in c.list_prompts():
        print('    ' + p['name'].ljust(30) + ' ' + (p.get('description', '') or '')[:60])
    print()
    print('[*] openchatcut_status:')
    r = c.call_tool('openchatcut_status', {})
    print(json.dumps(r, ensure_ascii=False, indent=2)[:800])


if __name__ == '__main__':
    main()
