"""独立帮助服务：不重启或占用主网站的生成任务进程。"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import auth
import help_chat
from router import ApiError, Ctx


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.close_connection = True
        if self.path != '/api/help/question':
            self.reply(404, {'error':'未知接口'})
            return
        username = auth.username_from_headers(self.headers)
        if not username:
            self.reply(401, {'error':'请先登录'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 256000:
                raise ApiError(413, '问题或对话记录过长')
            body = Ctx({}, self.rfile.read(length), self.headers).json()
            result = help_chat.answer(username, body)
            self.reply(200, result)
        except ApiError as exc:
            self.reply(exc.status, {'error':exc.message})
        except ValueError:
            self.reply(400, {'error':'请求格式不正确'})
        except Exception:
            self.reply(500, {'error':'帮助服务暂时异常，请稍后再试'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
