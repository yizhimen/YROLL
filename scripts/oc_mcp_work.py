"""OpenChatCut MCP Client (full)
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
        self.edit_session_id = None
        self._init_done = False

    def post(self, payload, timeout=10):
        body = json.dumps(payload).encode()
        h = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', 'Authorization': 'Bearer ' + self.token}
        if self.session_id:
            h['mcp-session-id'] = self.session_id
        req = urllib.request.Request(self.url, data=body, method='POST', headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                sid = r.headers.get('mcp-session-id')
                if sid and not self.session_id:
                    self.session_id = sid
                return r.read().decode()
        except urllib.error.HTTPError as e:
            return '{"http_error":' + str(e.code) + ',"body":' + json.dumps(e.read().decode()[:300]) + '}'

    def call(self, method, params=None):
        self.req_id += 1
        payload = {'jsonrpc': '2.0', 'id': self.req_id, 'method': method, 'params': params or {}}
        text = self.post(payload)
        for line in text.split(chr(10)):
            if line.startswith('data: '):
                try:
                    return json.loads(line[6:])
                except Exception:
                    return {'raw': line[6:]}
        return {'raw': text}

    def notify(self, method, params=None):
        self.post({'jsonrpc': '2.0', 'method': method, 'params': params or {}})

    def initialize(self):
        if self._init_done:
            return
        self.call('initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'yroll-monitor', 'version': '0.1.0'}})
        self.notify('notifications/initialized')
        self._init_done = True

    def call_tool(self, name, args=None):
        self.initialize()
        return self.call('tools/call', {'name': name, 'arguments': args or {}})

    def get_prompt(self, name, args=None):
        return self.call('prompts/get', {'name': name, 'arguments': args or {}})

    def create_project(self, name, aspect='9:16'):
        r = self.call_tool('create_project', {'name': name, 'aspectRatio': aspect})
        text = r.get('result', {}).get('structuredContent', {}).get('id', '?')
        return text

    def target_project(self, project_id, mode='offline'):
        r = self.call_tool('target_project', {'projectId': project_id, 'mode': mode})
        return r.get('result', {}).get('structuredContent', {})

    def begin_edit(self, approval_mode='auto'):
        r = self.call_tool('begin_edit_session', {'approvalMode': approval_mode})
        sc = r.get('result', {}).get('structuredContent', {})
        self.edit_session_id = sc.get('editSessionId')
        return sc

    def read_timeline(self):
        args = {}
        if self.edit_session_id:
            args['editSessionId'] = self.edit_session_id
        r = self.call_tool('read_timeline', args)
        return r.get('result', {}).get('structuredContent', {})

    def add_clip(self, asset_id, timeline_start_frame, duration_frames, track_id='main'):
        """Add image clip to timeline (frame-based, 24fps = 24 frames/sec)."""
        args = {
            'assetId': asset_id,
            'trackId': track_id,
            'startFrame': timeline_start_frame,
            'durationFrames': duration_frames,
        }
        if self.edit_session_id:
            args['editSessionId'] = self.edit_session_id
        return self.call_tool('add_clip', args)

    def list_assets(self):
        """Try to find how to list media library."""
        r = self.call_tool('list_media', {})
        return r

    def review(self):
        """Commit edit session."""
        if not self.edit_session_id:
            return None
        return self.call_tool('review_edit_session', {'editSessionId': self.edit_session_id})


if __name__ == '__main__':
    c = MCPClient()
    c.initialize()
    print('[*] Initialized, session:', c.session_id)
    print()
    print('[*] List projects:')
    r = c.call_tool('list_projects', {})
    sc = r.get('result', {}).get('structuredContent', {})
    if isinstance(sc, list):
        for p in sc[:5]:
            print('  -', p.get('name'), '(', p.get('id', '?')[:8] + ')', 'updated:', p.get('updatedAt'))
    print()
    print('[*] List prompts:')
    r = c.call_tool('prompts/list', {})
    sc = r.get('result', {}).get('structuredContent', {})
    if isinstance(sc, dict):
        for name in sc:
            print('  -', name)
