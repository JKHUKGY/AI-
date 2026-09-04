# 仓库索引

> 给 Claude 用的定位地图：先查这份文件找到目标区域，再按需读取具体文件，
> 避免整仓库探索。本仓库是"AI 短剧全流水线"——从选题到分镜、出图、关键帧、
> 图生视频提示词、LTX 本地生成、剧本家协作网站。
>
> 配套入口是 `index` skill（`.claude/skills/index/`）：仓库外的资源（网址/账号/
> 云主机/原始素材）查它的 `references/resources.md`，实时进度跑它的
> `scripts/snapshot.py`。本文件只管仓库内的文件定位。

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
| 项目需求背景 + AI 已做工作日志 | `需求.md` |
| 协作网站使用说明（给人看） | `web/README.md` |
| **现在做到哪一步了**（每部剧各环节实时进度） | 跑 `python3 .claude/skills/index/scripts/snapshot.py`，别信任何文档里写死的进度数字 |
| **线上网址 / 登录账号 / 云主机 / API key / 原始剧本 docx** 在哪 | `.claude/skills/index/references/resources.md`（仓库外的资源清单） |
| 提示词/分镜方法论为什么是这样 | `研究.md`（skill 里的硬规则大多出自这里） |

## 顶层目录

```
.claude/skills/   10 个 skill：7 个流水线环节（选题→分镜→出图→关键帧→镜头卡/视频提示词→LTX校验→LTX执行）
                  + 2 个双 agent 循环（loop-picture-generation / loop-video-generation）
                  + index（定位入口：找不到东西/不知道进度时先用它）
output/           按剧名分目录的产出物（storyboard/assets/keyframes/videos/_web_state）
web/              剧本家协作网站（纯 stdlib Python 后端 + 无构建前端）；线上正式站
                  https://scriptwriter-jia.northcentralus.cloudapp.azure.com （账号/运维见 resources.md）
需求.md           原始需求 + 按日期记录的"AI 已做"工作日志（追加式，找历史决策先看这）
研究.md           方法论长文：剧本→分镜图→图生视频的提示词到底怎么写（skill 规则的出处）
README.md         给人看的流水线使用说明（每步的触发词 + 环境准备）
《出狱后我成为了非洲矿王》一卡.docx / 短剧流水线.pdf / 列车重逢/   外部素材与参考资料，非本仓库产出
```

## `.claude/skills/` —— 流水线环节（按执行顺序）

