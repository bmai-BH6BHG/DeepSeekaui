import urllib.request, urllib.error

paths = [
    '/api/status', '/api', '/status', '/health', '/about',
    '/v1', '/v1/chat', '/v1/chat/completions',
    '/api/v1/chat/completions', '/api/v1/models',
    '/api/chat/completions', '/api/conversation',
    '/api/work', '/api/tasks', '/api/session',
    '/openapi.json', '/docs', '/swagger',
]

for p in paths:
    try:
        req = urllib.request.Request('http://127.0.0.1:7878' + p, method='GET')
        resp = urllib.request.urlopen(req, timeout=3)
        data = resp.read()[:200]
        print(f'200 {p}: {data}')
    except urllib.error.HTTPError as e:
        if e.code != 404:
            data = e.read()[:200]
            print(f'{e.code} {p}: {data}')
    except Exception as e:
        print(f'ERR {p}: {str(e)[:60]}')
