import urllib.request, json, sys

paths = [
    '/api/status', '/api/chat', '/api/send', '/api/prompt',
    '/api/conversation', '/api/session', '/api/tasks',
    '/api/work', '/api/context', '/api/messages',
    '/api/v1/chat', '/api/v1/messages', '/api/v1/prompt',
]

for p in paths:
    try:
        req = urllib.request.Request('http://127.0.0.1:7878' + p)
        resp = urllib.request.urlopen(req, timeout=3)
        data = resp.read()[:300]
        print(f'{p} -> {resp.status}')
        if data.strip():
            print(f'  {data[:200]}')
    except Exception as e:
        code = getattr(e, 'code', '?')
        print(f'{p} -> {code} {str(e)[:60]}')
