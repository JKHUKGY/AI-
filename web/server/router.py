"""极简路由层，建在标准库 http.server 之上：正则路径匹配 + method 分发 +
JSON 请求体解析/JSON 响应封装。前端静态资源和 API 由同一个进程同端口提供，
不存在跨域，不需要处理 CORS。
"""
import json
import re


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, pattern, handler):
        regex = re.compile('^' + pattern + '$')
        self.routes.append((method.upper(), regex, handler))

    def get(self, pattern):
        def deco(fn):
            self.add('GET', pattern, fn)
            return fn
        return deco

    def post(self, pattern):
        def deco(fn):
            self.add('POST', pattern, fn)
            return fn
        return deco

    def patch(self, pattern):
        def deco(fn):
            self.add('PATCH', pattern, fn)
            return fn
        return deco

    def match(self, method, path):
        for m, regex, handler in self.routes:
            if m != method:
                continue
            mo = regex.match(path)
            if mo:
                return handler, mo.groupdict()
        return None, None


class Ctx:
    """单次请求的上下文：query 参数、JSON body、以及发响应的几个小工具。
    handler 本身不直接碰 BaseHTTPRequestHandler，保持业务代码和 http.server
    细节解耦，方便以后想换掉底层实现。"""

    def __init__(self, query, body_bytes, headers):
        self.query = query
        self._body_bytes = body_bytes
        self.headers = headers
        self._json_cache = None

    def json(self):
        if self._json_cache is None:
            if not self._body_bytes:
                self._json_cache = {}
            else:
                try:
                    self._json_cache = json.loads(self._body_bytes.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    raise ApiError(400, f'请求体不是合法 JSON: {e}')
        return self._json_cache

    def query_one(self, key, default=None):
        vals = self.query.get(key)
        return vals[0] if vals else default
