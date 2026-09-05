"""角色、场景、分集和镜头的结构编辑。删除只移除文字条目，原文进入回收站。"""
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

import md_tables
import projects
import state
from router import ApiError

CHAR = re.compile(r'^(?:\d+\.|角色[一二三四五六七八九十百千\d]+[:：])\s*([^（(—－]+)')
SCENE = re.compile(r'^(SC\d+)')
HEADERS = ['镜号','场景编号','机位','在场人物','出场人物','画面描述','景别','运镜','时长(秒)',
           '台词/旁白','音效/BGM','分级','剧本原文锚点','生成单元拆分建议','图像生成提示词','运动描述','转场','备注']


def store_path(root):
    return str(Path(root) / '_web_state/content.json')


def lock(root):
    return state._lock_for(store_path(root) + '.edit')


def _data(root):
    return state.load(store_path(root))


def _save(root, data):
    Path(store_path(root)).parent.mkdir(parents=True, exist_ok=True)
    state.save(store_path(root), data)


def _ready(root):
    p = Path(root) / '_web_state/setup.json'
    if p.is_file() and json.loads(p.read_text()).get('status') != 'done':
        raise ApiError(409, '自动筹备尚未完成，请先在“项目筹备”完成或继续文字生成，再增删结构。已有文字仍可编辑。')


def _file(root, kind, episode=None):
    if kind not in ('character','scene','episode','shot'):
        raise ApiError(400, '不支持的条目类型')
    if kind in ('episode','shot'):
        if type(episode) is not int or not 1 <= episode <= 999:
            raise ApiError(400, '集号必须为 1–999 的整数')
        rel = f'storyboard/ep{episode:02d}.md'
    else:
        rel = 'storyboard/' + ('characters.md' if kind == 'character' else 'scenes.md')
    path = Path(root) / rel
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ApiError(400, '文件路径不合法')
    return path


def _write(path, text):
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.content-tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def _digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _sections(text):
    # 只识别代码块以外的二级标题，保留目标区块之外的原始文本。
    result, offset, fence = [], 0, None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = re.match(r'(`{3,}|~{3,})', stripped)
        if marker:
            token = marker.group(1)
            if fence is None: fence = token
            elif token[0] == fence[0] and len(token) >= len(fence): fence = None
        elif fence is None:
            match = re.match(r'^##\s+(.+?)\s*$', line)
            if match: result.append({'title':match.group(1),'start':offset})
        offset += len(line)
    for i, section in enumerate(result):
        section['end'] = result[i+1]['start'] if i+1 < len(result) else len(text)
    return result