| 顺序 | Skill 目录 | 输入 → 输出 | 关键文件 |
|---|---|---|---|
| 1 | `short-drama-scout/` | 选题方向/大纲要点 → 故事梗概+人物小传+12-15集分集大纲 | `references/output_template.md`, `references/tiktok_trends.md` |
| 2 | `short-drama-storyboard/` | 故事/大纲 → 画风 + 逐集分镜表（含**机位**列）+ 人物三视图提示词 + **场景机位组**提示词（每地点 A主机位/B反打/C侧机位/D细节 + 空间关系） | `references/shot_grammar.md`, `character_prompt_template.md`, `scene_prompt_template.md`, `storyboard_methods.md`, `style_guide.md`, `checklist.md` |
| 3 | `short-drama-image-gen/` | 人物/场景提示词 → 三视图立绘 + 场景图（Codex CLI 出图） | `scripts/generate_images.py`, `references/jobs_schema.md`, `parallel_mode.md`, `review_checklist.md`, `api_setup.md` |
| 4 | `short-drama-keyframe-gen/` | **两阶段、中间一道人工闸门**。阶段一：分镜表 + 已选人物/场景图 → **关键帧卡 `keyframe_cards.json`**（逐人写位置/纵深层/身体朝向/**相对镜头露多少脸**/视线/瞬间动作 + 景别对应的裁切线）→ `build_keyframe_prompt.py` 机械装配出提示词、审阅表 `keyframe_prompts_ep0X.md` 和 `jobs_ep0X.json`，**提示词是派生产物，不手写**；停下来等用户确认走位。阶段二：确认后才出图（全量每一镜，不按 S/A/B/C 筛选）| `scripts/build_keyframe_prompt.py`（装配+校验）, `references/keyframe_card_schema.md`, `blocking_guide.md`（走位/朝向/景别规则，每条带实拍证据）, `keyframe_prompt_guide.md`（素材查找+分镜表列对应）, `shot_selection.md`, `keyframe_review_checklist.md`, `examples/ep03_keyframe_cards.json`(+`_v1_replica`) |
| 5 | `short-drama-video-gen/` | 关键帧 + 运动描述 → **镜头卡 `shot_cards.json`**（4-8 秒生成单元，逐拍结构化）→ 按选定模型分别装配：`build_prompt.py`→`video_jobs.json`（LTX-2.5）/ `build_h3_prompt.py`→`h3_jobs.json`（MiniMax-H3）。**同一份卡喂两个模型，提示词是派生产物，不手写。** B 级跟 S/A 级一样走 LTX，`ken_burns.py` 只是反复生成失败时的兜底 | `scripts/build_prompt.py`（LTX 装配+校验）, **`build_h3_prompt.py`（MiniMax-H3 装配+校验）**, **`rekey_shot.py`（L2 升级管道：改关键帧卡→重出图→回填首帧→重装配）**, `extract_frames.py`, `ken_burns.py`, `references/shot_card_schema.md`, **`keyframe_escalation_guide.md`（故障→L1视频层/L2关键帧层/L3分镜层 的路由表）**, `model_capability_ledger.md`（模型能做/做不到清单，每条带证据）, `video_prompt_guide.md`, `stability_playbook.md`, `video_jobs_schema.md`, `video_review_checklist.md`, `video_platform_comparison.md` |
| 6 | `short-drama-ltx-export/` | **LTX-2.5 通道**的提交前关卡：校验 `video_jobs.json`（路径/64整除/8k+1/台词语言声明/seed/token 预算/否定句/first_frame_strength/**是否还和镜头卡一致**）+ `ltx_remote_config.json` + `--dry-run` | `scripts/validate_video_jobs.py`, `references/resolution_presets.md` |
| 7 | `short-drama-ltx-generate/` | **LTX-2.5 通道**的执行：真实租显卡（只剩 RunPod，`rent_cheapest` 够用就行最便宜优先）→ `ltx_ssh_submit.py` 每镜跑一次 CLI（实测要 80GB，每镜重装 67GB 权重）→ 下载、验收、**用完关机**。⚠️ **本目录下的 GPU 运维资产是两条视频通道共用的** | `scripts/ltx_ssh_submit.py`, `ltx_batch.py`, **`runpod_ops.py` / `gpu_teardown.py` / `idle_shutdown_watchdog.py`（共用）**, `references/runpod_gpu_ops.md`（共用）, `ltx_pipeline_gotchas.md` |
| 6′ | `minimax-h3-export/` | **MiniMax-H3 通道**的提交前关卡：驱动 `build_h3_prompt.py` 把同一份镜头卡装配成 **ref2va 六段结构化提示词** + `h3_jobs.json`（**装配即校验**）+ `h3_remote_config.json` + `--dry-run` 看真实 HTTP 请求体 | 无自有脚本（装配器在 `short-drama-video-gen/scripts/`） |
| 7′ | `minimax-h3-generate/` | **MiniMax-H3 通道**的执行：租显卡（**门槛低得多，1×RTX 4090 24GB 就够，$0.34/hr**）→ 部署 SGLang Diffusion → 下 Ref2VA 权重 → 起**常驻服务**（权重只装一次）→ SSH 隧道 + `h3_submit.py` 走 HTTP 提交 → 抽帧**+听审**验收（原生立体声）→ 关机 | `scripts/h3_submit.py`（自建 SGLang）, **`h3_cloud_submit.py`（官方云 API，不租卡、能出 2K、没有 seed）**, `references/minimax_h3_ops.md`, **`minimax_cloud_api.md`（官方云 API 规格 + 跟自建那份 jobs 的四处落差）** |

双 agent 循环（可选，替换上面某一环的"生成+验收+重试"部分）：

| Skill 目录 | 替换谁 | 说明 |
|---|---|---|
| `loop-picture-generation/` | `short-drama-image-gen`/`keyframe-gen` 的出图+验收 | 出图 agent + 审查 agent，4 路并行 |
| `loop-video-generation/` | `short-drama-ltx-generate` 的提交+验收+重试 | Generator + Reviewer，**严格串行**（都抢同一块显卡）。审查只对照 `script_ref`（剧本原文），不拿分镜表"画面描述"自问自答；`fix_instruction` 指向**镜头卡的字段** |

每个 skill 目录下都有 `SKILL.md`（含 `description` frontmatter，触发关键词见其中）、
可选的 `scripts/`（可执行脚本）、`references/`（详细方法论/规范文档）、部分还有
`examples/`（如 `short-drama-scout/examples/千金归位-她让全家跪着道歉`）。

## `output/<剧名>/` —— 每部短剧的产出物（固定结构）

目前 `output/` 下有这些目录（**进度数字一律以 `snapshot.py` 的实时输出为准**，
下面只写它是什么、别拿这里的描述当最新状态）：

| 目录 | 是什么 |
|---|---|
| `出狱后我成为了非洲矿王/` | 主线项目、进度最全：10 集分镜表，前 3 集有关键帧和视频 |
| `出狱后我成为了非洲矿王_v2/` | 同一部剧按新版 skill（机位组场景图 + 三视图 + 走位枚举）**从剧本重做**的一版。2026-09-03 进度：`style_bible.md`/`characters.md`(11角色)/`scenes.md`(14地点) 齐全；**素材 81 张已验收 0 返工**（8 个角色三视图 + 7 个地点 20 张机位底板，含二楼俯拍与桌面俯拍两张专用底板）；**分镜表 ep01-ep03 已完成**（95 镜，逐镜含机位/纵深/相对镜头朝向/视线）；尚未出关键帧。**要改这部剧一律看 v2，旧目录只留作对照** |
| `千金归位/` | 早期整条链跑通的样例（立绘/关键帧/视频齐全），但没有独立 `storyboard/` 目录 |
| `暗局/` | 早期阶段，仅 ep01 分镜+部分素材 |
| `雪山决斗/` | 单镜试拍，只有 `refs/` 和 `videos/shot01/`，用来验证 LTX 生成链路 |
| `_pilot_机位组/` | 试拍目录，不是一部剧：验证"一个场景出 A主机位/B反打/C侧机位/D细节 一组底板"这套机位组做法 |

每部剧目录结构：

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
    keyframe_cards.json    关键帧卡（人维护的唯一手写来源：走位/朝向/景别）
    keyframe_prompts_ep0X.md  提示词审阅表（阶段一交给人看的那一份）
    jobs_ep0X*.json        关键帧生成任务清单（由卡装配出来，不手改）
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

## 其他

- `.gitignore`：忽略 `.env`、`__pycache__/`、`*.pyc`、`**/_web_state/logs/`、
  租显卡平台的 `runpod_config.json`、以及协作网站的
  `web/server/data/`（登录账号哈希 + 会话密钥，换机器部署要重新 `manage_users.py add`）。
  `review.json` 本身**要**提交，不受影响。
  → 所以"找不到账号/key/显卡配置"是正常的，它们按设计就不在仓库里，见
  `.claude/skills/index/references/resources.md`。
- 根目录的 `.docx`/`.pdf` 是外部参考资料（剧本一卡通/短剧流水线说明），非本仓库
  生成的代码产出物，不建索引到子内容。
