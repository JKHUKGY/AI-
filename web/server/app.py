#!/usr/bin/env python3
"""剧本家协作网站服务端入口。

    python3 web/server/app.py [--port 8000] [--host 0.0.0.0]

同一个端口既提供前端静态页面（web/frontend/），也提供 /api/* JSON 接口和
/media/* 图片视频，浏览器同源访问，不需要处理 CORS。局域网内其它设备用
这台机器的局域网 IP + 端口访问即可。"重新生成"按钮依赖这台机器上
`codex login` 过的状态，所以这个服务要在装了 Codex CLI 并登录过的机器上
启动（也就是当前跑 Claude Code 的这台机器），剧本家自己的设备只需要一个
浏览器。
"""
import argparse
import json
import mimetypes
import os
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_prompt
import approvals
import auth
import jobs
import md_render
import md_tables
import media
import projects
import project_setup
import prompt_history
import prompt_tasks
import help_chat
import content_editor
import state
from router import ApiError, Ctx, Router

mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(WEB_DIR, 'frontend')
CONTENT_DIR = os.path.join(WEB_DIR, 'content')

router = Router()


@router.post(r'/api/help/question')
def api_help_question(ctx, params):
    return help_chat.answer(ctx.username, ctx.json())


@router.get(r'/api/projects/(?P<name>[^/]+)/content/trash')
def api_content_trash(ctx, params):
    return {'items':content_editor.trash(_project_or_404(params['name']))}


@router.post(r'/api/projects/(?P<name>[^/]+)/content/(?P<action>add|preview-delete|delete|restore)')
def api_content_change(ctx, params):
    root = _project_or_404(params['name'])
    body = ctx.json()
    if not isinstance(body, dict): raise ApiError(400, '请求体必须为对象')
    action = params['action']
    if action == 'add': return content_editor.add(root, body, ctx.username)
    if action == 'preview-delete': return content_editor.preview(root, body)
    if action == 'delete': return content_editor.remove(root, body, ctx.username)
    return content_editor.restore(root, body.get('id'), ctx.username)

_CHAR_TITLE_RE = re.compile(r'^(?:\d+\.|角色[一二三四五六七八九十百千\d]+[:：])\s*([^（(—－]+)')
_CHAR_ALIAS_RE = re.compile(r'[（(][^）)]*?["“‘\']([^"”’\'）)]+)["”’\']')
_SCENE_TITLE_RE = re.compile(r'^(SC\d+)')


def _project_or_404(name):
    pdir = projects.project_dir(name)
    if not pdir:
        raise ApiError(404, f'项目不存在: {name}')
    return pdir


