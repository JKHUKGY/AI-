# 仓库索引

> 给 Claude 用的定位地图：先查这份文件找到目标区域，再按需读取具体文件，
> 避免整仓库探索。本仓库是"AI 短剧全流水线"——从选题到分镜、出图、关键帧、
> 图生视频提示词、LTX 本地生成、剧本家协作网站。

## 一句话定位表

| 我想找… | 去这里 |
|---|---|
| 某个流水线环节怎么做（选题/分镜/出图/关键帧/视频提示词/LTX导出/LTX执行） | `.claude/skills/short-drama-*/SKILL.md`（见下表） |
| 某部短剧已经产出的分镜表、人设、场景设定 | `output/<剧名>/storyboard/` |
| 某部短剧已经生成的人物三视图/场景图 | `output/<剧名>/assets/` |
| 某部短剧某一集的关键帧图 | `output/<剧名>/keyframes/ep0X/` |
| 某部短剧某一集的成片/图生视频结果 | `output/<剧名>/videos/ep0X/` |
| 剧本家在协作网站上提的意见/编辑记录 | `output/<剧名>/_web_state/review.json` |
| 协作网站后端逻辑 | `web/server/*.py`（见下表） |
| 协作网站前端页面 | `web/frontend/views/*.js` |
| Gemini API 调用方式 | `scripts/gemini_client.py` |
| 项目需求背景 + AI 已做工作日志 | `需求.md` |
| 协作网站使用说明（给人看） | `web/README.md` |

## 顶层目录

```
.claude/skills/   7 个流水线 skill（选题→分镜→出图→关键帧→视频提示词→LTX导出→LTX执行）
output/           按剧名分目录的产出物（storyboard/assets/keyframes/videos/_web_state）
web/              本地/局域网剧本家协作网站（纯 stdlib Python 后端 + 无构建前端）
scripts/          仓库级公共脚本（目前只有 gemini_client.py）
需求.md           原始需求 + 按日期记录的"AI 已做"工作日志（追加式，找历史决策先看这）
README.md         仅一行占位，无实际内容
.env.example      GEMINI_API_KEY 模板，复制为 .env（已在 .gitignore）
《出狱后我成为了非洲矿王》一卡.docx / 短剧流水线.pdf   外部参考资料，非本仓库产出代码
```

## `.claude/skills/` —— 流水线环节（按执行顺序）

| 顺序 | Skill 目录 | 输入 → 输出 | 关键文件 |
|---|---|---|---|
| 1 | `short-drama-scout/` | 选题方向/大纲要点 → 故事梗概+人物小传+12-15集分集大纲 | `references/output_template.md`, `references/tiktok_trends.md` |
| 2 | `short-drama-storyboard/` | 故事/大纲 → 画风+逐集分镜表+人物/场景提示词 | `references/shot_grammar.md`, `character_prompt_template.md`, `scene_prompt_template.md`, `storyboard_methods.md`, `style_guide.md`, `checklist.md` |
| 3 | `short-drama-image-gen/` | 人物/场景提示词 → 三视图立绘 + 场景图（Codex CLI 出图） | `scripts/generate_images.py`, `references/jobs_schema.md`, `parallel_mode.md`, `review_checklist.md`, `api_setup.md` |
| 4 | `short-drama-keyframe-gen/` | 分镜表 + 已选人物/场景图 → 每集 8-12 张关键帧 | `references/keyframe_prompt_guide.md`, `shot_selection.md`, `keyframe_review_checklist.md` |
| 5 | `short-drama-video-gen/` | 关键帧 + 运动描述 → 图生视频完整提示词（S/A级）+ ffmpeg 推拉摇移脚本（B级） | `scripts/extract_frames.py`, `ken_burns.py`, `references/video_prompt_guide.md`, `stability_playbook.md`, `video_jobs_schema.md`, `video_platform_comparison.md`, `video_review_checklist.md` |
| 6 | `short-drama-ltx-export/` | video_jobs 提示词清单 → 校验后的 `video_jobs.json` + `ltx_remote_config.json` | `scripts/validate_video_jobs.py`, `references/resolution_presets.md` |
| 7 | `short-drama-ltx-generate/` | 校验好的 job 文件 → 真实租显卡（vast.ai / AutoDL 二选一比价）跑 LTX-2.5、下载结果、验收 | `scripts/ltx_ssh_submit.py`, `idle_shutdown_watchdog.py`, `autodl_ops.py`, `references/gpu_rental_ops.md`, `autodl_gpu_ops.md`, `autodl_cpu_ops.md`, `ltx_pipeline_gotchas.md` |

每个 skill 目录下都有 `SKILL.md`（含 `description` frontmatter，触发关键词见其中）、
可选的 `scripts/`（可执行脚本）、`references/`（详细方法论/规范文档）、部分还有
`examples/`（如 `short-drama-scout/examples/千金归位-她让全家跪着道歉`）。

