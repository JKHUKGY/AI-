# 角色与场景的多代理生成和独立审查

本流程强制执行 [loop-picture-generation](../../loop-picture-generation/SKILL.md)
的至少四个真实 subagent 规则。旧的“两名代理分别生成并自查”流程不再使用。

角色与空场景没有参考依赖时，拆为 jobs_characters.json 和 jobs_scenes.json，
分别由 Generator A、Generator B 生成。Reviewer A实际逐张审图，Reviewer B
独立核对档案、画风及角色／场景参考一致性；两者均通过后主代理合并 selected.md。
依赖已选角色图的场景要等该图通过审查，不能提前调用。

只有一个可生成任务时，用一名生成者加三名独立审查者，仍只出该轮规定张数。
实际并发依宿主槽位限制分批调度；子代理总人数与运行槽位数分别记录。

脚本 --parallel N 控制图像子进程，不能替代 subagent 人数。统一计算各生成者
同时运行的图像任务；遇限流降低并发，不取消独立审查，不额外生成凑人数。
每名生成者写自己的输出及 manifest，由主代理合并，避免多个进程写同一公共日志。

调用模板和调度细则直接复用 loop-picture-generation/references 下的
generator_agent.md、reviewer_agent.md、batch_loop.md；原首轮1张及1→2→3阶梯保持。