def _read_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _write_text(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _state_path(name):
    return projects.web_state_path(name)


def _augment_variants(variants, selections):
    return {jid: {'files': files, 'selected': selections.get(jid)} for jid, files in variants.items()}


def _apply_shot_patch(md_path, rel_file, ep, shot_id, updates):
    text = _read_text(md_path)
    try:
        new_text, old_row = md_tables.set_cell(text, '镜号', shot_id, updates)
    except ValueError as e:
        raise ApiError(400, str(e))
    _write_text(md_path, new_text)
    return old_row


# ---------------- guide ----------------

@router.get(r'/api/guide')
def api_guide(ctx, params):
    text = _read_text(os.path.join(CONTENT_DIR, 'guide.md'))
    return {'html': md_render.render(text)}


# ---------------- projects ----------------

@router.get(r'/api/projects')
def api_projects(ctx, params):
    allowed = auth.allowed_projects(ctx.username)
    all_projects = projects.list_projects()
    if allowed is None:
        return {'projects': all_projects}
    return {'projects': [p for p in all_projects if p['name'] in allowed or p.get('owner') == ctx.username]}


@router.post(r'/api/projects')
def api_create_project(ctx, params):
    try:
        name = project_setup.create(ctx.json(), ctx.username)
    except FileExistsError:
        raise ApiError(409, '同名项目已存在，请换一个项目名；不会覆盖旧项目')
    except ValueError as exc:
        raise ApiError(400, str(exc))
    return {'name': name}


@router.get(r'/api/projects/(?P<name>[^/]+)/setup')
def api_setup(ctx, params):
    pdir = _project_or_404(params['name'])
    progress = project_setup.status(pdir)
    if not progress:
        return {'setup': None}
    tasks_path = os.path.join(pdir, 'assets', 'jobs_initial.json')
    tasks = json.loads(_read_text(tasks_path)) if os.path.isfile(tasks_path) else []
    tasks = [t for t in tasks if not content_editor.disabled(pdir, t['id'], 'asset', None)]
    return {'setup': progress, 'metadata': project_setup.metadata(pdir), 'image_tasks': tasks,
            'gpu': {'status': 'needs_plan', 'message': '尚未授权租卡。先完成基准图、关键帧和视频镜头卡，再提交机型、单价、预计时长、预算上限与关机方案供用户审批。'}}


@router.post(r'/api/projects/(?P<name>[^/]+)/setup/start')
def api_setup_start(ctx, params):
    try:
        return {'setup': project_setup.start(_project_or_404(params['name']))}
    except ai_prompt.BusyError as exc:
        raise ApiError(429, str(exc))
    except ValueError as exc:
        raise ApiError(400, str(exc))


@router.get(r'/api/projects/(?P<name>[^/]+)/setup/file')
def api_setup_file(ctx, params):
    pdir = _project_or_404(params['name'])
    progress = project_setup.status(pdir) or {}
    rel = ctx.query_one('path')
    if not rel or rel not in progress.get('files', []):
        raise ApiError(404, '该文字文件不在项目基础文件清单中')
    return {'path': rel, 'text': _read_text(os.path.join(pdir, rel))}


# ---------------- characters / scenes / style bible ----------------

def _parse_named_sections(text, title_re):
    """按 title_re（角色序号/场景编号）把二级标题段落分成"正式条目"和
    "杂项"（比如"画风锚点"这种不匹配编号规则的段落）。杂项并入 intro，
    不要混进角色/场景列表，否则前端按下标对应资产图片会全部错位一格。"""
    sections = md_render.split_h2_sections(text)
    intro_parts = []
    named = []
    for sec in sections:
        title = sec['title']
        if title is None:
            intro_parts.append(sec['body'])
            continue
        m = title_re.match(title)
        if not m:
            intro_parts.append(f'## {title}\n\n{sec["body"]}')
            continue
        named.append({'title': title, 'key': m.group(1).strip(), 'html': md_render.render(sec['body']), 'body': sec['body']})
    return intro_parts, named


@router.get(r'/api/projects/(?P<name>[^/]+)/characters')
def api_characters(ctx, params):
    name = params['name']
    _project_or_404(name)
    path = projects.characters_md_path(name)
    if not path:
        return {'exists': False}
    intro_parts, sections = _parse_named_sections(_read_text(path), _CHAR_TITLE_RE)
    selections = state.get_selections(_state_path(name))
    for sec in sections:
        prefix = sec['key'] or sec['title']
        variants = projects.list_asset_variants(name, prefix)
        if not variants:
            # 有些角色的档案标题写的是本名，但资产目录用的是剧情里的化名/
            # 曾用名（比如"顾晚晴（校园化名"陆晚"）"，资产目录是"陆晚_xxx"），
            # 本名匹配不到图时，退而尝试标题括号里引号包起来的别名。
            for alias in _CHAR_ALIAS_RE.findall(sec['title']):
                variants = projects.list_asset_variants(name, alias.strip())
                if variants:
                    break
        sec['variants'] = _augment_variants(variants, selections)
        if not sec['variants']:
            sec['variants'] = {prefix + '_三视图': {'files':[], 'selected':None}}
    return {
        'exists': True,
        'intro_html': '\n'.join(md_render.render(p) for p in intro_parts),
        'characters': sections,
    }


def _patch_named_section(md_path, file_rel, name, title, new_text, edit_note):
    text = _read_text(md_path)
    old_section = next((s for s in md_render.split_h2_sections(text) if s['title'] == title), None)
    try:
        new_full = md_render.set_h2_section_body(text, title, new_text)
    except ValueError as e:
        raise ApiError(404, str(e))
    _write_text(md_path, new_full)
    old_body = old_section['body'] if old_section else None
    state.add_edit(_state_path(name), file_rel, edit_note, old_body, new_text, row_key={'标题': title})
    return {'html': md_render.render(new_text)}


@router.patch(r'/api/projects/(?P<name>[^/]+)/characters/(?P<title>[^/]+)')
def api_patch_character(ctx, params):
    name = params['name']
    _project_or_404(name)
    title = unquote(params['title'])
    path = projects.characters_md_path(name)
    if not path:
        raise ApiError(404, '这个项目还没有人物设计文档')
    body = ctx.json()
    new_text = body.get('text')
    if new_text is None:
        raise ApiError(400, '需要 text')
    return _patch_named_section(path, 'storyboard/characters.md', name, title, new_text, '人物描述正文')


@router.get(r'/api/projects/(?P<name>[^/]+)/scenes')
def api_scenes(ctx, params):
    name = params['name']
    _project_or_404(name)
    path = projects.scenes_md_path(name)
    if not path:
        return {'exists': False}
    intro_parts, sections = _parse_named_sections(_read_text(path), _SCENE_TITLE_RE)
    selections = state.get_selections(_state_path(name))
    for sec in sections:
        prefix = sec['key'] or sec['title']
        sec['variants'] = _augment_variants(projects.list_asset_variants(name, prefix), selections)
        if not sec['variants']:
            sec['variants'] = {prefix + '_A主机位': {'files':[], 'selected':None}}
    return {
        'exists': True,
        'intro_html': '\n'.join(md_render.render(p) for p in intro_parts),
        'scenes': sections,
    }


@router.patch(r'/api/projects/(?P<name>[^/]+)/scenes/(?P<title>[^/]+)')
def api_patch_scene(ctx, params):
    name = params['name']
    _project_or_404(name)
    title = unquote(params['title'])
    path = projects.scenes_md_path(name)
    if not path:
        raise ApiError(404, '这个项目还没有场景设计文档')
    body = ctx.json()
    new_text = body.get('text')
    if new_text is None:
        raise ApiError(400, '需要 text')
    return _patch_named_section(path, 'storyboard/scenes.md', name, title, new_text, '场景描述正文')


@router.get(r'/api/projects/(?P<name>[^/]+)/style-bible')
def api_style_bible(ctx, params):
    name = params['name']
    _project_or_404(name)
    path = projects.style_bible_md_path(name)
    if not path:
        return {'exists': False}
    text = _read_text(path)
    return {'exists': True, 'html': md_render.render(text), 'text': text}


@router.patch(r'/api/projects/(?P<name>[^/]+)/style-bible')
def api_patch_style_bible(ctx, params):
    name = params['name']
    _project_or_404(name)
    path = projects.style_bible_md_path(name)
    if not path:
        raise ApiError(404, '这个项目还没有风格简报')
    body = ctx.json()
    new_text = body.get('text')
    if new_text is None:
        raise ApiError(400, '需要 text')
    old_text = _read_text(path)
    _write_text(path, new_text)
    state.add_edit(_state_path(name), 'storyboard/style_bible.md', '风格简报全文', old_text, new_text)
    return {'html': md_render.render(new_text)}


# ---------------- episodes ----------------

@router.get(r'/api/projects/(?P<name>[^/]+)/episodes')
def api_episodes(ctx, params):
    name = params['name']
    _project_or_404(name)
    kf = projects.list_media_episode_numbers(name, 'keyframes')
    vd = projects.list_media_episode_numbers(name, 'videos')
    return {
        'episodes': projects.list_episode_numbers(name),
        'keyframe_episodes': kf,
        'video_episodes': vd,
    }


@router.get(r'/api/projects/(?P<name>[^/]+)/episodes/(?P<ep>\d+)')
def api_episode_detail(ctx, params):
    name = params['name']
    ep = int(params['ep'])
    _project_or_404(name)
    path = projects.episode_md_path(name, ep)
    if not path:
        raise ApiError(404, f'第{ep}集分镜表不存在')
    text = _read_text(path)
    table = md_tables.parse_table(text)
    if not table:
        raise ApiError(500, '分镜表文件里没有找到表格')
    lines = text.splitlines()
    meta_html = md_render.render('\n'.join(lines[:table['header_idx']]))
    tail_html = md_render.render('\n'.join(lines[table['end']:]))
    return {'header': table['header'], 'rows': table['rows'], 'meta_html': meta_html, 'tail_html': tail_html}


@router.patch(r'/api/projects/(?P<name>[^/]+)/episodes/(?P<ep>\d+)/shots/(?P<shot>[^/]+)')
def api_episode_patch(ctx, params):
    name = params['name']
    ep = int(params['ep'])
    shot_no = unquote(params['shot'])
    _project_or_404(name)
    path = projects.episode_md_path(name, ep)
    if not path:
        raise ApiError(404, f'第{ep}集分镜表不存在')
    updates = ctx.json()
    if not isinstance(updates, dict) or not updates:
        raise ApiError(400, '请求体需要是 {字段: 新值} 的对象')
    old_row = _apply_shot_patch(path, f'storyboard/ep{ep:02d}.md', ep, shot_no, updates)
    sp = _state_path(name)
    for field, new_value in updates.items():
        state.add_edit(sp, f'storyboard/ep{ep:02d}.md', field, old_row.get(field), new_value, row_key={'镜号': shot_no})
    return {'ok': True, 'old_row': old_row, 'updates': updates}


# ---------------- keyframes ----------------

# keyframes.md 的表头在不同项目/不同时期并不统一（早期是"对应画面描述/选中文件
# 路径"，新版是"这一镜要讲成什么（验收依据）/选中文件"，新版还多了"机位"列），
# 镜号也有"1"和"镜1"两种写法。前端不该去猜这些，所以在这里统一归一化成固定
# 字段，认不出来的列原样放进 notes，不丢信息。
_KF_COLS = (
    ('scene', ('场景',)),
    ('camera', ('机位',)),
    ('characters', ('出场人物', '人物')),
    ('description', ('对应画面描述', '画面描述', '讲成什么', '描述')),
    ('file', ('选中文件路径', '选中文件')),
    ('grade', ('分级',)),
)


def _pick_col(header, aliases, used):
    for a in aliases:
        if a in header and a not in used:
            return a
    for h in header:
        if h in used:
            continue
        if any(a in h for a in aliases):
            return h
    return None


def _normalize_keyframe_rows(table, ep, variants):
    """把 keyframes.md 的表格行 + 磁盘上的图片对齐成一条条"镜"。

    镜号可能写成 "1" 或 "镜1"，只取其中的数字来拼 job_id，避免出现
    `ep01_镜镜1` 这种对不上目录名、导致整集图片一张都挂不到镜上的情况。
    """
    header = table['header'] if table else []
    used = {'镜号'}
    colmap = {}
    for field, aliases in _KF_COLS:
        col = _pick_col(header, aliases, used)
        if col:
            colmap[field] = col
            used.add(col)
    note_cols = [h for h in header if h not in used]

    shots = []
    matched = set()
    for row in (table['rows'] if table else []):
        raw_no = (row.get('镜号') or '').strip()
        m = re.search(r'\d+', raw_no)
        if not m:
            continue
        num = int(m.group())
        job_id = f'ep{ep:02d}_镜{num:02d}'
        job = variants.get(job_id)
        if job:
            matched.add(job_id)
        listed = (row.get(colmap.get('file', '')) or '').strip().strip('`')
        shots.append({
            'shot_no': raw_no or str(num),
            'shot_num': num,
            'job_id': job_id,
            'scene': row.get(colmap.get('scene', ''), ''),
            'camera': (row.get(colmap.get('camera', ''), '') or '').strip('`'),
            'characters': row.get(colmap.get('characters', ''), ''),
            'description': row.get(colmap.get('description', ''), ''),
            'grade': row.get(colmap.get('grade', ''), ''),
            'listed_file': listed.split('/')[-1] if listed else '',
            'notes': [{'label': c, 'value': row[c]} for c in note_cols if row.get(c)],
            'files': (job or {}).get('files', []),
            'selected': (job or {}).get('selected'),
        })

    orphans = {jid: variants[jid] for jid in variants if jid not in matched}
    return shots, orphans


@router.get(r'/api/projects/(?P<name>[^/]+)/keyframes/(?P<ep>\d+)')
def api_keyframes(ctx, params):
    name = params['name']
    ep = int(params['ep'])
    _project_or_404(name)
    path = projects.keyframes_md_path(name, ep)
    variants = _augment_variants(projects.list_keyframe_variants(name, ep), state.get_selections(_state_path(name)))
    if not path:
        # 还没写 keyframes.md 但图已经出了（生成中途/老项目），也要能看图，
        # 这时每个 job 目录自己就是一"镜"。
        shots, orphans = [], variants
        return {'exists': False, 'header': [], 'rows': [], 'variants': variants,
                'shots': shots, 'orphan_jobs': orphans}
    table = md_tables.parse_table(_read_text(path))
    shots, orphans = _normalize_keyframe_rows(table, ep, variants)
    return {
        'exists': True,
        'header': table['header'] if table else [],
        'rows': table['rows'] if table else [],
        'variants': variants,
        'shots': shots,
        'orphan_jobs': orphans,
    }


# ---------------- videos ----------------

@router.get(r'/api/projects/(?P<name>[^/]+)/videos/(?P<ep>\d+)')
def api_videos(ctx, params):
    name = params['name']
    ep = int(params['ep'])
    _project_or_404(name)
    path = projects.video_jobs_md_path(name, ep)
    video_files = projects.list_video_files(name, ep)
    if not path:
        return {'exists': False, 'header': [], 'rows': [], 'video_files': video_files}
    table = md_tables.parse_table(_read_text(path))
    return {'exists': True, 'header': table['header'] if table else [], 'rows': table['rows'] if table else [], 'video_files': video_files}


@router.patch(r'/api/projects/(?P<name>[^/]+)/videos/(?P<ep>\d+)/shots/(?P<shot>[^/]+)')
def api_video_patch(ctx, params):
    name = params['name']
    ep = int(params['ep'])
    shot_id = unquote(params['shot'])
    _project_or_404(name)
    path = projects.video_jobs_md_path(name, ep)
    if not path:
        raise ApiError(404, f'第{ep}集视频清单不存在')
    updates = ctx.json()
    if not isinstance(updates, dict) or not updates:
        raise ApiError(400, '请求体需要是 {字段: 新值} 的对象')
    old_row = _apply_shot_patch(path, f'videos/ep{ep:02d}/video_jobs.md', ep, shot_id, updates)
    sp = _state_path(name)
    for field, new_value in updates.items():
        state.add_edit(sp, f'videos/ep{ep:02d}/video_jobs.md', field, old_row.get(field), new_value, row_key={'镜号': shot_id})
    return {'ok': True, 'old_row': old_row, 'updates': updates}


@router.post(r'/api/projects/(?P<name>[^/]+)/videos/(?P<ep>\d+)/request_regen')
def api_video_request_regen(ctx, params):
    name = params['name']
    ep = int(params['ep'])
    _project_or_404(name)
    body = ctx.json()
    shot_id = body.get('shot_no')
    if not shot_id:
        raise ApiError(400, '需要 shot_no（镜号）')
    entry = state.add_regen_job(
        _state_path(name),
        target={'type': 'video', 'episode': ep, 'shot_no': shot_id},
        note=body.get('note', ''),
        status='pending_human',
        kind='video',
    )
    return {'regen_job': entry}


# ---------------- comments ----------------

@router.get(r'/api/projects/(?P<name>[^/]+)/comments')
def api_comments_list(ctx, params):
    name = params['name']
    _project_or_404(name)
    resolved_param = ctx.query_one('resolved')
    resolved = None
    if resolved_param is not None:
        resolved = resolved_param.lower() in ('1', 'true', 'yes')
    return {'comments': state.list_comments(_state_path(name), resolved=resolved)}


@router.post(r'/api/projects/(?P<name>[^/]+)/comments')
def api_comments_add(ctx, params):
    name = params['name']
    _project_or_404(name)
    body = ctx.json()
    target = body.get('target')
    text = body.get('text')
    if not target or not text:
        raise ApiError(400, '需要 target 和 text')
    entry = state.add_comment(_state_path(name), target, text, body.get('author'))
    return {'comment': entry}


@router.post(r'/api/projects/(?P<name>[^/]+)/comments/(?P<cid>[^/]+)/resolve')
def api_comments_resolve(ctx, params):
    name = params['name']
    _project_or_404(name)
    try:
        entry = state.resolve_comment(_state_path(name), params['cid'])
    except ValueError as e:
        raise ApiError(404, str(e))
    return {'comment': entry}


# ---------------- selections ----------------

@router.get(r'/api/projects/(?P<name>[^/]+)/select')
def api_select_get(ctx, params):
    name = params['name']
    _project_or_404(name)
    return {'selections': state.get_selections(_state_path(name))}


@router.post(r'/api/projects/(?P<name>[^/]+)/select')
def api_select_post(ctx, params):
    name = params['name']
    _project_or_404(name)
    body = ctx.json()
    job_id = body.get('job_id')
    filename = body.get('file')
    if not job_id or not filename:
        raise ApiError(400, '需要 job_id 和 file')
    return {'selections': state.set_selection(_state_path(name), job_id, filename)}


# ---------------- regenerate (image / keyframe only, free & local) ----------------

def _out_dir_for_kind(pdir, kind, episode):
    if kind not in ('asset', 'keyframe'):
        raise ApiError(400, 'kind 必须是 asset 或 keyframe')
    if kind == 'keyframe':
        if not episode or not str(episode).isdigit() or int(episode) < 1:
            raise ApiError(400, 'keyframe 类型需要 episode')
        return os.path.join(pdir, 'keyframes', f'ep{int(episode):02d}')
    return os.path.join(pdir, 'assets')


def _prompt_context(ctx, params, job_id, kind, episode):
    name = params['name']
    pdir = _project_or_404(name)
    if not isinstance(job_id, str) or not job_id or job_id != os.path.basename(job_id) or job_id in ('.', '..'):
        raise ApiError(400, '需要合法的 job_id')
    out_dir = _out_dir_for_kind(pdir, kind, episode)
    if content_editor.disabled(pdir, job_id, kind, episode):
        raise ApiError(409, '该条目已移入回收站，请先恢复后再生成')
    context = jobs.find_job_context(out_dir, job_id)
    variants = {}
    group_title = job_id
    if kind == 'asset':
        for handler, key in ((api_characters, 'characters'), (api_scenes, 'scenes')):
            data = handler(ctx, params)
            section = next((s for s in data.get(key, []) if job_id in s['variants']), None)
            if section:
                variants = section['variants']
                group_title = section['title']
                if not context['prompt']:
                    # 没有生成记录/任务时，使用该栏目的完整设计档案（含风格锚点）。
                    path = projects.characters_md_path(name) if key == 'characters' else projects.scenes_md_path(name)
                    intro, _ = _parse_named_sections(_read_text(path), _CHAR_TITLE_RE if key == 'characters' else _SCENE_TITLE_RE)
                    context.update(prompt='\n\n'.join(intro + [section['body']]),
                                   prompt_source=f'storyboard/{os.path.basename(path)} · {group_title}')
                    context['original_prompt'] = context['prompt']
                break
        if not variants:
            own = projects.list_asset_variants(name, job_id).get(job_id, [])
            variants = {job_id: {'files': own}}
    else:
        variants = {jid: {'files': files} for jid, files in projects.list_keyframe_variants(name, int(episode)).items()}
        group_title = f'第 {int(episode)} 集关键帧'
    refs = []
    for raw in context['ref_images']:
        rel = projects.media_rel_from_manifest_path(raw)
        if rel and rel.split('/', 1)[0] == name and rel not in refs:
            refs.append(rel)
    options = {}
    for jid, data in variants.items():
        for rel in data['files']:
            options[rel] = {'path': rel, 'job_id': jid,
                            'selected': os.path.basename(rel) == data.get('selected'),
                            'previous': rel in refs}
    for rel in refs:
        options.setdefault(rel, {'path': rel, 'job_id': rel.split('/')[-2], 'selected': False, 'previous': True})
    context.update(ref_images=refs, reference_group=group_title,
                   reference_options=sorted(options.values(), key=lambda item: (
                       not item['previous'], not item['selected'], item['job_id'] != job_id, item['path'])))
    history_path, history_key = _history_location(pdir, job_id, kind, episode)
    context['history'] = prompt_history.versions(out_dir, job_id, history_path, history_key, context)
    return context


def _history_location(pdir, job_id, kind, episode):
    return os.path.join(pdir, '_web_state', 'prompt_history.json'), f'{kind}:{int(episode) if kind == "keyframe" else 0}:{job_id}'


@router.post(r'/api/projects/(?P<name>[^/]+)/prompt_history')
def api_save_prompt(ctx, params):
    body = ctx.json()
    if not isinstance(body, dict):
        raise ApiError(400, '请求体必须为对象')
    job_id, kind, episode = body.get('job_id'), body.get('kind', 'asset'), body.get('episode')
    _prompt_context(ctx, params, job_id, kind, episode)
    path, key = _history_location(_project_or_404(params['name']), job_id, kind, episode)
    try:
        return {'version': prompt_history.save(path, key, body.get('prompt'), '手动保存', ctx.username)}
    except ValueError as exc:
        raise ApiError(400, str(exc))


def _reference_paths(name, refs):
    if not isinstance(refs, list) or len(refs) > 6:
        raise ApiError(400, '参考图必须是数组，最多选择 6 张')
    result = []
    project_root = os.path.realpath(_project_or_404(name)) + os.sep
    for rel in refs:
        if not isinstance(rel, str) or rel.split('/', 1)[0] != name:
            raise ApiError(400, '只能选择当前项目的参考图')
        path = projects.resolve_media_path(rel)
        if (not path or not os.path.realpath(path).startswith(project_root)
                or os.path.splitext(path)[1].lower() not in ('.png', '.jpg', '.jpeg', '.webp')):
            raise ApiError(400, '参考图不存在或不是有效图片，请重新选择')
        if path not in result:
            result.append(path)
    return result


@router.get(r'/api/projects/(?P<name>[^/]+)/last_prompt')
def api_last_prompt(ctx, params):
    job_id = ctx.query_one('job_id')
    kind = ctx.query_one('kind', 'asset')
    episode = ctx.query_one('episode')
    return _prompt_context(ctx, params, job_id, kind, episode)


@router.post(r'/api/projects/(?P<name>[^/]+)/ai_rewrite_prompt')
def api_ai_rewrite_prompt(ctx, params):
    """结合选定历史原文改写提示词并保存文字版本，不触发图片生成。"""
    name = params['name']
    pdir = _project_or_404(name)
    body = ctx.json()
    if not isinstance(body, dict):
        raise ApiError(400, '请求体必须是 JSON 对象')
    job_id = body.get('job_id')
    kind = body.get('kind', 'asset')
    episode = body.get('episode')
    instruction = body.get('instruction', '')
    mode = body.get('mode', 'edit')
    if mode not in ('fresh', 'edit'):
        raise ApiError(400, '请选择完全重新生成或参考原文局部修改')
    current_prompt = body.get('current_prompt', '')
    if not isinstance(instruction, str) or not isinstance(current_prompt, str):
        raise ApiError(400, 'instruction 和 current_prompt 必须是文本')
    instruction = instruction.strip()
    current_prompt = current_prompt.strip()
    if not isinstance(job_id, str) or not job_id.strip() or not instruction:
        raise ApiError(400, '需要 job_id 和 instruction')

    context = _prompt_context(ctx, params, job_id, kind, episode)
    chosen = body.get('prompt_version_id')
    if chosen and mode == 'edit':
        version = next((v for v in context['history'] if v['id'] == chosen), None)
        if not version:
            raise ApiError(400, '历史版本不存在，请重新选择')
        context.update(original_prompt=version['prompt'], prompt_source=version['source'])
    current_prompt = current_prompt or context['prompt'] or ''
    if not current_prompt and mode == 'edit':
        raise ApiError(400, '没有找到历史提示词或角色设计，请先补充完整提示词再改写')

    try:
        new_prompt = (ai_prompt.fresh(instruction) if mode == 'fresh' else
                      ai_prompt.rewrite(current_prompt, instruction,
                                        original_prompt=context['original_prompt'] or current_prompt))
    except ValueError as e:
        raise ApiError(400, str(e))
    except ai_prompt.BusyError as e:
        raise ApiError(429, str(e))
    except RuntimeError as e:
        raise ApiError(502, f'Codex 写提示词失败：{e}')
    history_path, history_key = _history_location(pdir, job_id, kind, episode)
    version = prompt_history.save(history_path, history_key, new_prompt, 'Codex 全新生成' if mode == 'fresh' else 'Codex 改写', ctx.username)
    return {'prompt': new_prompt, 'provider': 'codex', 'mode': mode, 'prompt_source': None if mode == 'fresh' else context['prompt_source'], 'version': version}


@router.post(r'/api/projects/(?P<name>[^/]+)/prompt_tasks')
def api_start_prompt_task(ctx, params):
    body = ctx.json()
    if not isinstance(body, dict):
        raise ApiError(400, '请求体必须为对象')
    jid, kind, ep = body.get('job_id'), body.get('kind', 'asset'), body.get('episode')
    _prompt_context(ctx, params, jid, kind, ep)
    if (body.get('mode', 'edit') not in ('fresh', 'edit') or not isinstance(body.get('instruction'), str)
            or not 1 <= len(body['instruction'].strip()) <= 4000):
        raise ApiError(400, '请选择生成方式并填写 1–4000 字描述')
    try:
        task = prompt_tasks.start(_project_or_404(params['name']),
            {'type': kind, 'job_id': jid, 'episode': int(ep) if kind == 'keyframe' else None},
            ctx.username, lambda: api_ai_rewrite_prompt(ctx, params))
        return {'task': task}
    except ai_prompt.BusyError as exc:
        raise ApiError(429, str(exc))


@router.get(r'/api/tasks')
def api_tasks(ctx, params):
    result = []
    for project in api_projects(ctx, {})['projects']:
        name = project['name']
        pdir = _project_or_404(name)
        result.extend({**t, 'project': name} for t in prompt_tasks.list_tasks(pdir))
        for entry in state.list_regen_jobs(_state_path(name)):
            if entry.get('kind') != 'image' or not entry.get('token'):
                continue
            task = dict(entry)
            live = jobs.get_status(task['token'])
            if live:
                task.update(live)
                if live['status'] != entry['status'] or live.get('new_files', []) != entry.get('new_files', []):
                    state.update_regen_job(_state_path(name), entry['id'], **{k: v for k, v in live.items() if k != 'job_id'})
            elif task['status'] == 'running':
                task.update(status='interrupted', error='服务重启后无法追踪原进程；请先检查图库，任务记录已保留')
            result.append({**task, 'id': entry['id'], 'project': name, 'kind': 'image'})
    return {'tasks': result}


@router.post(r'/api/projects/(?P<name>[^/]+)/regenerate/preview')
def api_regenerate_preview(ctx, params):
    name = params['name']
    pdir = _project_or_404(name)
    body = ctx.json()
    if not isinstance(body, dict):
        raise ApiError(400, '请求体必须为对象')
    job_id = body.get('job_id')
    kind = body.get('kind', 'asset')
    episode = body.get('episode')
    context = _prompt_context(ctx, params, job_id, kind, episode)
    prompt = body.get('prompt') or context['prompt']
    if not prompt:
        raise ApiError(400, '没有提供 prompt，历史记录里也没找到这个 job 上一次用过的 prompt，请手动填写')

    # 剧本家不显式传 ref_images 时，默认复用这个 job 上一次生成时用过的参考图
    # （通常是角色三视图/场景基准图），避免"重新生成"悄悄丢失一致性参考、
    # 跑出一张对不上脸/对不上场景的图。显式传空数组 [] 表示确实要改成纯文生图。
    if 'ref_images' in body:
        ref_images_rel = body.get('ref_images')
    else:
        # manifest 里存的是当初调用脚本时的原始路径（仓库相对/绝对都可能），
        # 换算成本应用统一使用的、相对 output/ 的媒体路径。
        ref_images_rel = context['ref_images']
    _reference_paths(name, ref_images_rel)
    count = body.get('count', 1)
    if type(count) is not int or not 1 <= count <= 6:
        raise ApiError(400, '生成张数必须为 1–6 的整数')
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 30000:
        raise ApiError(400, '提示词需为 1–30000 字')
    payload = {'job_id': job_id, 'kind': kind, 'episode': episode, 'prompt': prompt,
               'count': count, 'ref_images': ref_images_rel}
    return {'approval': approvals.preview(pdir, payload, ctx.username)}


@router.post(r'/api/projects/(?P<name>[^/]+)/regenerate')
def api_regenerate(ctx, params):
    name = params['name']
    pdir = _project_or_404(name)
    body = ctx.json()
    if not isinstance(body, dict) or body.get('approved') is not True or not isinstance(body.get('approval_id'), str):
        raise ApiError(403, '图片任务必须先预览并由用户明确审批')
    def submit(payload):
        job_id, kind, episode = payload['job_id'], payload['kind'], payload['episode']
        if content_editor.disabled(pdir, job_id, kind, episode):
            raise ValueError('该条目已移入回收站，请恢复后重新审批')
        for entry in state.list_regen_jobs(_state_path(name)):
            target = entry.get('target', {})
            if (entry.get('kind') == 'image' and target.get('job_id') == job_id and target.get('type') == kind
                    and str(target.get('episode') or '') == str(episode or '')):
                live = jobs.get_status(entry.get('token'))
                if live and live['status'] == 'running':
                    raise ValueError('这个图片任务已经在运行，请在顶部任务栏查看进度')
        out_dir = _out_dir_for_kind(pdir, kind, episode)
        refs = _reference_paths(name, payload['ref_images'])
        token = jobs.start_regenerate(out_dir, job_id, payload['prompt'], payload['count'], refs, projects.web_state_logs_dir(name))
        state.add_regen_job(_state_path(name), target={'type': kind, 'job_id': job_id, 'episode': episode},
                            note='用户已明确批准此提示词、参考图和张数', status='running', token=token, kind='image')
        return {'token': token, 'used_ref_images': payload['ref_images']}
    try:
        return approvals.execute(pdir, body['approval_id'], ctx.username, submit)
    except ValueError as e:
        raise ApiError(400, str(e))


@router.get(r'/api/projects/(?P<name>[^/]+)/regenerate/(?P<token>[^/]+)')
def api_regenerate_status(ctx, params):
    name = params['name']
    _project_or_404(name)
    record = next((t for t in state.list_regen_jobs(_state_path(name)) if t.get('token') == params['token']), None)
    if not record:
        raise ApiError(404, '找不到当前项目的这个任务')
    status = jobs.get_status(params['token'])
    if not status:
        raise ApiError(404, '找不到这个任务（服务重启后进行中任务的记录会丢失）')
    if status['status'] in ('done', 'failed'):
        try:
            state.update_regen_job(_state_path(name), params['token'], status=status['status'])
        except ValueError:
            pass
    return status


# ---------------- auth ----------------

@router.get(r'/api/me')
def api_me(ctx, params):
    return {
        'username': ctx.username,
        'display_name': auth.display_name(ctx.username),
        'is_admin': auth.is_admin(ctx.username),
    }


# ---------------- inbox ----------------

@router.get(r'/api/inbox')
def api_inbox(ctx, params):
    allowed = auth.allowed_projects(ctx.username)
    out = []
    for p in projects.list_projects():
        if not auth.can_access_project(ctx.username, p['name']):
            continue
        sp = _state_path(p['name'])
        comments = state.list_comments(sp, resolved=False)
        regen_jobs = [j for j in state.list_regen_jobs(sp) if j.get('status') != 'done']
        if comments or regen_jobs:
            out.append({'project': p['name'], 'comments': comments, 'regen_jobs': regen_jobs})
    return {'projects': out}


# ---------------- HTTP plumbing ----------------

class Handler(BaseHTTPRequestHandler):
    server_version = 'ScreenwriterWeb/1.0'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
        except ValueError:
            raise ApiError(400, 'Content-Length 不合法')
        if length < 0 or length > 8 * 1024 * 1024:
            raise ApiError(413, '请求过大，上传文件最多 5 MB')
        return self.rfile.read(length) if length else b''

    def _handle_login(self):
        try:
            body_bytes = self._read_body()
        except ApiError as exc:
            self.close_connection = True
            self._send_json(exc.status, {'error': exc.message})
            return
        try:
            body = json.loads(body_bytes.decode('utf-8')) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {'error': '请求体不是合法 JSON'})
            return
        username = (body.get('username') or '').strip()
        password = body.get('password') or ''
        if not username or not password:
            self._send_json(400, {'error': '需要用户名和密码'})
            return
        if not auth.verify_password(username, password):
            self._send_json(401, {'error': '用户名或密码错误'})
            return
        cookie_value = auth.make_session_cookie_value(username)
        payload = json.dumps({'ok': True, 'display_name': auth.display_name(username)}, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Set-Cookie', auth.build_set_cookie_header(cookie_value, auth.SESSION_TTL_SECONDS, self.server.secure_cookies))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_logout(self):
        payload = json.dumps({'ok': True}, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Set-Cookie', auth.build_clear_cookie_header(self.server.secure_cookies))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_api(self, method):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if path == '/api/login' and method == 'POST':
            self._handle_login()
            return
        if path == '/api/logout' and method == 'POST':
            self._handle_logout()
            return

        username = auth.username_from_headers(self.headers)
        if not username:
            self._send_json(401, {'error': '未登录或登录已过期，请重新登录'})
            return

        handler, params = router.match(method, path)
        if not handler:
            self._send_json(404, {'error': f'未知接口: {method} {path}'})
            return
        project_name = params.get('name')
        if project_name is not None and not auth.can_access_project(username, project_name):
            self._send_json(403, {'error': '没有权限访问这个项目'})
            return
        try:
            body_bytes = self._read_body()
        except ApiError as exc:
            self.close_connection = True
            self._send_json(exc.status, {'error': exc.message})
            return
        ctx = Ctx(query, body_bytes, self.headers)
        ctx.username = username
        try:
            if method == 'PATCH' and project_name:
                with content_editor.lock(_project_or_404(project_name)):
                    result = handler(ctx, params)
            else:
                result = handler(ctx, params)
            self._send_json(200, result)
        except ApiError as e:
            self._send_json(e.status, {'error': e.message})
        except Exception:
            traceback.print_exc()
            self._send_json(500, {'error': '服务器内部错误'})

    def _handle_media(self, path):
        username = auth.username_from_headers(self.headers)
        if not username:
            self.send_error(401)
            return
        rel = unquote(path[len('/media/'):])
        project_name = rel.split('/', 1)[0] if rel else None
        if not project_name or not auth.can_access_project(username, project_name):
            self.send_error(403)
            return
        abs_path = projects.resolve_media_path(rel)
        if not abs_path:
            self.send_error(404)
            return
        file_size = os.path.getsize(abs_path)
        range_header = self.headers.get('Range')
        rng = media.parse_range(range_header, file_size) if range_header else None
        ctype = media.guess_content_type(abs_path)
        if rng:
            start, end = rng
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
            self.send_header('Content-Length', str(end - start + 1))
        else:
            start, end = 0, file_size - 1
            self.send_response(200)
            self.send_header('Content-Length', str(file_size))
        self.send_header('Content-Type', ctype)
        self.send_header('Accept-Ranges', 'bytes')
        self.end_headers()
        try:
            for chunk in media.iter_file(abs_path, start, end):
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_static(self, path):
        if path == '/':
            path = '/index.html'
        if path != '/login.html' and not auth.username_from_headers(self.headers):
            self.send_response(302)
            self.send_header('Location', '/login.html?next=' + quote(path, safe=''))
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        safe = os.path.normpath(path).lstrip('/')
        abs_path = os.path.normpath(os.path.join(FRONTEND_DIR, safe))
        if not (abs_path == FRONTEND_DIR or abs_path.startswith(FRONTEND_DIR + os.sep)) or not os.path.isfile(abs_path):
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(abs_path)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript', 'application/json'):
            # 前端文件里全是中文字面量，不显式声明 charset 的话浏览器的编码
            # 嗅探有时会猜成 windows-1252，把中文渲染成乱码。
            ctype += '; charset=utf-8'
        with open(abs_path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith('/api/'):
            self._handle_api('GET')
        elif path.startswith('/media/'):
            self._handle_media(path)
        else:
            self._handle_static(path)

    def do_POST(self):
        self._handle_api('POST')

    def do_PATCH(self):
        self._handle_api('PATCH')


class Server(ThreadingHTTPServer):
    # 图片画廊页面一次要并发加载几十张图，默认 socketserver 的 listen
    # backlog 只有 5，浏览器一开页面就并发开一批连接，很容易把 backlog
    # 挤满导致部分图片连接被拒绝/卡住（表现为图片框一直空白加载不出来）。
    request_queue_size = 128


def main():
    project_setup.recover_interrupted()
    prompt_tasks.recover(projects.OUTPUT_DIR)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', default='0.0.0.0', help='默认监听所有网卡，方便局域网访问')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--secure-cookies', action='store_true',
                     help='服务在 HTTPS 反向代理（nginx+certbot 等）后面时打开，'
                          '给登录 cookie 加 Secure 标记；纯 HTTP（局域网内网用）不要加这个参数')
    args = ap.parse_args()
    if not auth.has_any_user():
        print('提醒：目前还没有任何登录账号，所有页面/接口都会拒绝访问。')
        print('先运行：python3 web/server/manage_users.py add <用户名> 创建一个账号。')
    httpd = Server((args.host, args.port), Handler)
    httpd.secure_cookies = args.secure_cookies
    print(f'剧本家协作网站已启动：http://{args.host}:{args.port} （局域网内用这台机器的 IP 替换 {args.host} 访问，Ctrl+C 停止）')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
