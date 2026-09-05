from pathlib import Path
import json, hashlib, shutil, subprocess, os, datetime
R=Path.cwd(); W=R/'tmp/cloud-archive-20260905'; D=json.loads((W/'plan.json').read_text()); stage=W/'upload'; stage.mkdir(exist_ok=True)
config=W/'rclone.conf'
fd=os.open(config,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
with os.fdopen(fd,'wb') as dst, (Path.home()/'.config/rclone/rclone.conf').open('rb') as src:shutil.copyfileobj(src,dst)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1048576):h.update(b)
 return h.hexdigest()
def run(*args):subprocess.run(['rclone','--config',str(config),*args],check=True)
manifest=R/'docs/archives/2026-09-05-v3-candidates.json'
def save():manifest.write_text(json.dumps(D,ensure_ascii=False,indent=2)+'\n')
try:
 for x in D['files']:
  src=R/x['source'];x['sha256']=digest(src)
  dst=stage/x['remote'];dst.parent.mkdir(parents=True,exist_ok=True)
  if not dst.is_symlink():dst.symlink_to(src)
  if x['pending_link']:x['pending_link_target']=os.readlink(R/x['pending_link'])
 D['status']='uploading';D['created_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
 run('copy',str(stage),D['remote'],'--copy-links','--checksum','--transfers','8','--checkers','8','--stats','30s','--stats-one-line','--log-level','NOTICE')
 run('check',str(stage),D['remote'],'--copy-links','--one-way','--checkers','8','--combined',str(W/'check.txt'))
 lines=(W/'check.txt').read_text().splitlines()
 assert len(lines)==len(D['files']) and all(l.startswith('= ') for l in lines),'remote check mismatch'
 D['status']='verified';D['verification']='rclone check: all remote file sizes and MD5 match local files; SHA-256 stored per file';save()
 run('copyto',str(manifest),D['remote']+'/归档清单.json','--checksum')
 for rel in D['protected']:
  assert (R/rel).is_file(), 'protected file missing before cleanup'
 # Verify every source again before removing any file.
 for x in D['files']:assert digest(R/x['source'])==x['sha256'],'source changed'
 for x in D['files']:
  if x['remove_local']:
   (R/x['source']).unlink();x['local_status']='removed'
  else:x['local_status']='retained_reference'
  if x['pending_link']:
   link=R/x['pending_link']
   if link.is_symlink() and os.readlink(link)==x['pending_link_target']:link.unlink()
 for rel in D['protected']:assert (R/rel).is_file(),'protected file missing after cleanup'
 D['status']='archived';D['files_removed']=sum(x['local_status']=='removed' for x in D['files']);D['bytes_freed']=sum(x['size'] for x in D['files'] if x['local_status']=='removed');save()
 run('copyto',str(manifest),D['remote']+'/归档清单.json','--checksum')
 print(json.dumps({'status':D['status'],'count':len(D['files']),'files_removed':D['files_removed'],'MiB_freed':D['bytes_freed']/1048576,'remote':D['remote']},ensure_ascii=False),flush=True)
finally:
 config.unlink(missing_ok=True)
