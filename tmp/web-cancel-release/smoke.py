import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote
sys.path.insert(0, '/home/deploy/AI-/web/server')
import auth

base = 'https://scriptwriter-jia.northcentralus.cloudapp.azure.com'
username = next(u for u in auth.load_users() if auth.is_admin(u))
cookie = auth.SESSION_COOKIE_NAME + '=' + auth.make_session_cookie_value(username)
def request(path, body=None, authenticated=True):
    headers = {'Content-Type': 'application/json'}
    if authenticated:
        headers['Cookie'] = cookie
    with urlopen(Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                         headers=headers), timeout=20) as response:
        text = response.read().decode()
        return json.loads(text) if path.startswith('/api/') else text

assert '终止生成' in request('/tasks.js')
assert 'stop-generation' in request('/shared.js')
assert 'setup-cancel' in request('/views/setup.js')
assert 'cancelTask' in request('/api.js')
name = request('/api/projects')['projects'][0]['name']
prefix = '/api/projects/' + quote(name, safe='')
for path, authenticated, code in [
    (prefix + '/prompt_tasks/nonexistent-cancel-smoke/cancel', True, 404),
    (prefix + '/regenerate/nonexistent-cancel-smoke/cancel', True, 404),
    (prefix + '/setup/cancel', False, 401),
    (prefix + '/prompt_tasks/nonexistent-cancel-smoke/cancel', False, 401),
    (prefix + '/regenerate/nonexistent-cancel-smoke/cancel', False, 401),
]:
    try:
        request(path, {}, authenticated)
        raise AssertionError('Invalid cancellation accepted')
    except HTTPError as error:
        assert error.code == code, (error.code, code)
assert isinstance(request('/api/tasks')['tasks'], list)
print('PASS HTTPS cancellation controls, scoped unknown IDs, authentication, task list; no user tasks changed')
