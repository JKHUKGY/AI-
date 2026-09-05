# 故事与分镜

仅定位文件；实际操作读取对应 skill。路径相对当前宿主的 skills 根目录。
表中关键文件的省略前缀沿用最近的 `scripts/` 或 `references/`。

| 顺序 | Skill 目录 | 输入 → 输出 | 关键文件 |
|---|---|---|---|
| 1 | `short-drama-scout/` | 选题方向/大纲要点 → 故事梗概+人物小传+12-15集分集大纲 | `references/output_template.md`, `references/tiktok_trends.md` |
| 2 | `short-drama-storyboard/` | 故事/大纲 → 画风 + 逐集分镜表（含**机位**列）+ 人物三视图提示词 + **场景机位组**提示词（每地点 A主机位/B反打/C侧机位/D细节 + 空间关系） | `references/shot_grammar.md`, `character_prompt_template.md`, `scene_prompt_template.md`, `storyboard_methods.md`, `style_guide.md`, `checklist.md`, `interactive_review.md`（默认关闭的逐步确认模式协议） |
