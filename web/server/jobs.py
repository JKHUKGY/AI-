"""重新生成子进程编排：复用 short-drama-image-gen 的
generate_images.py（免费、走本机已登录的 codex CLI），网站的"重新生成"
按钮只是拼一个单 job 的 jobs.json，起一个子进程，轮询状态。

注意：这个任务注册表是进程内内存态，服务重启就丢——可以接受，因为
generate_images.py 本身是幂等的"追加新变体"（按已有文件数续编号），重启
后剧本家重新点一次按钮不会破坏已有产出，只是丢失了正在跑的那次任务的
轮询句柄。
"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GENERATE_SCRIPT = os.path.join(
    REPO_ROOT, '.claude', 'skills', 'short-drama-image-gen', 'scripts', 'generate_images.py'
)

_registry = {}
_registry_lock = threading.Lock()


def find_last_job_meta(base_dir, job_id):
    """从 manifest.append.jsonl 里找这个 job_id 最近一次用过的 prompt +
    ref_images，给前端的重新生成表单预填。ref_images 关系到人物/场景一致性
    （比如某个表情图是拿角色三视图当参考生成的），不回填的话剧本家在网站上
    随手点"重新生成"会丢失这份一致性参考，跑出来的图大概率对不上脸/对不上
    场景。"""
    context = find_job_context(base_dir, job_id)
    return context['prompt'], context['ref_images']


def find_job_context(base_dir, job_id):
    """空白/仅选片的记录不能覆盖之前的完整提示词；缺失时回查同 ID 的 jobs。"""
    records = []
    manifest = Path(base_dir) / 'manifest.append.jsonl'
    if manifest.is_file():
        for line in manifest.read_text(encoding='utf-8').splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (isinstance(entry, dict) and entry.get('job_id') == job_id
                    and isinstance(entry.get('prompt'), str) and entry['prompt'].strip()):
                records.append(entry)
    if records:
        first, last = records[0], records[-1]
        return {'prompt': last['prompt'], 'original_prompt': first['prompt'],
                'ref_images': last.get('ref_images') or [], 'prompt_source': manifest.name}
    # 仅搜索当前 assets/ 或 epXX/ 的任务文件，不拿其他角色的提示词顶替。
    for path in sorted(Path(base_dir).glob('*jobs*.json'), key=lambda p: (p.stat().st_mtime, p.name), reverse=True):
        try:
            entries = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(entries, dict):
            entries = entries.get('jobs', [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if (isinstance(entry, dict) and entry.get('id', entry.get('job_id')) == job_id
                    and isinstance(entry.get('prompt'), str) and entry['prompt'].strip()):
                return {'prompt': entry['prompt'], 'original_prompt': entry['prompt'],
                        'ref_images': entry.get('ref_images') or [], 'prompt_source': path.name}
    return {'prompt': None, 'original_prompt': None, 'ref_images': [], 'prompt_source': None}


def _existing_files(job_dir, job_id):
    if not os.path.isdir(job_dir):
        return set()
    return {f for f in os.listdir(job_dir) if f.startswith(job_id) and f.lower().endswith('.png')}


def start_regenerate(out_dir, job_id, prompt, count, ref_images, log_dir):
    """out_dir：assets/ 或 keyframes/ep0X/ 这一级目录（脚本会在它下面建
    job_id/ 子目录续编号）；log_dir：临时 jobs.json + 子进程日志的落地目录
    （用 _web_state/logs，不要污染 assets/keyframes 目录）。"""
    if not prompt or not prompt.strip():
        raise ValueError('prompt 不能为空')
    count = max(1, min(int(count or 2), 6))
    ref_images = list(ref_images or [])

    job_dir = os.path.join(out_dir, job_id)
    before = _existing_files(job_dir, job_id)

    token = uuid.uuid4().hex[:12]
    os.makedirs(log_dir, exist_ok=True)
    tmp_jobs_path = os.path.join(log_dir, f'regen_{token}.json')
    with open(tmp_jobs_path, 'w', encoding='utf-8') as f:
        json.dump([{'id': job_id, 'prompt': prompt, 'count': count, 'ref_images': ref_images}], f, ensure_ascii=False)

    log_path = os.path.join(log_dir, f'regen_{token}.log')
    log_file = open(log_path, 'w', encoding='utf-8')

    cmd = [sys.executable, GENERATE_SCRIPT, tmp_jobs_path, '--out-dir', out_dir]
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=REPO_ROOT)

    with _registry_lock:
        _registry[token] = {
            'proc': proc,
            'log_file': log_file,
            'log_path': log_path,
            'job_dir': job_dir,
            'job_id': job_id,
            'before': before,
            'started_at': time.time(),
        }
    return token


def get_status(token):
    with _registry_lock:
        entry = _registry.get(token)
    if not entry:
        return None

    proc = entry['proc']
    ret = proc.poll()
    running = ret is None
    if not running and not entry['log_file'].closed:
        entry['log_file'].close()

    log_tail = ''
    if os.path.isfile(entry['log_path']):
        with open(entry['log_path'], encoding='utf-8', errors='replace') as f:
            log_tail = f.read()[-4000:]

    new_files = []
    if os.path.isdir(entry['job_dir']):
        now = _existing_files(entry['job_dir'], entry['job_id'])
        new_files = sorted(now - entry['before'])

    status = 'running' if running else ('done' if ret == 0 else 'failed')
    return {
        'token': token,
        'job_id': entry['job_id'],
        'status': status,
        'returncode': ret,
        'log_tail': log_tail,
        'new_files': new_files,
        'started_at': entry['started_at'],
    }
