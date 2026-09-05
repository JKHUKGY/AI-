# unit、代理与审查记录

unit 对应一个角色三视图、场景、场次主帧或逐镜关键帧任务。
旧队列升级时保留已有图片、原文、轮次及结论；不能因增加 subagent 而重新从第1轮出图。

## units_queue.json

| 字段 | 含义 |
|---|---|
| id / type | 唯一任务ID；character_turnaround / scene / scene_master / keyframe |
| source_card / source_version | 有卡片时记录源文件、条目定位和版本；原任务无卡片时记录源 jobs |
| prompt / ref_images | 从当前源卡机械装配的完整提示词和实际参考路径；生成者不改派生内容 |
| storyboard_ref | 剧本／角色／场景原文逐字摘录；关键帧用 script_ref_zh，不拿画面描述代替剧本 |
| approved_design_refs | 已确认走位卡、画风、角色、底板及主帧等验收输入路径 |
| depends_on | 依赖的角色图或场次主帧 unit ID；未通过前不能执行依赖任务 |
| round_count | 已完成的生成及全部独立审查轮数，初始0，最多3；继承既有历史 |
| count_per_round | 第1轮1张、第2轮2张、第3轮3张；不按代理人数乘张数 |
| status | pending / active / passed / capped / blocked_dependency / technical_error |
| history | 每轮保存真实 generator_agent_id、reviewer_agent_ids、files、每位审查者的 review_scope/verdict/reason/inspected_files/proposed_file、字段修改及调用错误 |
| selected_file | 仅 passed 时填写所有必需 Reviewer 均通过的同一文件；其他状态留空 |
| best_candidate | 到限后最接近的候选及差异，仅供用户查看，不能供下游当作已选素材 |

审查过程中如生成已完成但尚缺 Reviewer，在 history 中记录待审项，不能因为
round_count尚未增加而重复启动该轮生成。审查已有候选不增加生成次数。

## agent_roster.json

每个真实 subagent 记录 `agent_id`、`role`、`unit_ids`、`deliverables`、
`started_at`、`finished_at` 和实际运行状态。人数只统计有实质交付的不同真实ID。
批次记录 `required_distinct_subagents: 4`、宿主实际槽位限制及最高同时运行数。
主代理与图像工具/CLI进程不计数。少于四个不能将本工作流标为完成。

默认两名不同 Generator 各承担任务，R1逐张审查，R2连戏检查；单任务改为
一个 Generator、三个独立 Reviewer。角色名称对应真实调用，不用同一代理反复
改名凑数。记录各自独立报告路径，最后由主代理合并公共队列和最终登记。
