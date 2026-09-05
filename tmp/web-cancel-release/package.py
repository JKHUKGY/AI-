from pathlib import Path
import hashlib
import json
import tarfile

root = Path('/workspaces/AI-')
stage = root / 'tmp/web-cancel-release'
files = ['web/server/' + f for f in ('app.py', 'ai_prompt.py', 'generation_control.py', 'prompt_tasks.py',
    'project_setup.py', 'content_editor.py', 'jobs.py', 'state.py')]
files += ['web/frontend/' + f for f in ('api.js', 'shared.js', 'tasks.js', 'views/setup.js')]
files += ['web/content/guide.md', 'web/README.md']
manifest = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in files}
(stage / 'manifest.json').write_text(json.dumps(manifest, indent=2))
with tarfile.open(stage / 'release.tar.gz', 'w:gz') as archive:
    for p in files:
        archive.add(root / p, arcname=p)
print('Packaged', len(files), 'files')
