"""账号控制、积分与用量的事务账本；主站和帮助服务共用 SQLite。"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from router import ApiError

_locks = {}
_guard = threading.Lock()
PRICES = {'image': 10, 'video': 300}
FEATURES = {'create':'创建项目', 'edit':'编辑与反馈', 'text':'文字生成', 'image':'图片生成', 'video':'视频生成', 'help':'使用帮助'}


def user_lock(username):
    with _guard:
        return _locks.setdefault(username, threading.RLock())


@contextmanager
def db():
    import auth
    Path(auth.DATA_DIR).mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(Path(auth.DATA_DIR) / 'control.sqlite3'), timeout=30)
    os.chmod(Path(auth.DATA_DIR) / 'control.sqlite3', 0o600)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(username TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
          session_version INTEGER NOT NULL DEFAULT 0, balance INTEGER NOT NULL DEFAULT 0 CHECK(balance>=0),
          gpu_allowed INTEGER NOT NULL DEFAULT 0, last_seen REAL);
        CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY, username TEXT NOT NULL, project TEXT NOT NULL,
          kind TEXT NOT NULL, quantity INTEGER NOT NULL, unit_cost INTEGER NOT NULL, status TEXT NOT NULL,
          charged INTEGER NOT NULL DEFAULT 0, ref TEXT, detail TEXT NOT NULL DEFAULT '{}',
          created_at REAL NOT NULL, finished_at REAL);
        CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY, username TEXT NOT NULL, delta INTEGER NOT NULL,
          reason TEXT NOT NULL, actor TEXT NOT NULL, created_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, usage_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0, error TEXT, sent_at REAL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS features(username TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS rentals(id TEXT PRIMARY KEY, username TEXT NOT NULL, project TEXT NOT NULL,
          status TEXT NOT NULL, pod_id TEXT, detail TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
          updated_at REAL NOT NULL);
        ''')
        connection.execute('BEGIN IMMEDIATE')
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _account(c, username):
    c.execute('INSERT OR IGNORE INTO accounts(username) VALUES (?)', (username,))
    return dict(c.execute('SELECT * FROM accounts WHERE username=?', (username,)).fetchone())


def account(username):
    with db() as c:
        result = _account(c, username)
        result['held'] = c.execute("SELECT COALESCE(SUM(quantity*unit_cost),0) FROM usage WHERE username=? AND status IN ('reserved','running','unknown')", (username,)).fetchone()[0]
        flags = c.execute('SELECT value FROM features WHERE username=?',(username,)).fetchone()
        result['features'] = {key:True for key in FEATURES} | (json.loads(flags['value']) if flags else {})
        return result


def require_feature(username, feature):
    import auth
    ensure_enabled(username)
    if not auth.is_admin(username) and not account(username)['features'].get(feature,True):
        raise ApiError(403, f'管理员已禁止该账号使用{FEATURES[feature]}')


def set_features(username, flags):
    if not isinstance(flags,dict) or set(flags)-set(FEATURES) or any(type(v) is not bool for v in flags.values()):
        raise ApiError(400,'功能权限不合法')
    with db() as c:
        c.execute('INSERT OR REPLACE INTO features VALUES (?,?)',(username,json.dumps(flags)))


def ensure_enabled(username):
    if not account(username)['enabled']:
        raise ApiError(403, '账号已停用，请联系管理员')


def set_enabled(username, enabled):
    with db() as c:
        _account(c, username)
        c.execute('UPDATE accounts SET enabled=?, session_version=session_version+1 WHERE username=?', (int(enabled), username))


def allocate(username, delta, actor, request_id):
    if type(delta) is not int or delta == 0 or abs(delta) > 10000000:
        raise ApiError(400, '积分调整必须是非零整数，最多 10000000')
    if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
        raise ApiError(400, '缺少有效操作编号，请刷新后重试')
    key = 'allocation:' + request_id
    with db() as c:
        old = c.execute('SELECT * FROM ledger WHERE id=?', (key,)).fetchone()
        if old:
            if old['username'] != username or old['delta'] != delta or old['actor'] != actor:
                raise ApiError(409, '操作编号已用于其他积分调整')
            return _account(c, username)
        row = _account(c, username)
        if row['balance'] + delta < 0:
            raise ApiError(400, '不能扣减超过可用余额的积分')
        c.execute('UPDATE accounts SET balance=balance+? WHERE username=?', (delta, username))
        c.execute('INSERT INTO ledger VALUES (?,?,?,?,?,?)', (key, username, delta, '管理员分配', actor, time.time()))
        return _account(c, username)


def reserve(username, project, kind, quantity=1, identifier=None, detail=None):
    if kind in ('image','video'):
        require_feature(username,kind)
    if type(quantity) is not int or not 1 <= quantity <= 100:
        raise ApiError(400, '生成数量不合法')
    identifier = identifier or uuid.uuid4().hex
    cost = PRICES.get(kind, 0)
    with db() as c:
        user = _account(c, username)
        if not user['enabled']:
            raise ApiError(403, '账号已停用')
        old = c.execute('SELECT * FROM usage WHERE id=?', (identifier,)).fetchone()
        if old:
            if (old['username'], old['project'], old['kind'], old['quantity']) != (username, project, kind, quantity):
                raise ApiError(409, '任务编号冲突')
            return dict(old)
        total = cost * quantity
        if user['balance'] < total:
            raise ApiError(402, f'积分不足：本次需要 {total}，可用 {user["balance"]}，请联系管理员分配')
        c.execute('UPDATE accounts SET balance=balance-? WHERE username=?', (total, username))
        c.execute('INSERT INTO usage(id,username,project,kind,quantity,unit_cost,status,detail,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                  (identifier, username, project, kind, quantity, cost, 'reserved', json.dumps(detail or {}, ensure_ascii=False), time.time()))
        if total:
            c.execute('INSERT INTO ledger VALUES (?,?,?,?,?,?)', ('hold:' + identifier, username, -total, '冻结积分', username, time.time()))
        return dict(c.execute('SELECT * FROM usage WHERE id=?', (identifier,)).fetchone())


def started(identifier, ref=None):
    with db() as c:
        changed = c.execute("UPDATE usage SET status='running', ref=? WHERE id=? AND status='reserved'", (ref, identifier)).rowcount
        kind = c.execute('SELECT kind FROM usage WHERE id=?', (identifier,)).fetchone()
        if changed and kind and kind['kind'] == 'mail_test':
            c.execute('INSERT OR IGNORE INTO outbox(id,usage_id) VALUES (?,?)', ('start:' + identifier, identifier))


def gpu_notification(identifier):
    """仅在实例确认存在之后入队，每次开卡恰好一条通知。"""
    with db() as c:
        c.execute('INSERT OR IGNORE INTO outbox(id,usage_id) VALUES (?,?)', ('start:' + identifier, identifier))


def settle(identifier, status, completed=0):
    if status not in ('done', 'failed', 'cancelled', 'interrupted'):
        raise ValueError('Invalid settlement')
    with db() as c:
        row = c.execute('SELECT * FROM usage WHERE id=?', (identifier,)).fetchone()
        if not row or row['status'] not in ('reserved', 'running', 'unknown'):
            return
        completed = max(0, min(int(completed), row['quantity']))
        charged = completed * row['unit_cost']
        refund = row['quantity'] * row['unit_cost'] - charged
        c.execute('UPDATE accounts SET balance=balance+? WHERE username=?', (refund, row['username']))
        if refund:
            c.execute('INSERT INTO ledger VALUES (?,?,?,?,?,?)', ('refund:' + identifier, row['username'], refund, '退回未完成部分', 'system', time.time()))
        c.execute('UPDATE usage SET status=?, charged=?, finished_at=? WHERE id=?', (status, charged, time.time(), identifier))


def audit(username, kind, project='', detail=None):
    row = reserve(username, project, kind, detail=detail)
    started(row['id']); settle(row['id'], 'done')
    return row['id']


def settings():
    with db() as c:
        return {'mail_to': 'j18210070075@gmail.com', **{r['key']: json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}}


def save_settings(values):
    with db() as c:
        for key, value in values.items():
            c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))


def usage(username=None, limit=200):
    with db() as c:
        rows = c.execute('SELECT * FROM usage' + (' WHERE username=?' if username else '') + ' ORDER BY created_at DESC LIMIT ?',
                         (username, limit) if username else (limit,)).fetchall()
        return [{**dict(row), 'detail': json.loads(row['detail'])} for row in rows]


def touch(username):
    with db() as c:
        _account(c, username)
        c.execute('UPDATE accounts SET last_seen=? WHERE username=? AND (last_seen IS NULL OR last_seen<?)', (time.time(), username, time.time()-60))
