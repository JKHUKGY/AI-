from pathlib import Path
import tarfile,json,subprocess
r=Path('/home/deploy/AI-'); package=r/'tmp/skills-release-20260905.tar.gz'
active=0
for p in (r/'output').glob('*/_web_state/prompt_tasks.json'):
 try:active+=sum(t.get('status')=='running' for t in json.loads(p.read_text()).get('tasks',[]))
 except Exception:pass
print('active_text_tasks',active,flush=True)
if active:raise SystemExit('Active tasks; defer service restart')
with tarfile.open(package) as src:
 members=src.getmembers()
 assert all(m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
 backup=r/'tmp/skills-before-20260905.tar.gz'
 if backup.exists():raise SystemExit('Backup exists; inspect before redeploy')
 with tarfile.open(backup,'w:gz') as dst:
  for m in members:
   p=r/m.name
   if p.is_file():dst.add(p,arcname=m.name)
 src.extractall(r,filter='data')
subprocess.run(['python3','-m','unittest','discover','-s','web/server/tests','-p','test_skills.py'],cwd=r,check=True)
subprocess.run(['sudo','systemctl','restart','scriptwriter-web'],check=True)
subprocess.run(['systemctl','is-active','scriptwriter-web'],check=True)
print('deployed',len(members),flush=True)