## `output/<剧名>/` —— 每部短剧的产出物（固定结构）

目前有 3 部：`出狱后我成为了非洲矿王`（进度最全，10 集分镜+13场景+多角色三视图）、
`千金归位`（有分镜/立绘/关键帧/视频，无独立 storyboard 目录）、`暗局`（早期阶段，
仅 ep01 部分产出）。每部剧目录结构：

```
output/<剧名>/
  storyboard/
    style_bible.md       画风圣经（视觉风格/色调/镜头语言总则）
    characters.md        人物设计提示词档案
    scenes.md             场景设计提示词档案
    ep01.md ~ ep0N.md     逐集分镜表（画面/动作/景别/运镜/时长/生成分级）
  assets/
    <人物名>_<状态>_正面|侧面转身|背面转身/   三视图图片（_00.png, _01.png...多版本供选）
    <人物名>_表情_<表情名>/                    表情差分图
    SC<编号>_<场景名>[_日/夜版]/               场景图
    jobs_*.json           出图任务清单（喂给 generate_images.py 的输入）
    manifest.append.jsonl 出图记录追加日志
    selected.md           已选中/验收通过的图片记录
  keyframes/ep0X/
    ep0X_镜NN/             该镜关键帧图
    jobs_ep0X*.json        关键帧生成任务清单
    keyframes.md           关键帧索引说明
    manifest.append.jsonl
  videos/ep0X/
    ep0X_镜NN.mp4           单镜视频结果
    ep0X_full_preview.mp4  拼接预览
    video_jobs.json/.md    图生视频提示词清单（LTX 专属字段版）
    ltx_remote_config.json / ltx_submit_results.json
    concat_list.txt        ffmpeg 拼接清单
  _web_state/
    review.json            剧本家在协作网站上的评论/入选标记/编辑审计记录（**要提交**）
    logs/                  重新生成子进程临时日志（已 gitignore，不提交）
```

命名约定：`SC<两位数字>_<场景中文名>` 为场景 ID；人物图目录用
`<人物名>_<状态/造型>_<正面|侧面转身|背面转身>`；关键帧目录用 `ep0X_镜NN`。

## `web/` —— 剧本家协作网站

零依赖：后端纯 `stdlib http.server`，前端纯静态无构建。启动：
`python3 web/server/app.py --port 8000`。详细设计取舍见 `web/README.md`；
公网云主机部署步骤见 `web/DEPLOY.md`。

```
web/server/
  app.py         服务入口 + 各 API handler 注册（559 行，主逻辑最全）
  router.py      极简路由层：正则路径匹配 + method 分发
  projects.py    扫描 output/*/，识别每部剧当前处于流水线哪个阶段
  jobs.py        "重新生成"按钮 → 复用 short-drama-image-gen 逻辑起子进程
  state.py       review.json 的读写（剧本家反馈落地的唯一入口）
  md_render.py   极简 markdown → HTML（只覆盖仓库文档实际用到的语法子集）
  md_tables.py   解析/改写分镜表等 GFM pipe-table，供网站在线编辑用
  media.py       受限静态文件服务，只映射 /media/<output/ 下相对路径>
web/frontend/
  index.html, app.js, api.js, shared.js, style.css   页面骨架/路由/API封装/公共组件/样式
  views/home.js         项目列表首页
  views/guide.js        渲染 content/guide.md 给剧本家看的操作指南
  views/style-bible.js  画风圣经查看
  views/characters.js   人物立绘查看+选片
  views/scenes.js       场景图查看+选片
  views/episode.js      分镜表查看+在线编辑（92行，含表格编辑逻辑）
  views/keyframes.js    关键帧图查看+重新生成
  views/videos.js       视频清单查看（121行，最复杂视图）
  views/inbox.js        剧本家反馈收件箱
web/content/guide.md    渲染给剧本家看的指南正文（改这个文件即可改指南内容）
```

后端 API 惯例：项目数据只从 `output/<剧名>/` 现有文件读取/回写，不额外存数据库；
"重新生成"对图片是真实调用（1-3分钟出一张），对视频只登记待办不执行。

## `scripts/gemini_client.py`

供 Claude Code 调用 Gemini API 的最小 CLI 客户端（128 行，仅 stdlib + requests）。
三个子命令：`test`（验证 key）、`image --prompt --out`（文生图）、
`text --prompt`（纯文本）。key 从根目录 `.env` 的 `GEMINI_API_KEY` 读取。

## 其他

- `.gitignore`：忽略 `.env`、`__pycache__/`、`*.pyc`、`**/_web_state/logs/`；
  `review.json` 本身**要**提交，不受影响。
- 根目录的 `.docx`/`.pdf` 是外部参考资料（剧本一卡通/短剧流水线说明），非本仓库
  生成的代码产出物，不建索引到子内容。
