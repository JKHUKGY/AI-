import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

root = Path('/home/deploy/AI-')
stage = Path(sys.argv[1])
manifest = json.loads((stage / 'manifest.json').read_text())
for path in (root / 'output').glob('*/_web_state/setup.json'):
    assert json.loads(path.read_text()).get('status') != 'running', 'Setup active; wait before restart'
for path in (root / 'output').glob('*/_web_state/prompt_tasks.json'):
    assert not any(t['status'] == 'running' for t in json.loads(path.read_text()).get('tasks', [])), 'Prompt active; wait before restart'
assert subprocess.run(['pgrep', '-f', '[g]enerate_images.py|[c]odex exec'], capture_output=True).returncode == 1, 'Generation active; wait before restart'
with tarfile.open(stage / 'release.tar.gz') as archive:
    assert set(archive.getnames()) == set(manifest)
    for member in archive.getmembers():
        assert member.isfile() and member.name.startswith('web/') and '..' not in Path(member.name).parts
        data = archive.extractfile(member).read()
        assert hashlib.sha256(data).hexdigest() == manifest[member.name]
        if member.name.endswith('.py'):
            compile(data, member.name, 'exec')
        path = stage / 'candidate' / member.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
for rel in manifest:
    path = root / rel
    if path.exists():
        backup = stage / 'backup' / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
for rel in manifest:
    target = root / rel
    temp = target.with_name(target.name + '.cancel-release')
    shutil.copy2(stage / 'candidate' / rel, temp)
    temp.replace(target)
subprocess.run(['sudo', 'systemctl', 'restart', 'scriptwriter-web'], check=True)
assert all(hashlib.sha256((root / p).read_bytes()).hexdigest() == h for p, h in manifest.items())
print('Deployed and verified', len(manifest), 'files; backup:', stage / 'backup')
