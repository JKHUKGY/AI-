import json,sys
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import quote
sys.path.insert(0,'/home/deploy/AI-/web/server')
import auth
base='https://scriptwriter-jia.northcentralus.cloudapp.azure.com'
username=next(u for u in auth.load_users() if auth.is_admin(u))
cookie=auth.SESSION_COOKIE_NAME+'='+auth.make_session_cookie_value(username)
def get(path,body=None,authenticated=True):
    headers={'Content-Type':'application/json'}
    if authenticated: headers['Cookie']=cookie
    with urlopen(Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=20) as r:
        data=r.read().decode(); return json.loads(data) if path.startswith('/api/') else data
assert 'content-editor.js' in get('/')
assert '回收站' in get('/content-editor.js')
assert 'ContentEditor.toolbar' in get('/views/characters.js')
assert 'insert-shot' in get('/views/episode.js')
name=get('/api/projects')['projects'][0]['name']; prefix='/api/projects/'+quote(name,safe='')
assert isinstance(get(prefix+'/content/trash')['items'],list)
for path,body,authenticated,code in [(prefix+'/content/trash',None,False,401),(prefix+'/content/delete',{},True,400)]:
    try: get(path,body,authenticated); raise AssertionError('invalid request accepted')
    except HTTPError as error: assert error.code==code
print('PASS HTTPS controls, trash endpoint, authentication and deletion confirmation; no project content modified')
