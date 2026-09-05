# 第01集执行状态

用户先前的“ok／继续完成主帧和关键帧”出图批准持续有效。2026-09-05 又明确允许项目外工具临时输出目录及任务内自动审批；见机器文件/多代理续做/execution_approval.json。宿主强制权限仍由系统控制。

- 原38镜剧情、风格与人物设定保持批准版本；按独立审查反馈澄清构图与画内／画外信息。
- 主帧累计28张，已选3张；监狱p2/p3与别墅v1到限，17个依赖镜头保持阻塞。
- 关键帧实际状态以 generation_status.json、keyframe_generation.json 和 keyframes.md 为准；首轮1张、第二轮2张、第三轮3张，历史次数不重置。
- 镜19_02通过两位独立审查，已选。镜17/18/20已到限未通过；镜21–25等待后续修正；客房35–38正在首轮审查。
- 剩余可独立镜头按机器文件/多代理续做/keyframe_batch_schedule.json继续；未通过候选保持可见且不混入已选目录。

## 当前装配入口

使用 `python output/出狱后我成为了非洲矿王_v3/机器文件/build_keyframe_jobs.py output/出狱后我成为了非洲矿王_v3/keyframes/ep01/keyframe_cards.json -o output/出狱后我成为了非洲矿王_v3/keyframes/ep01/jobs_ep01.json`。

这个项目适配器复用原skill的全部校验和机械装配，允许源卡显式指定 `reference_strategy=plate_plus_master`，以及 `framing.subject_measurement`：全身高度从头到鞋底测量，裁切人物按指定清晰主体与头顶留白计算。镜17的主帧较紧，原默认只能向内裁切，故改用空场景底板定义环境取景、主帧定义身份道具。原skill脚本内容未改；首次参考图适配已验证其余37张卡装配相同；后续裁切适配仅由明确源卡字段启用，原skill脚本未改。

`jobs_ep01.json`含全38镜，不可绕过依赖检查整体提交。实际生成读取机器文件/多代理续做中的指定批次jobs，保留每个unit轮次和candidate编号。
