import sys
from pathlib import Path
sys.path[:0]=['/workspaces/AI-/web/server','/workspaces/AI-/web/server/tests']
import app
from test_project_workflow import FOUNDATION,BOARD
app.projects.OUTPUT_DIR=str(Path(__file__).parent/'output')
app.auth.username_from_headers=lambda headers:'browser-test'
app.auth.allowed_projects=lambda username:[]
app.project_setup._call=lambda query,schema:FOUNDATION if schema==app.project_setup.FOUNDATION else BOARD
server=app.Server(('127.0.0.1',18009),app.Handler)
server.secure_cookies=False
server.serve_forever()
