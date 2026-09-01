"""项目/资产发现：扫描 output/*/，不同项目目前处于流水线的不同阶段
（有的只做完分镜表，有的关键帧/视频目录还是空的），这里的函数都要对
"某个阶段目录/文件不存在"保持宽容，返回空结果而不是报错。
"""
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(REPO_ROOT, 'output')

_EPISODE_RE = re.compile(r'^ep(\d+)\.md$')


def project_dir(name):
    """路径穿越防护：只接受不含分隔符的纯目录名，且必须真实存在于 output/ 下。"""
    if not name or name != os.path.basename(name) or name in ('.', '..'):
        return None
    path = os.path.join(OUTPUT_DIR, name)
    if not os.path.isdir(path):
        return None
    return path


def list_episode_numbers(name):
    pdir = project_dir(name)
    if not pdir:
        return []
    sb = os.path.join(pdir, 'storyboard')
    if not os.path.isdir(sb):
        return []
    nums = []
    for fn in os.listdir(sb):
        m = _EPISODE_RE.match(fn)
        if m:
            nums.append(int(m.group(1)))
    return sorted(nums)


def list_projects():
    if not os.path.isdir(OUTPUT_DIR):
        return []
    projects = []
    for name in sorted(os.listdir(OUTPUT_DIR)):
        path = os.path.join(OUTPUT_DIR, name)
        if not os.path.isdir(path) or name.startswith('_') or name.startswith('.'):
            continue
        if not (os.path.isdir(os.path.join(path, 'storyboard')) or os.path.isdir(os.path.join(path, 'assets'))):
            continue
        projects.append({
            'name': name,
            'has_storyboard': os.path.isdir(os.path.join(path, 'storyboard')),
            'has_assets': os.path.isdir(os.path.join(path, 'assets')),
            'has_keyframes': os.path.isdir(os.path.join(path, 'keyframes')),
            'has_videos': os.path.isdir(os.path.join(path, 'videos')),
            'episodes': list_episode_numbers(name),
        })
    return projects


def _file_or_none(path):
    return path if os.path.isfile(path) else None


def episode_md_path(name, ep_no):
    pdir = project_dir(name)
    return _file_or_none(os.path.join(pdir, 'storyboard', f'ep{ep_no:02d}.md')) if pdir else None


def characters_md_path(name):
    pdir = project_dir(name)
    return _file_or_none(os.path.join(pdir, 'storyboard', 'characters.md')) if pdir else None


def scenes_md_path(name):
    pdir = project_dir(name)
    return _file_or_none(os.path.join(pdir, 'storyboard', 'scenes.md')) if pdir else None


def style_bible_md_path(name):
    pdir = project_dir(name)
    return _file_or_none(os.path.join(pdir, 'storyboard', 'style_bible.md')) if pdir else None


def keyframes_md_path(name, ep_no):
    pdir = project_dir(name)
    return _file_or_none(os.path.join(pdir, 'keyframes', f'ep{ep_no:02d}', 'keyframes.md')) if pdir else None


def video_jobs_md_path(name, ep_no):
    pdir = project_dir(name)
    return _file_or_none(os.path.join(pdir, 'videos', f'ep{ep_no:02d}', 'video_jobs.md')) if pdir else None


def _png_variants(job_path, job_id):
    if not os.path.isdir(job_path):
        return []
    return sorted(f for f in os.listdir(job_path) if f.startswith(job_id) and f.lower().endswith('.png'))


def list_asset_variants(name, prefix):
    """assets/ 下目录名以 prefix 开头的 job，各自列出变体图片的媒体相对路径
    （相对 output/，供 /media/<这个路径> 使用）。"""
    pdir = project_dir(name)
    if not pdir:
        return {}
    assets_dir = os.path.join(pdir, 'assets')
    if not os.path.isdir(assets_dir):
        return {}
    result = {}
    for job_id in sorted(os.listdir(assets_dir)):
        job_path = os.path.join(assets_dir, job_id)
        if not os.path.isdir(job_path) or not job_id.startswith(prefix):
            continue
        files = _png_variants(job_path, job_id)
        if files:
            result[job_id] = [f'{name}/assets/{job_id}/{f}' for f in files]
    return result


def list_keyframe_variants(name, ep_no):
    pdir = project_dir(name)
    if not pdir:
        return {}
    ep_dir = os.path.join(pdir, 'keyframes', f'ep{ep_no:02d}')
    if not os.path.isdir(ep_dir):
        return {}
    result = {}
    for job_id in sorted(os.listdir(ep_dir)):
        job_path = os.path.join(ep_dir, job_id)
        if not os.path.isdir(job_path):
            continue
        files = _png_variants(job_path, job_id)
        if files:
            result[job_id] = [f'{name}/keyframes/ep{ep_no:02d}/{job_id}/{f}' for f in files]
    return result


def list_video_files(name, ep_no):
    pdir = project_dir(name)
    if not pdir:
        return {}
    ep_dir = os.path.join(pdir, 'videos', f'ep{ep_no:02d}')
    if not os.path.isdir(ep_dir):
        return {}
    result = {}
    for fn in sorted(os.listdir(ep_dir)):
        if fn.lower().endswith('.mp4'):
            result[os.path.splitext(fn)[0]] = f'{name}/videos/ep{ep_no:02d}/{fn}'
    return result


def web_state_path(name):
    pdir = project_dir(name)
    if not pdir:
        return None
    d = os.path.join(pdir, '_web_state')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'review.json')


def web_state_logs_dir(name):
    pdir = project_dir(name)
    if not pdir:
        return None
    d = os.path.join(pdir, '_web_state', 'logs')
    os.makedirs(d, exist_ok=True)
    return d


def resolve_media_path(rel_path):
    """rel_path 形如 '<剧名>/assets/xxx/xxx_00.png'，校验规范化后仍落在
    output/ 目录内，返回绝对路径；不合法返回 None。"""
    if not rel_path or rel_path.startswith('/') or '..' in rel_path.split('/'):
        return None
    abs_path = os.path.normpath(os.path.join(OUTPUT_DIR, rel_path))
    if not (abs_path == OUTPUT_DIR or abs_path.startswith(OUTPUT_DIR + os.sep)):
        return None
    if not os.path.isfile(abs_path):
        return None
    return abs_path


def media_rel_from_manifest_path(p):
    """manifest.append.jsonl 里的 ref_images 记录的是当初调用
    generate_images.py 时传入的路径，可能是相对仓库根目录（'output/剧名/
    assets/...'）也可能是绝对路径，统一转换成本应用到处使用的、相对
    output/ 的媒体路径（'剧名/assets/...'），转换/校验失败返回 None。"""
    if not p:
        return None
    abs_path = p if os.path.isabs(p) else os.path.normpath(os.path.join(REPO_ROOT, p))
    abs_path = os.path.normpath(abs_path)
    if not abs_path.startswith(OUTPUT_DIR + os.sep):
        return None
    if not os.path.isfile(abs_path):
        return None
    return os.path.relpath(abs_path, OUTPUT_DIR).replace(os.sep, '/')
