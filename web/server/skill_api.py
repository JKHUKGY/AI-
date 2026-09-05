"""Skill planning, loading probes, and administrator execution in project copies."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

import ai_prompt
import auth
import control_store
import generation_control
import projects
import prompt_tasks
import skill_catalog
import state
from router import ApiError


def _root(name):
    p = projects.project_dir(name)
    if not p:
        raise ApiError(404, '项目不存在')
    return Path(p)


def _store(root):
    (root / '_web_state').mkdir(parents=True, exist_ok=True)
    return str(root / '_web_state/skill_proposals.json')


def _body(ctx):
    body = ctx.json()
    if not isinstance(body, dict):
        raise ApiError(400, '请求体必须为对象')
    return body


def _context(root):
    parts = []
    for rel in ('project.json', 'source/script.txt', 'storyboard/ep01.md', 'assets/selected.md',
                'keyframes/ep01/keyframes.md'):
        path = root / rel
        if path.is_file() and path.resolve().is_relative_to(root.resolve()):
            parts.append(f'\n{rel}:\n{path.read_text()[:20000]}')
    return ''.join(parts)


def _target(skill, operation, identifier):
    return {'type': 'skill', 'job_id': skill_catalog.LABELS[skill],
            'skill': skill, 'operation': operation, 'proposal': identifier}


def _prepare(root, work):
    """Copy text inputs; reference media remain read-only files outside the sandbox."""
    dest = work / 'output' / root.name
    dest.mkdir(parents=True)
    for name in skill_catalog.LABELS:
        for src in skill_catalog.files(name):
            dst = work / '.claude/skills' / src.relative_to(skill_catalog.ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    (work / '.agents').mkdir()
    (work / '.agents/skills').symlink_to('../.claude/skills', target_is_directory=True)
    for rel in ('project.json', 'source', 'storyboard', 'assets', 'keyframes', 'videos'):
        src = root / rel
        if not src.exists() or not src.resolve().is_relative_to(root.resolve()):
            continue
        todo = [src] if src.is_file() else [p for p in src.rglob('*') if p.is_file()]
        for p in todo:
            if not p.resolve().is_relative_to(root.resolve()):
                continue
            if any(s in p.name.lower() for s in ('remote_config', 'runpod_config', '.env', 'secret', 'credential')):
                continue
            target = dest / p.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.mp4', '.wav', '.mp3'):
                target.symlink_to(p.resolve())
            elif p.suffix in ('.md', '.txt', '.json', '.csv') and p.stat().st_size <= 10000000:
                shutil.copyfile(p, target)
    return dest


def _hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and not p.is_symlink()
            and p.resolve().is_relative_to(root.resolve())}


def _execute(root, proposal):
    work = root / '_web_state/skill_runs' / proposal['id'] / 'workspace'
    if work.exists():
        raise RuntimeError('本次执行目录已存在，请检查任务记录；不会重复执行')
    work.mkdir(parents=True)
    dest = _prepare(root, work)
    baseline = _hashes(dest)
    output = work / 'result.md'
    query = (f"使用 $" + proposal['skill'] + f" 完成以下已批准任务。工作副本是 output/{root.name}。\n"
             f"模式：{proposal['mode']}。任务：{proposal['request']}\n已审阅方案：\n{proposal['plan']}\n"
             "仅在当前工作副本中操作，读取本地 .claude/skills 下的完整 SKILL.md 和所需参考文档。"
             "原项目只作为输入；不要修改副本之外的文件。不使用绕过沙盒或审批的选项。"
             "H3 当前停用，不执行该通道。不得自行租卡或启动新的计费视频任务；需要时输出待确认的具体方案，"
             "由网站租显卡入口执行。涉及图片生成须遵守 skill 的真实独立代理与轮次规则；"
             "宿主不支持时明确报告，不能伪造完成。用户选择模式在第一组候选及修改建议落地后停止，"
             "等待用户查看并提交下一次指令。缺少素材或审批时交付已完成部分和具体缺项。"
             "最终用中文说明实际执行、产物相对路径、测试证据及未完成事项。")
    cmd = [os.environ.get('CODEX_BIN', 'codex'), 'exec', '--ignore-user-config', '--ephemeral',
           '--skip-git-repo-check', '--sandbox', 'workspace-write', '--color', 'never',
           '-c', 'approval_policy="never"', '-c', 'features.hooks=false',
           '-c', 'features.multi_agent=true', '-c', 'agents.max_threads=4',
           '-c', 'features.apps=false', '-c', 'features.plugins=false',
           '--output-last-message', str(output), '-']
    try:
        proc = generation_control.current().run(cmd, input=query, text=True, encoding='utf-8',
                                                timeout=1800, cwd=str(work))
    except subprocess.TimeoutExpired:
        raise RuntimeError('本次调用超过 30 分钟，已停止；工作副本中的产物保留') from None
    if proc.returncode:
        raise RuntimeError(ai_prompt._failure_message(proc.stderr))
    if not output.is_file():
        raise RuntimeError('Skill 未返回执行报告；请查看工作副本')
    changed = [rel for rel, digest in _hashes(dest).items() if baseline.get(rel) != digest]
    return {'prompt': output.read_text(), 'scope': 'execution', 'proposal': proposal['id'],
            'artifacts': [str((dest / rel).relative_to(Path(projects.OUTPUT_DIR))) for rel in changed]}


def register(router):
    @router.get(r'/api/skills')
    def catalog(ctx, params):
        return {'skills': skill_catalog.catalog(), 'can_execute': auth.is_admin(ctx.username)}

    @router.get(r'/api/skills/(?P<skill>[a-z0-9-]+)')
    def detail(ctx, params):
        return skill_catalog.get(params['skill'], True)

    @router.get(r'/api/projects/(?P<name>[^/]+)/skills/tasks')
    def tasks(ctx, params):
        root = _root(params['name'])
        return {'tasks': [t for t in prompt_tasks.list_tasks(root) if t['target'].get('type') == 'skill']}

    @router.post(r'/api/projects/(?P<name>[^/]+)/skills/(?P<skill>[a-z0-9-]+)/(?P<action>probe|preview)')
    def prepare(ctx, params):
        root = _root(params['name'])
        body = _body(ctx)
        skill = skill_catalog.get(params['skill'])
        action = params['action']
        control_store.require_feature(ctx.username, 'text')
        request = body.get('request', '')
        if not isinstance(request, str) or len(request) > 8000:
            raise ApiError(400, '任务说明最多 8000 字')
        if action == 'preview' and not request.strip():
            raise ApiError(400, '请填写任务说明')
        if action == 'preview' and not skill['enabled']:
            raise ApiError(409, 'H3 已停用；可运行加载自检，暂不执行制作任务')
        mode = body.get('mode', 'user_choice')
        if mode not in skill['modes']:
            raise ApiError(400, '不支持这个模式')
        identifier = uuid.uuid4().hex
        context = _context(root)
        instructions = skill_catalog.instructions(skill['id'])
        query = ("这是网站的 skill 加载自检/执行前规划。只输出文字，不操作文件，不生成图片或租显卡。\n"
                 f"准确加载以下 skill={skill['id']}，版本={skill['version']}，模式={mode}。\n{instructions}\n"
                 f"项目素材：{context}\n用户任务：{request}\n")
        query += ("请用中文列出该 skill 名称、核心输入、产物、两条该文档特有约束。明确这里只验证加载调用。"
                  if action == 'probe' else
                  "请依据该 skill 给出具体执行方案、预期产物、缺少的输入和需要用户决定的事项。"
                  "执行将使用项目副本；显卡租赁通过网站已有入口完成。不要把规划说成实际生成成功。")
        def run():
            answer = ai_prompt.run_text(query, timeout=180)
            if action == 'preview':
                proposal = {'id': identifier, 'skill': skill['id'], 'version': skill['version'],
                            'mode': mode, 'request': request, 'plan': answer,
                            'author': ctx.username, 'created_at': time.time(), 'status': 'pending'}
                def save(data): data.setdefault('proposals', {})[identifier] = proposal
                state._mutate(_store(root), save)
            return {'prompt': answer, 'scope': action, 'proposal': identifier,
                    'skill': skill['id'], 'version': skill['version']}
        return {'task': prompt_tasks.start(root, _target(skill['id'], action, identifier), ctx.username, run)}

    @router.post(r'/api/projects/(?P<name>[^/]+)/skills/execute')
    def execute(ctx, params):
        root = _root(params['name'])
        body = _body(ctx)
        if not auth.is_admin(ctx.username):
            raise ApiError(403, '带工具的 skill 执行目前仅对管理员开放；普通账号可使用规划和加载自检')
        if body.get('approved') is not True:
            raise ApiError(400, '请先查看并批准具体方案')
        if not isinstance(body.get('proposal'), str):
            raise ApiError(400, '缺少方案编号')
        filename = _store(root)
        with state._lock_for(filename):
            data = state.load(filename)
            proposal = data.get('proposals', {}).get(body.get('proposal'))
            if not proposal or proposal['author'] != ctx.username:
                raise ApiError(404, '方案不存在')
            if proposal.get('task'):
                return {'task': proposal['task']}
            if proposal['status'] != 'pending' or time.time() - proposal['created_at'] > 86400:
                raise ApiError(409, '方案已失效，请重新预览')
            skill = skill_catalog.get(proposal['skill'])
            if not skill['enabled'] or skill['version'] != proposal['version']:
                raise ApiError(409, 'Skill 状态或版本已改变，请重新预览')
            control_store.require_feature(ctx.username, 'text')
            proposal['status'] = 'submitting'
            state.save(filename, data)
            try:
                task = prompt_tasks.start(root, _target(skill['id'], 'execute', proposal['id']),
                                          ctx.username, lambda: _execute(root, proposal))
            except Exception:
                proposal['status'] = 'pending'
                state.save(filename, data)
                raise
            proposal.update(status='submitted', task=task)
            state.save(filename, data)
            return {'task': task}
