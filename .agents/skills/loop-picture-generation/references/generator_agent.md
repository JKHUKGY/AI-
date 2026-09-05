# Generator 子代理任务模板

人数和调度先读 [../SKILL.md](../SKILL.md) 与 [batch_loop.md](batch_loop.md)。
Generator 职责固定，只执行已装配的任务；不自行判断候选合格、不作最终选图。

派发时给出：unit ID、轮次及历史、源卡版本、完整 prompt、绝对参考图路径、
本轮张数、独立输出目录。同一 unit 同一轮只能有一个 Generator 负责，避免重复花额度。

```text
你是本批次的 Generator <真实 agent ID 对应角色>，只处理 <unit IDs>。
按提供的 jobs 原样调用可用且已授权的图像生成工具，或项目原有 generate_images.py。
使用当前宿主 skill 路径；Codex 为 .agents/skills，Claude 为 .claude/skills。
先实际查看未看过的参考图；输出、临时文件和日志遵守项目 AGENTS.md 的写入范围。
若调用渠道不能满足写入范围、引用数量或其他实际限制，报告具体障碍，不绕过权限。
本轮生成 <1/2/3> 张：<完整 job 和参考图>。
只写 <分配目录>，保留之前候选。不要写共享队列和最终选图登记。
照完整反馈执行；有卡片的任务不手改派生 prompt，有冲突则报告字段与阻碍。
不要评价图片通过与否，审查由不同的子代理完成。
返回真实 agent ID、unit ID、round、实际新增 files、调用/错误记录和源 job 版本。
```

工具返回前的错误不算成功产图；部分成功时保留已有文件、报告缺额，不能重跑整轮
覆盖或多算图片。工具和脚本子进程不另算 subagent 人数。
