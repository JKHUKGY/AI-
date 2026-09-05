"""同一个图片任务的提示词版本；读取旧任务和生成记录，追加网站文字草稿。"""
import hashlib
import json
from pathlib import Path
import time

import state


def _id(prompt):
    return hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:24]


def versions(base_dir, job_id, store_path, key, fallback=None):
    items = {}
    def add(prompt, source, timestamp='', image=None):
        if not isinstance(prompt, str) or not prompt.strip():
            return
        prompt = prompt.strip()
        vid = _id(prompt)
        item = items.setdefault(vid, {'id': vid, 'prompt': prompt, 'source': source,
                                     'timestamp': timestamp, 'image_count': 0})
        if timestamp and timestamp > item['timestamp']:
            item.update(timestamp=timestamp, source=source)
        if image:
            item['image_count'] += 1
    for path in sorted(Path(base_dir).glob('*jobs*.json')):
        try:
            entries = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if isinstance(entries, dict):
            entries = entries.get('jobs', [])
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get('id', entry.get('job_id')) == job_id:
                    add(entry.get('prompt'), path.name)
    manifest = Path(base_dir) / 'manifest.append.jsonl'
    if manifest.is_file():
        for line in manifest.read_text(encoding='utf-8').splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get('job_id') == job_id:
                add(entry.get('prompt'), '图片生成记录', entry.get('timestamp') or '', entry.get('file'))
    for entry in state.load(store_path).get('prompt_versions', {}).get(key, []):
        add(entry['prompt'], entry['source'], entry['timestamp'])
    if fallback:
        add(fallback.get('prompt'), fallback.get('prompt_source') or '设计档案')
        add(fallback.get('original_prompt'), '历史原始提示词')
    return sorted(items.values(), key=lambda item: item['timestamp'], reverse=True)


def save(path, key, prompt, source, username):
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 30000:
        raise ValueError('提示词需为 1–30000 字的文本')
    prompt = prompt.strip()
    entry = {'id': _id(prompt), 'prompt': prompt, 'source': source,
             'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'), 'author': username, 'image_count': 0}
    def mutate(data):
        history = data.setdefault('prompt_versions', {}).setdefault(key, [])
        old = next((v for v in history if v['id'] == entry['id']), None)
        if old:
            return old
        history.append(entry)
        return entry
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return state._mutate(str(path), mutate)
