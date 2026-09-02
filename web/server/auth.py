"""每人独立账号密码登录：给公网部署用，局域网内部用不需要开这个。

用法（部署前在服务器上跑一次）：
    python3 web/server/manage_users.py add <用户名>

存两个文件在 web/server/data/（都不提交进 git，见 .gitignore）：
    users.json    {用户名: {salt, hash, display_name}}，密码用
                  PBKDF2-HMAC-SHA256（20万轮）加盐哈希，不存明文。
    secret_key    32字节随机数的16进制串，首次启动自动生成，用来给会话
                  cookie 签名。这个文件丢了等于所有人的登录 cookie 失效，
                  换了它也一样——都只是逼所有人重新登录，不会丢用户数据。

会话是无状态签名 cookie（不是服务端 session 表），格式：
    <用户名>:<过期时间戳>:<hmac签名>
好处是重启服务不会让所有人掉线（cookie 在浏览器那边不受影响），
坏处是没法"服务端主动踢人下线"——如果要撤销某个人的访问，得改密码
（旧 cookie 里的用户名对得上签名依然有效，直到过期），这是当前的已知
限制，不是公网长期票据系统的替代品。
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from http.cookies import SimpleCookie

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
USERS_PATH = os.path.join(DATA_DIR, 'users.json')
SECRET_KEY_PATH = os.path.join(DATA_DIR, 'secret_key')
PERMISSIONS_PATH = os.path.join(DATA_DIR, 'permissions.json')

PBKDF2_ITERATIONS = 200_000
SESSION_COOKIE_NAME = 'sw_session'
SESSION_TTL_SECONDS = 14 * 24 * 3600  # 14 天，超时要求重新登录

# 防暴力破解：同一个用户名连续登录失败次数过多时，短时间内直接拒绝，不再
# 校验密码（内存态，重启服务会清零，够用——不是要顶抗专业刷号攻击）。
_FAIL_WINDOW_SECONDS = 300
_FAIL_MAX_ATTEMPTS = 8
_fail_counts = {}


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path, default):
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def _save_json(path, data):
    _ensure_data_dir()
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def get_secret_key():
    if os.path.isfile(SECRET_KEY_PATH):
        with open(SECRET_KEY_PATH, encoding='utf-8') as f:
            return f.read().strip()
    _ensure_data_dir()
    key = secrets.token_hex(32)
    tmp = SECRET_KEY_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(key)
    os.replace(tmp, SECRET_KEY_PATH)
    return key


def load_users():
    return _load_json(USERS_PATH, {})


def save_users(users):
    _save_json(USERS_PATH, users)


def _hash_password(password, salt_hex):
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ITERATIONS)
    return digest.hex()


def add_user(username, password, display_name=None):
    users = load_users()
    salt_hex = secrets.token_hex(16)
    users[username] = {
        'salt': salt_hex,
        'hash': _hash_password(password, salt_hex),
        'display_name': display_name or username,
    }
    save_users(users)


def remove_user(username):
    users = load_users()
    if username in users:
        del users[username]
        save_users(users)
        remove_permissions(username)
        return True
    return False


# ---------------- 项目可见范围（哪个账号能看哪几部剧） ----------------
#
# permissions.json：{用户名: {"admin": true}} 或 {用户名: {"projects": [剧名, ...]}}。
# 默认（不在这个文件里）视为"什么项目都看不到"——新建账号必须显式授权，
# 不能因为漏了一步配置就意外拿到"看全部"的权限。


def load_permissions():
    return _load_json(PERMISSIONS_PATH, {})


def save_permissions(perms):
    _save_json(PERMISSIONS_PATH, perms)


def is_admin(username):
    return bool(load_permissions().get(username, {}).get('admin'))


def allowed_projects(username):
    """返回这个账号能看的剧名列表；None 表示管理员，不限制。"""
    entry = load_permissions().get(username)
    if not entry:
        return []
    if entry.get('admin'):
        return None
    return list(entry.get('projects') or [])


def can_access_project(username, project_name):
    allowed = allowed_projects(username)
    return allowed is None or project_name in allowed


def set_admin(username, flag):
    perms = load_permissions()
    entry = perms.setdefault(username, {})
    if flag:
        entry['admin'] = True
        entry.pop('projects', None)
    else:
        entry.pop('admin', None)
    save_permissions(perms)


def set_projects(username, project_names):
    perms = load_permissions()
    entry = perms.setdefault(username, {})
    entry.pop('admin', None)
    entry['projects'] = list(dict.fromkeys(project_names))  # 去重保序
    save_permissions(perms)


def remove_permissions(username):
    perms = load_permissions()
    if username in perms:
        del perms[username]
        save_permissions(perms)


def _rate_limited(username):
    now = time.time()
    hits = [t for t in _fail_counts.get(username, []) if now - t < _FAIL_WINDOW_SECONDS]
    _fail_counts[username] = hits
    return len(hits) >= _FAIL_MAX_ATTEMPTS


def _record_failure(username):
    _fail_counts.setdefault(username, []).append(time.time())


def verify_password(username, password):
    if _rate_limited(username):
        return False
    users = load_users()
    entry = users.get(username)
    if not entry:
        # 用户名不存在也算一次失败，避免用响应时间/次数差异被拿来枚举用户名
        _record_failure(username)
        return False
    ok = hmac.compare_digest(_hash_password(password, entry['salt']), entry['hash'])
    if not ok:
        _record_failure(username)
    return ok


def display_name(username):
    return load_users().get(username, {}).get('display_name', username)


def make_session_cookie_value(username, ttl=SESSION_TTL_SECONDS):
    expiry = int(time.time()) + ttl
    payload = f'{username}:{expiry}'
    sig = hmac.new(get_secret_key().encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{payload}:{sig}'


def verify_session_cookie_value(value):
    if not value:
        return None
    parts = value.split(':')
    if len(parts) != 3:
        return None
    username, expiry_str, sig = parts
    payload = f'{username}:{expiry_str}'
    expected = hmac.new(get_secret_key().encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        expiry = int(expiry_str)
    except ValueError:
        return None
    if expiry < time.time():
        return None
    if username not in load_users():
        return None
    return username


def username_from_headers(headers):
    raw = headers.get('Cookie')
    if not raw:
        return None
    cookie = SimpleCookie()
    cookie.load(raw)
    morsel = cookie.get(SESSION_COOKIE_NAME)
    if not morsel:
        return None
    return verify_session_cookie_value(morsel.value)


def build_set_cookie_header(value, max_age, secure):
    parts = [f'{SESSION_COOKIE_NAME}={value}', 'Path=/', 'HttpOnly', 'SameSite=Lax', f'Max-Age={max_age}']
    if secure:
        parts.append('Secure')
    return '; '.join(parts)


def build_clear_cookie_header(secure):
    parts = [f'{SESSION_COOKIE_NAME}=', 'Path=/', 'HttpOnly', 'SameSite=Lax', 'Max-Age=0']
    if secure:
        parts.append('Secure')
    return '; '.join(parts)


def has_any_user():
    return bool(load_users())
