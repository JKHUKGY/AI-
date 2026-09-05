from pathlib import Path
import hashlib,json,tarfile
root=Path('/workspaces/AI-'); stage=root/'tmp/web-content-release'
files=['web/server/app.py','web/server/content_editor.py','web/frontend/api.js','web/frontend/index.html',
       'web/frontend/content-editor.js','web/frontend/views/characters.js','web/frontend/views/scenes.js',
       'web/frontend/views/episode.js','web/frontend/style.css','web/content/guide.md','web/README.md']
manifest={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in files}
(stage/'manifest.json').write_text(json.dumps(manifest,indent=2))
with tarfile.open(stage/'release.tar.gz','w:gz') as archive:
    for p in files: archive.add(root/p,arcname=p)
print('Packaged',len(files),'files')
