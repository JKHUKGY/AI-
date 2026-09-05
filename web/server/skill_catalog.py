"""Versioned catalog of repository skills; never accepts a client supplied path."""
import hashlib
from pathlib import Path
from router import ApiError

ROOT = Path(__file__).resolve().parents[2] / '.claude/skills'
LABELS = {
    'index': '项目导航',
    'short-drama-scout': '故事选题与大纲',
    'short-drama-storyboard': '分镜与人物场景设计',
    'short-drama-image-gen': '人物与场景出图',
    'short-drama-keyframe-gen': '关键帧生成与筛选',
    'loop-picture-generation': '图片生成与独立审查',
    'short-drama-video-gen': '视频镜头卡与提示词',
    'short-drama-ltx-export': 'LTX 提交前校验',
    'short-drama-ltx-generate': 'LTX 视频生成',
    'loop-video-generation': '视频生成与独立审查',
    'single-image-video-control': '单图可控视频',
    'short-drama-internal-test': '全流程联调',
    'minimax-h3-export': 'H3 提交前校验（已停用）',
    'minimax-h3-generate': 'H3 视频生成（已停用）',
}


def files(identifier):
    if identifier not in LABELS:
        raise ApiError(404, '没有这个 skill')
    root = ROOT / identifier
    result = []
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(root)
        if path.name == 'SKILL.md' or (rel.parts[0] in ('references', 'scripts') and
                path.suffix in ('.md', '.py', '.sh', '.json') and
                not any(s in path.name.lower() for s in ('remote_config', 'runpod_config', 'secret', 'credential'))):
            result.append(path)
    if root / 'SKILL.md' not in result:
        raise ApiError(503, '服务器尚未安装此 skill')
    return result


def get(identifier, include_text=False):
    paths = files(identifier)
    h = hashlib.sha256()
    for path in paths:
        h.update(str(path.relative_to(ROOT)).encode())
        h.update(b'\0' + path.read_bytes() + b'\0')
    text = (ROOT / identifier / 'SKILL.md').read_text()
    description = next((line[len('description:'):].strip() for line in text.splitlines()
                        if line.startswith('description:')), '')
    result = {'id': identifier, 'title': LABELS[identifier], 'description': description,
              'version': h.hexdigest(), 'files': len(paths),
              'enabled': not identifier.startswith('minimax-h3-'),
              'modes': ['user_choice', 'managed'] if identifier == 'short-drama-keyframe-gen' else ['user_choice']}
    if include_text:
        result['text'] = text
    return result


def catalog():
    return [get(identifier) for identifier in LABELS]


def instructions(identifier):
    """Include references for text-only planning; scripts stay in the execution package."""
    parts = []
    for path in files(identifier):
        if path.suffix == '.md':
            parts.append(f'\n--- {path.relative_to(ROOT)} ---\n{path.read_text()}')
    text = ''.join(parts)
    if len(text) > 300000:
        raise ApiError(503, 'Skill 文档过大，需要管理员拆分后调用')
    return text
