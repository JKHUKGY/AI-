# ep01 视频提示词产物

本目录仅为准备阶段。shot_cards.json 是当前维护入口；authoring/initial_cards.py 仅保存初次手工编排过程，后续已修改卡片，不要重跑覆盖。

49 张卡和 video_jobs.json 一一对应；镜16第二段在 blocked_shot_cards.json / blocked_prompts，不是可提交任务。完整制作方案共38镜、50单元。执行前必须读 execution_manifest.json 和给人看/06_视频提示词/第01集_视频提示词.md。

重装配（在仓库根目录）：

```bash
python3 .agents/skills/short-drama-video-gen/scripts/build_prompt.py output/出狱后我成为了非洲矿王_v3/videos/ep01/shot_cards.json --lint
python3 .agents/skills/short-drama-video-gen/scripts/build_prompt.py output/出狱后我成为了非洲矿王_v3/videos/ep01/shot_cards.json -o output/出狱后我成为了非洲矿王_v3/videos/ep01/video_jobs.json --emit-prompts output/出狱后我成为了非洲矿王_v3/videos/ep01/prompts
python3 output/出狱后我成为了非洲矿王_v3/videos/ep01/verify_and_publish.py
```

verify_and_publish.py 是本次38镜/50单元方案的本地复核与阅读页生成器；后续改变拆段方案时需相应更新计数断言。它只检查卡片/路径/台词和重建阅读页，不生成视频、不上传网站或云盘。
