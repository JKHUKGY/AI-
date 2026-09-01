# Generator agent（出图 agent）

## 职责边界

只做一件事：把 unit 当前这一轮的 `prompt` 变成图片，调用已有的
`short-drama-image-gen/scripts/generate_images.py`。**不自己评判这条
prompt/修改意见是否合理，不自己决定要不要按 Reviewer 的意见改**——每一轮
的 `prompt` 已经是 orchestrator（跑这个 skill 的你）根据上一轮 Reviewer
的 `fix_instruction` 更新好的最终版本，Generator agent 拿到就是"照单生成"，
不需要重新措辞、不需要补充自己的想法、也不需要对着上一轮的修改意见提出
异议或打折扣执行。

唯一允许"停下来报错而不是硬生成"的情况是遇到**技术性障碍**：prompt 里
引用的 `ref_images` 文件路径不存在、或者 `codex` 未登录/连续报错退出——
这些要报得具体（缺哪个文件、codex 报了什么原文），不能含糊说"生成不了"。
除此之外，不允许因为"跟上一轮改动不大、感觉没必要重跑"之类的理由跳过
生成——只要 orchestrator 发起了这一轮调用，就要真的跑一遍 `codex exec`。

## 何时被起、要不要记住上一轮

每个 unit **每一轮都单独起一个新的 Generator agent**，不复用上一轮的 agent
实例。agent 不需要记得"上一轮生成过什么"，因为 orchestrator 已经把这一轮
最终 prompt、参考图、要生成几张都直接写在了调用它时的 prompt 里；文件
编号靠 `generate_images.py` 自己按已有文件数量接着往后编，Generator agent
也不需要关心这一点。

## Agent 调用模板

对处于"这一轮要生成"状态的每个 unit（新进槎位的 round 0，或上一轮 `fail`
且 `round_count < 3` 的），在**同一条消息里**为每个 unit 各发一次 Agent
调用（一次最多 4 个，凑够本轮活跃槎位数即可，不需要一定填满 4 个），
`subagent_type` 用 `general-purpose`（或省略，走默认）。prompt 参照：

```
你是本轮 AI 短剧出图任务里"<unit.id>"这一个镜头/角色/场景的出图 agent，
只处理这一个 unit，不要碰其它 unit 的文件。

1. 这是本轮要用的完整提示词，已经包含了如果上一轮被 Reviewer 打回的修改
   意见——你不需要评判这个提示词是否合理、是否应该照做，直接照它生成：
   """
   <unit.prompt 当前值>
   """
   参考图（ref_images，可能为空）：<unit.ref_images 列表，给出绝对路径>
   本轮要生成 <unit.count_per_round> 张。

2. 写一份只含这一个 job 的 jobs.json（id 固定用 "<unit.id>"，这样新图会
   接着已有文件往后编号、不会覆盖前面几轮生成的图），放在
   <临时 jobs 文件路径>，然后运行：
   python3 .claude/skills/short-drama-image-gen/scripts/generate_images.py \
     <临时 jobs 文件路径> --out-dir <unit 对应输出目录>

3. 命令结束后，只报告这一轮**新增**的文件（不要把之前几轮已经生成过的旧
   文件也列进来），按下面格式返回：
   files: <这一轮新增文件的绝对路径列表>
   error: <如果 codex 报错/目标文件没生成，具体错误原文；正常完成留空>

不需要你自己看图判断好不好，审查是另一个 agent 的工作，你只负责把图吐
出来并报告生成结果。
```

## "无条件执行"具体意味着什么

- 返回结果里不需要评价"我觉得这个修改意见其实……"，也不需要建议
  orchestrator 换个思路——如果确实觉得 prompt 有技术性问题（比如引用了
  不存在的参考图），在 `error` 字段里指出，而不是对 prompt 的内容提意见。
- 不允许"觉得跟上一轮差别不大就跳过不跑"，orchestrator 每发起一次调用都
  代表这一轮确实要重新生成。
