# 网站代码

零依赖：后端纯 `stdlib http.server`，前端纯静态无构建。启动：
`python3 web/server/app.py --port 8000`。详细设计取舍见 `web/README.md`；
公网云主机部署步骤见 `web/DEPLOY.md`。

```
web/server/
  app.py         服务入口 + 各 API handler 注册
  auth.py        登录鉴权与会话
  manage_users.py 用户管理命令
  ai_prompt.py   通过服务器已登录的 Codex CLI，结合历史原文和当前版本改写绘图提示词
  prompt_history.py 同任务的旧提示词、Codex 草稿和手动版本
  prompt_tasks.py  后台文字任务及结果持久化，重复请求复用正在运行的任务
  help_chat.py / help_server.py  Luna 使用帮助问答及独立服务
  project_setup.py 导入剧本、后台生成文字基础文件与断点续跑；不执行媒体或租卡
  approvals.py   图片任务预览快照与手动审批，重复确认不重复启动
  router.py      极简路由层：正则路径匹配 + method 分发
  projects.py    扫描 output/*/，识别每部剧当前处于流水线哪个阶段
  jobs.py        回查有效历史提示词/原始任务；"重新生成"按钮 → 图片生成子进程
  state.py       review.json 的读写（剧本家反馈落地的唯一入口）
  md_render.py   极简 markdown → HTML（只覆盖仓库文档实际用到的语法子集）
  md_tables.py   解析/改写分镜表等 GFM pipe-table，供网站在线编辑用
  media.py       受限静态文件服务，只映射 /media/<output/ 下相对路径>
web/frontend/
  index.html, app.js, api.js, shared.js, style.css   页面骨架/路由/API封装/公共组件/样式
  tasks.js              全站任务栏与刷新恢复，独立于当前页面
  help.js               侧边使用帮助对话、当前页面指引与常见问题
  views/home.js         项目列表首页与新建项目/剧本导入
  views/setup.js        文字筹备进度、文件预览、图片审批与租卡待办
  views/guide.js        渲染 content/guide.md 给剧本家看的操作指南
  views/style-bible.js  画风圣经查看
  views/characters.js   人物立绘查看+选片
  views/scenes.js       场景图查看+选片
  views/episode.js      分镜表查看+在线编辑
  views/keyframes.js    关键帧图查看+重新生成
  views/videos.js       视频清单查看
  views/inbox.js        剧本家反馈收件箱
web/content/guide.md    渲染给剧本家看的指南正文（改这个文件即可改指南内容）
```

后端 API 惯例：项目数据只从 `output/<剧名>/` 现有文件读取/回写，不额外存数据库；
新项目归创建者所有；文字筹备只写文件。图片须预览后手动审批才实际生成，对视频与租卡只登记待办不执行。

网址、账号、Azure / Codespace 运维：读当前宿主 index 的 `references/resources.md`，再选对应资源页。
