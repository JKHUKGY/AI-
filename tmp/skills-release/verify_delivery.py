from pathlib import Path
import sys,json,hashlib,urllib.request,urllib.error
from urllib.parse import quote
sys.path.insert(0,'/home/deploy/AI-/web/server')
import auth,skill_catalog
base='https://scriptwriter-jia.northcentralus.cloudapp.azure.com'
cookie='sw_session='+auth.make_session_cookie_value('junzhenj',ttl=600)
p=Path('/home/deploy/AI-/tmp/skills-live-report.json');d=json.loads(p.read_text())
checks=[]
for item in d['execution']['result']['artifacts']:
 data=(Path('/home/deploy/AI-/output')/item).read_bytes()
 request=urllib.request.Request(base+'/media/'+quote(item,safe='/'),headers={'Cookie':cookie})
 with urllib.request.urlopen(request,timeout=20) as response:download=response.read()
 assert data==download
 checks.append({'path':item,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'https_match':True})
d['artifact_checks']=checks
d['deployed_versions']={x['id']:x['version'] for x in skill_catalog.catalog()}
d['original_test_script_unchanged']=(Path('/home/deploy/AI-/output')/d['project']/'source/script.txt').read_text().strip()=='小雨推开旧书店的门，向店主索取父亲留下的信封。信封里是一张旧矿场地图。'
assert d['original_test_script_unchanged']
p.write_text(json.dumps(d,ensure_ascii=False,indent=2))
print(json.dumps({'probes_passed':sum(x['status']=='done' for x in d['probes']),'execution':d['execution']['status'],'https_artifact_checks':checks,'original_unchanged':True},ensure_ascii=False))
