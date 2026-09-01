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
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobs
import md_render
import md_tables
import media
import projects
import state
from router import ApiError, Ctx, Router

mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

WEB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(WEB_DIR, 'frontend')
CONTENT_DIR = os.path.join(WEB_DIR, 'content')

router = Router()

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
    return {'projects': projects.list_projects()}


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
        named.append({'title': title, 'key': m.group(1).strip(), 'html': md_render.render(sec['body'])})
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
    return {
        'exists': True,
        'intro_html': '\n'.join(md_render.render(p) for p in intro_parts),
        'characters': sections,
    }


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
    return {
        'exists': True,
        'intro_html': '\n'.join(md_render.render(p) for p in intro_parts),
        'scenes': sections,
    }


@router.get(r'/api/projects/(?P<name>[^/]+)/style-bible')
def api_style_bible(ctx, params):
    name = params['name']
    _project_or_404(name)
    path = projects.style_bible_md_path(name)
    if not path:
        return {'exists': False}
    return {'exists': True, 'html': md_render.render(_read_text(path))}


# ---------------- episodes ----------------

@router.get(r'/api/projects/(?P<name>[^/]+)/episodes')
def api_episodes(ctx, params):
    name = params['name']
    _project_or_404(name)
    return {'episodes': projects.list_episode_numbers(name)}


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

@router.get(r'/api/projects/(?P<name>[^/]+)/keyframes/(?P<ep>\d+)')
def api_keyframes(ctx, params):
    name = params['name']
    ep = int(params['ep'])
    _project_or_404(name)
    path = projects.keyframes_md_path(name, ep)
    variants = _augment_variants(projects.list_keyframe_variants(name, ep), state.get_selections(_state_path(name)))
    if not path:
        return {'exists': False, 'header': [], 'rows': [], 'variants': variants}
    table = md_tables.parse_table(_read_text(path))
    return {'exists': True, 'header': table['header'] if table else [], 'rows': table['rows'] if table else [], 'variants': variants}


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

@router.post(r'/api/projects/(?P<name>[^/]+)/regenerate')
def api_regenerate(ctx, params):
    name = params['name']
    pdir = _project_or_404(name)
    body = ctx.json()
    job_id = body.get('job_id')
    kind = body.get('kind', 'asset')
    episode = body.get('episode')
    if not job_id:
        raise ApiError(400, '需要 job_id')

    if kind == 'keyframe':
        if not episode:
            raise ApiError(400, 'keyframe 类型需要 episode')
        out_dir = os.path.join(pdir, 'keyframes', f'ep{int(episode):02d}')
    else:
        out_dir = os.path.join(pdir, 'assets')

    last_prompt, last_ref_images = jobs.find_last_job_meta(out_dir, job_id)
    prompt = body.get('prompt') or last_prompt
    if not prompt:
        raise ApiError(400, '没有提供 prompt，历史记录里也没找到这个 job 上一次用过的 prompt，请手动填写')

    # 剧本家不显式传 ref_images 时，默认复用这个 job 上一次生成时用过的参考图
    # （通常是角色三视图/场景基准图），避免"重新生成"悄悄丢失一致性参考、
    # 跑出一张对不上脸/对不上场景的图。显式传空数组 [] 表示确实要改成纯文生图。
    if 'ref_images' in body:
        ref_images_rel = body.get('ref_images') or []
    else:
        # manifest 里存的是当初调用脚本时的原始路径（仓库相对/绝对都可能），
        # 换算成本应用统一使用的、相对 output/ 的媒体路径。
        ref_images_rel = [
            r for r in (projects.media_rel_from_manifest_path(p) for p in last_ref_images) if r
        ]
    ref_images_abs = []
    for rel in ref_images_rel:
        abs_path = projects.resolve_media_path(rel)
        if not abs_path:
            raise ApiError(400, f'ref_images 里的路径不合法: {rel}')
        ref_images_abs.append(abs_path)

    log_dir = projects.web_state_logs_dir(name)
    try:
        token = jobs.start_regenerate(out_dir, job_id, prompt, body.get('count', 2), ref_images_abs, log_dir)
    except ValueError as e:
        raise ApiError(400, str(e))

    state.add_regen_job(
        _state_path(name),
        target={'type': kind, 'job_id': job_id, 'episode': episode},
        note=body.get('note'),
        status='running',
        token=token,
        kind='image',
    )
    return {'token': token, 'used_ref_images': ref_images_rel}


@router.get(r'/api/projects/(?P<name>[^/]+)/regenerate/(?P<token>[^/]+)')
def api_regenerate_status(ctx, params):
    name = params['name']
    _project_or_404(name)
    status = jobs.get_status(params['token'])
    if not status:
        raise ApiError(404, '找不到这个任务（服务重启后进行中任务的记录会丢失）')
    if status['status'] in ('done', 'failed'):
        try:
            state.update_regen_job(_state_path(name), params['token'], status=status['status'])
        except ValueError:
            pass
    return status


# ---------------- inbox ----------------

@router.get(r'/api/inbox')
def api_inbox(ctx, params):
    out = []
    for p in projects.list_projects():
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

    def _handle_api(self, method):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        handler, params = router.match(method, path)
        if not handler:
            self._send_json(404, {'error': f'未知接口: {method} {path}'})
            return
        length = int(self.headers.get('Content-Length', 0) or 0)
        body_bytes = self.rfile.read(length) if length else b''
        ctx = Ctx(query, body_bytes, self.headers)
        try:
            result = handler(ctx, params)
            self._send_json(200, result)
        except ApiError as e:
            self._send_json(e.status, {'error': e.message})
        except Exception:
            traceback.print_exc()
            self._send_json(500, {'error': '服务器内部错误'})

    def _handle_media(self, path):
        rel = unquote(path[len('/media/'):])
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', default='0.0.0.0', help='默认监听所有网卡，方便局域网访问')
    ap.add_argument('--port', type=int, default=8000)
    args = ap.parse_args()
    httpd = Server((args.host, args.port), Handler)
    print(f'剧本家协作网站已启动：http://{args.host}:{args.port} （局域网内用这台机器的 IP 替换 {args.host} 访问，Ctrl+C 停止）')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
