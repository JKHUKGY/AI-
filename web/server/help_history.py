"""Private, durable help exchanges; users never supply authoritative answer logs."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
import auth
from router import ApiError


@contextmanager
def db():
    path=Path(auth.DATA_DIR)/'help_conversations.sqlite3'
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
    os.chmod(path,0o600)
    c=sqlite3.connect(path,timeout=30);c.row_factory=sqlite3.Row
    try:
        c.executescript('''CREATE TABLE IF NOT EXISTS exchanges(
          id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
          username TEXT NOT NULL, page TEXT NOT NULL, project TEXT,
          question TEXT NOT NULL, answer TEXT, model TEXT NOT NULL,
          status TEXT NOT NULL, created_at REAL NOT NULL, finished_at REAL);
          CREATE INDEX IF NOT EXISTS help_conversation ON exchanges(conversation_id,id);
          CREATE INDEX IF NOT EXISTS help_username ON exchanges(username,id);''')
        c.execute('BEGIN IMMEDIATE')
        yield c
        c.commit()
    except Exception:
        c.rollback();raise
    finally:c.close()


def begin(username,body,model):
    cid=body.get('conversation_id') or uuid.uuid4().hex
    if not isinstance(cid,str) or not re.fullmatch(r'[a-fA-F0-9-]{32,36}',cid):
        raise ApiError(400,'对话编号格式不正确，请新开对话')
    with db() as c:
        owner=c.execute('SELECT username FROM exchanges WHERE conversation_id=? LIMIT 1',(cid,)).fetchone()
        if owner and owner['username']!=username:raise ApiError(403,'无权使用该对话编号')
        cursor=c.execute('INSERT INTO exchanges(conversation_id,username,page,project,question,model,status,created_at) VALUES(?,?,?,?,?,?,?,?)',
                         (cid,username,body.get('page','home'),body.get('project'),body['question'].strip(),model,'pending',time.time()))
        return {'id':cursor.lastrowid,'conversation_id':cid}


def finish(identifier,answer=None,status='done'):
    with db() as c:
        c.execute("UPDATE exchanges SET answer=?,status=?,finished_at=? WHERE id=? AND status='pending'",
                  (answer,status,time.time(),identifier))


def listing(username='',conversation_id='',before=None):
    clauses=[];args=[]
    for field,value in [('username',username),('conversation_id',conversation_id)]:
        if value:
            if not isinstance(value,str) or len(value)>100:raise ApiError(400,'筛选条件过长')
            clauses.append(field+'=?');args.append(value)
    if before is not None:
        try:before=int(before)
        except (ValueError,TypeError):raise ApiError(400,'分页位置不正确') from None
        if before<1:raise ApiError(400,'分页位置不正确')
        clauses.append('id<?');args.append(before)
    with db() as c:
        rows=c.execute('SELECT * FROM exchanges'+(' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY id DESC LIMIT 51',args).fetchall()
    return {'records':[dict(r) for r in rows[:50]],'next_before':rows[49]['id'] if len(rows)>50 else None}
