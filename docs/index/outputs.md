# 产出文件

路径相对仓库根。已知剧名和集号，直接代入下表；不知道版本才读 [项目目录](projects.md)。

## 优先给用户看的入口

已有 `output/<剧名>/给人看/` 时，用户查阅优先打开其中的 `阅读首页.html` 或
`README.md`：分镜表、已选图片、待处理图片、设定、审阅与进度分开排列。
JSON、源卡、任务、生成日志及候选原档放在 `机器文件/`。

当前 v3 已整理：`output/出狱后我成为了非洲矿王_v3/给人看/阅读首页.html`。
原 `storyboard/`、`assets/`、`keyframes/`、`videos/` 路径保留为兼容链接；
下表继续用于机器定位和脚本执行。更新源数据后运行该项目
`机器文件/刷新阅读入口.py`，刷新可读副本和图片入口。

## 制作源文件与兼容路径

每部剧目录结构：

```
output/<剧名>/
  project.json           网站新建项目的创建者、集数、时长、画风和审批要求
  source/script.txt      网站导入的原始剧本（上传原文件另存 uploaded_script.*）
  production_plan.md     后续图片/关键帧/视频/租卡审批清单
  storyboard/
    style_bible.md       画风圣经（视觉风格/色调/镜头语言总则）
    characters.md        人物设计提示词档案
    scenes.md             场景设计提示词档案
    outline.md            网站新项目的故事与分集规划
    ep01.md ~ ep0N.md     逐集分镜表（画面/动作/景别/运镜/时长/生成分级）
  assets/
    <人物名>_<状态>_正面|侧面转身|背面转身/   三视图图片（_00.png, _01.png...多版本供选）
    SC<编号>_<场景名>_<机位>_紧/            **紧底板**（近景/特写专用，由该机位的宽底板派生）
    <人物名>_表情_<表情名>/                    表情差分图
    SC<编号>_<场景名>[_日/夜版]/               场景图
    jobs_*.json           出图任务清单（喂给 generate_images.py 的输入）
    manifest.append.jsonl 出图记录追加日志
    selected.md           已选中/验收通过的图片记录
  keyframes/ep0X/
    ep0X_镜NN/             该镜关键帧图
    _master/               **场次主帧**（`master_<beat_id>/`，一个场次节拍一张「这个房间此刻的全貌」）
    keyframe_cards.json    关键帧卡 + **scene_beats**（人维护的唯一手写来源：在场名单/房间状态/走位/朝向/景别）
    keyframe_prompts_ep0X.md  提示词审阅表（阶段一交给人看的那一份）
    jobs_ep0X*.json        关键帧生成任务清单（由卡装配出来，不手改）
    keyframes.md           关键帧索引说明
    manifest.append.jsonl
  videos/ep0X/
    ep0X_镜NN.mp4           单镜视频结果
    ep0X_full_preview.mp4  拼接预览
    shot_cards.json       镜头卡（手写来源）
    h3_jobs.json / h3_remote_config.json  MiniMax-H3 任务及远端配置
    video_jobs.json/.md    图生视频提示词清单（LTX 专属字段版）
    ltx_remote_config.json / ltx_submit_results.json
    concat_list.txt        ffmpeg 拼接清单
  _web_state/
    setup.json / foundation.json  网站文字筹备进度与恢复断点
    prompt_history.json    按图片任务保存的手动/Codex 文字版本
    prompt_tasks.json      后台文字任务状态与结果，换页/刷新后可恢复
    approvals.json         图片预览快照、审批人及执行状态
    review.json            剧本家在协作网站上的评论/入选标记/编辑审计记录（**要提交**）
    logs/                  重新生成子进程临时日志（已 gitignore，不提交）
```

命名约定：`SC<两位数字>_<场景中文名>` 为场景 ID；人物图目录用
`<人物名>_<状态/造型>_<正面|侧面转身|背面转身>`；关键帧目录用 `ep0X_镜NN`。

## 定位顺序

- 找选定图片：先读 `assets/selected.md` 或该集 `keyframes.md` 的相关条目，再打开对应图片；不要展开所有候选图。
- 找某一镜：只列 `output/<剧名>/keyframes/ep0X/ep0X_镜NN/` 或在该集 jobs/卡中查镜号。
- 找提示词：关键帧看 `keyframe_prompts_ep0X.md`，视频看 `video_jobs.json` / `h3_jobs.json`。要修改则改对应卡，重新装配。
- 找反馈：`_web_state/review.json`；重新生成的临时日志在 `_web_state/logs/`。
- 文件缺失：先在该集/该阶段目录搜索；素材可能冷归档，见 [其他目录](repository.md)。文件数不等于验收通过数。
