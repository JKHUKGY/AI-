from pathlib import Path
import sys
sys.path[:0] = ['/workspaces/AI-/web/server', '/workspaces/AI-/web/server/tests']
import app
import generation_control as gc
from test_project_workflow import FOUNDATION, BOARD, SCRIPT

root = Path(__file__).parent
app.projects.OUTPUT_DIR = str(root / 'output')
app.auth.username_from_headers = lambda headers: 'browser-test'
app.auth.allowed_projects = lambda username: []
app.project_setup._call = lambda query, schema: FOUNDATION if schema == app.project_setup.FOUNDATION else BOARD
if not (root / 'output/终止验收').exists():
    app.project_setup.create({'name': '终止验收', 'script': SCRIPT, 'duration': 15}, 'browser-test')
    app.project_setup._capacity.acquire()
    app.project_setup._worker(str(root / 'output/终止验收'))

def delay():
    gc.current().run([sys.executable, '-c', 'import time; time.sleep(30)'], input='', timeout=40, text=True)

def prompt(*args, **kwargs):
    delay()
    return '新提示词不应在取消后落地'

def board(query, schema):
    if schema == app.project_setup.FOUNDATION:
        return FOUNDATION
    delay()
    return BOARD

app.ai_prompt.rewrite = prompt
app.ai_prompt.fresh = prompt
app.project_setup._call = board
script = root / 'dummy_images.py'
script.write_text('import time\ntime.sleep(30)\n')
app.jobs.GENERATE_SCRIPT = str(script)
server = app.Server(('127.0.0.1', 18010), app.Handler)
server.secure_cookies = False
server.serve_forever()