def _text(value, label, limit=30000, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ApiError(400, f'{label}需为有效文本，最多 {limit} 字')
    return value.strip()


def _reserved(data, kind, episode=None):
    return [e for e in data.get('trash', []) if e['kind'] == kind and (episode is None or e.get('episode') == episode)]


def add(root, body, username):
    if not isinstance(body, dict): raise ApiError(400, '请求体必须为对象')
    kind = body.get('kind')
    with lock(root):
        _ready(root)
        data = _data(root)
        episode = body.get('episode')
        if kind == 'episode':
            nums = projects.list_episode_numbers(Path(root).name)
            nums += projects.list_media_episode_numbers(Path(root).name, 'keyframes') + projects.list_media_episode_numbers(Path(root).name, 'videos')
            nums += [e['episode'] for e in _reserved(data, 'episode')]
            episode = max(nums, default=0) + 1
        path = _file(root, kind, episode)
        old = path.read_text(encoding='utf-8') if path.exists() else ''
        if kind in ('character','scene'):
            name = _text(body.get('name'), '名称', 80)
            if re.search(r'[\n\r/\\<>#|`（(—－]', name): raise ApiError(400, '名称不可含路径、换行或标题分隔符')
            description = _text(body.get('text'), '描述')
            if re.search(r'^##\s', description, re.M): raise ApiError(400, '条目正文请使用三级标题（###），不要使用二级标题')
            matcher = CHAR if kind == 'character' else SCENE
            titles = [s['title'] for s in _sections(old)] + [e['title'] for e in _reserved(data, kind)]
            if kind == 'character' and any(matcher.match(t) and matcher.match(t).group(1).strip() == name for t in titles):
                raise ApiError(409, '角色名称已存在或在回收站中，请恢复原条目或换名')
            assets = Path(root) / 'assets'
            if kind == 'character' and assets.is_dir() and any(p.name == name or p.name.startswith(name+'_') for p in assets.iterdir()):
                raise ApiError(409, '已有同名角色素材，请使用不同名称，避免关联到旧图片')
            if kind == 'scene' and any(re.sub(r'^SC\d+\s*', '', t) == name for t in titles):
                raise ApiError(409, '场景名称已存在或在回收站中')
            nums = [int(m.group()) for t in titles if matcher.match(t) for m in [re.search(r'\d+', t)] if m]
            if kind == 'scene' and assets.is_dir():
                nums += [int(m.group(1)) for p in assets.iterdir() for m in [re.match(r'^SC(\d+)(?:_|$)',p.name)] if m]
            number = max(nums, default=0) + 1
            title = f'{number}. {name}' if kind == 'character' else f'SC{number:02d} {name}'
            new = old.rstrip() + f'\n\n## {title}\n\n{description}\n'
            result = {'title':title}
        elif kind == 'episode':
            title = _text(body.get('name'), '集名', 100)
            if '\n' in title or '\r' in title: raise ApiError(400, '集名不能换行')
            new = f'# 第{episode}集 {title}\n\n| ' + ' | '.join(HEADERS) + ' |\n|' + '|'.join(['---']*len(HEADERS)) + '|\n'
            result = {'episode':episode}
        else:
            table = md_tables.parse_table(old)
            if not table or '镜号' not in table['header']: raise ApiError(400, '本集没有可编辑的分镜表')
            row = body.get('row')
            if not isinstance(row, dict) or set(row) - (set(table['header']) - {'镜号'}): raise ApiError(400, '镜头字段不正确')
            row = {k:_text(v, k, 8000, False) for k,v in row.items()}
            _text(row.get('画面描述'), '画面描述', 8000)
            keys = [r['镜号'] for r in table['rows']] + [e['key'] for e in _reserved(data,'shot',episode)]
            folder = Path(root) / f'keyframes/ep{episode:02d}'
            if folder.is_dir(): keys += [p.name.split('_镜')[-1] for p in folder.iterdir() if '_镜' in p.name]
            numbers = [int(m.group()) for key in keys for m in [re.search(r'\d+',key)] if m]
            row['镜号'] = str(max(numbers, default=0) + 1)
            lines = old.splitlines(keepends=True)
            after = body.get('after')
            if after is None: index = table['end']
            else:
                matches = [i for i,r in enumerate(table['rows']) if r['镜号'] == after]
                if not matches: raise ApiError(409, '插入位置已变化，请刷新')
                index = table['start'] + matches[0] + 1
            lines.insert(index, md_tables._render_row(table['header'],row) + '\n')
            new = ''.join(lines)
            result = {'episode':episode,'shot':row['镜号']}
        data.setdefault('events',[]).append({'action':'add','kind':kind,'result':result,'by':username,'at':time.time()})
        _save(root, data)
        _write(path, new)
        return result


def preview(root, body):
    if not isinstance(body,dict): raise ApiError(400,'请求体必须为对象')
    with lock(root):
        _ready(root)
        kind, ep = body.get('kind'), body.get('episode')
        path = _file(root,kind,ep)
        if not path.is_file(): raise ApiError(404,'条目不存在')
        text = path.read_text(encoding='utf-8')
        entry = {'id':uuid.uuid4().hex,'kind':kind,'episode':ep,'revision':_digest(text),'created_at':time.time()}
        if kind in ('character','scene'):
            section = next((s for s in _sections(text) if s['title']==body.get('title')),None)
            matcher = CHAR if kind=='character' else SCENE
            if not section or not matcher.match(section['title']): raise ApiError(404,'找不到该角色或场景')
            entry.update(title=section['title'],key=matcher.match(section['title']).group(1).strip(),position=section['start'],content=text[section['start']:section['end']])
        elif kind=='shot':
            table = md_tables.parse_table(text)
            rows = table['rows'] if table else []
            indices = [i for i,r in enumerate(rows) if r.get('镜号') == body.get('shot')]
            if len(indices)!=1: raise ApiError(409,'镜号不存在或重复，请刷新并核对')
            i=indices[0]
            entry.update(key=rows[i]['镜号'],row=rows[i],header=table['header'],position=i,content=md_tables._render_row(table['header'],rows[i]))
        else:
            entry.update(key=str(ep),content=text,position=0)
        references=[]
        if kind in ('character','scene'):
            for p in (Path(root)/'storyboard').glob('ep*.md'):
                table=md_tables.parse_table(p.read_text(encoding='utf-8'))
                for row in (table or {}).get('rows',[]):
                    if any(entry['key'] in row.get(k,'') for k in ('场景编号','画面描述','在场人物','出场人物','台词/旁白')):
                        references.append(f'{p.stem} · 镜{row.get("镜号", "?")}')
        entry['references']=references
        data=_data(root); data.setdefault('previews',[]).append(entry); data['previews']=data['previews'][-50:]; _save(root,data)
        return {**entry,'notice':'仅移除这份文字条目并存入回收站。已有图片、视频、任务和其他引用保留；请按需同步修改引用。'}


def remove(root, body, username):
    if not isinstance(body,dict) or body.get('confirmed') is not True: raise ApiError(400,'请先预览并确认删除')
    with lock(root):
        _ready(root); data=_data(root)
        entry=next((e for e in data.get('previews',[]) if e['id']==body.get('preview_id')),None)
        if not entry or time.time()-entry['created_at']>3600: raise ApiError(409,'删除预览已过期，请重新预览')
        if any(e['id']==entry['id'] for e in data.get('trash',[])): raise ApiError(409,'该删除请求已处理')
        path=_file(root,entry['kind'],entry['episode'])
        text=path.read_text(encoding='utf-8') if path.exists() else ''
        if _digest(text)!=entry['revision']: raise ApiError(409,'内容已被修改，请重新预览后删除')
        if entry['kind'] in ('character','scene'):
            start=entry['position']; new=text[:start]+text[start+len(entry['content']):]
        elif entry['kind']=='shot':
            table=md_tables.parse_table(text); lines=text.splitlines(keepends=True)
            del lines[table['start']+entry['position']]; new=''.join(lines)
        else: new=None
        data.setdefault('trash',[]).append({**entry,'deleted_by':username,'deleted_at':time.time(),'restored':False})
        _save(root,data)  # 原文先安全保存，随后才从展示文件移除。
        if new is None: path.unlink()
        else: _write(path,new)
        return {'ok':True,'id':entry['id']}


def trash(root):
    with lock(root):
        return [{k:v for k,v in e.items() if k not in ('content','row','header','revision')} for e in _data(root).get('trash',[]) if not e['restored']]


def restore(root, identifier, username):
    with lock(root):
        _ready(root); data=_data(root)
        entry=next((e for e in data.get('trash',[]) if e['id']==identifier and not e['restored']),None)
        if not entry: raise ApiError(404,'回收站条目不存在')
        path=_file(root,entry['kind'],entry['episode']); old=path.read_text(encoding='utf-8') if path.exists() else ''
        if entry['kind']=='episode':
            if path.exists(): raise ApiError(409,'该集号已有内容，不能覆盖恢复')
            new=entry['content']
        elif entry['kind']=='shot':
            table=md_tables.parse_table(old)
            if not table: raise ApiError(409,'请先恢复所属分集')
            if table['header']!=entry['header'] or any(r['镜号']==entry['key'] for r in table['rows']): raise ApiError(409,'镜号或表格结构冲突，不能覆盖恢复')
            lines=old.splitlines(keepends=True); index=table['start']+min(entry['position'],len(table['rows']))
            lines.insert(index,md_tables._render_row(table['header'],entry['row'])+'\n'); new=''.join(lines)
        else:
            matcher=CHAR if entry['kind']=='character' else SCENE
            if any(matcher.match(s['title']) and matcher.match(s['title']).group(1).strip()==entry['key'] for s in _sections(old)): raise ApiError(409,'同名或同编号条目已存在，不能覆盖恢复')
            new=old.rstrip()+'\n\n'+entry['content']
        _write(path,new)
        entry.update(restored=True,restored_by=username,restored_at=time.time()); _save(root,data)
        return {'ok':True}


def disabled(root, job_id, kind, episode):
    for e in _data(root).get('trash',[]):
        if e['restored']: continue
        if kind=='asset' and e['kind'] in ('character','scene') and (job_id==e['key'] or job_id.startswith(e['key']+'_')): return True
        if kind=='keyframe' and e.get('episode')==int(episode):
            if e['kind']=='episode': return True
            if e['kind']=='shot' and re.sub(r'\D','',e['key']) == re.sub(r'\D','',job_id.split('_镜')[-1]): return True
    return False
