# 并行模式：角色和场景同时出图

拿到 `characters.md` / `scenes.md`（或分镜表里整理出的人物形象/场景背景
提示词）之后，如果角色 job 和场景 job 之间没有依赖关系，不需要"先出完角色
再出场景"顺序等待，可以两边同时跑。这里有两层并行，分开处理：

1. **单个 codex exec 内部**：脚本本身能不能让多个生成任务同时跑。
2. **角色 vs 场景**：能不能让"出角色"和"出场景"这两件事同时进行，而不是
   一个 agent 做完角色再回头做场景。

两层都做到，才是真正的"一键并行生成"，不是只加了个 `--parallel` 参数就算。

## 第一步：判断能不能并行

- **能并行**：场景是空镜头（不含人物），或者场景里的人物不需要保持"跟某个
  已选定的角色三视图长一样的脸"这种强一致性要求。这是最常见的情况——
  角色三视图和场景图各自独立生成，互不引用。
- **不能完全并行**：如果某条场景 job 的 `ref_images` 需要用到某个角色的
  三视图（比如"这张场景图里要带上主角背影，脸型要跟已选定的三视图一致"），
  这条场景 job 必须等对应角色三视图选出来之后才能跑，不能塞进并行批次，
  单独放进"角色出完之后"的第二批 job。
- 把 job 按这个标准拆成两个文件：`jobs_characters.json`（全部角色三视图）、
  `jobs_scenes.json`（不依赖角色图的场景），依旧按 `jobs_schema.md` 的格式写。
  有依赖的场景 job 先不写进去，等角色选定后再单独生成。

## 第二步：脚本内部并行（`--parallel`）

`generate_images.py` 支持 `--parallel N`：把这一批 job 里所有要生成的图片
（job x count 展开）放进一个线程池，最多同时跑 N 个 `codex exec` 子进程。

```bash
python3 .claude/skills/short-drama-image-gen/scripts/generate_images.py \
  output/<故事名>/assets/jobs_characters.json \
  --out-dir output/<故事名>/assets --parallel 3
```

- 默认 `--parallel 1`，跟原来的顺序行为完全一样，不主动加并发。
- Codex CLI 走的是 ChatGPT 账号额度，没有公开的并发限速文档。第一次用
  并行模式，先从 `--parallel 2`～`3` 试跑，观察 stderr 里有没有连续出现
  `codex 退出码` 非 0 或者反复超时——出现就说明触发限流了，把 `--parallel`
  调小重跑，不要一上来就设 `--parallel 8/10` 铺开，容易两边（角色+场景）
  一起被限流，反而更慢。
- 场景数量如果很多（十几个场景 x 多时段），仍然按原 SKILL.md 的建议分批
  组织 `jobs_scenes.json`，不要一次性把全剧场景都塞进一个并行池。

## 第三步：subagent 级并行——角色和场景同时跑

两个 jobs 文件都准备好之后，用 Agent 工具在**同一条消息里**发出两个调用，
而不是写完一个等结果、再写下一个：

- **Agent A（角色出图）**：只处理 `jobs_characters.json`，跑完之后按本
  skill `review_checklist.md` 的标准（含"三视图专属检查"）逐张验收，
  选出每个角色最终入选的那版三视图。
- **Agent B（场景出图）**：只处理 `jobs_scenes.json`，跑完之后按同一份
  checklist 验收场景图。

两个 agent 互不依赖对方的结果，可以完全同时跑，跑的过程中会有两组
`codex exec` 进程同时在跑（Agent A 的 `--parallel` 池子和 Agent B 的
`--parallel` 池子是各自独立的，互不共享）。

### Agent A（角色）prompt 模板

```
你负责本轮 AI 短剧出图任务里的"角色三视图"部分，不要碰场景相关文件。

1. 运行：
   python3 .claude/skills/short-drama-image-gen/scripts/generate_images.py \
     output/<故事名>/assets/jobs_characters.json \
     --out-dir output/<故事名>/assets --parallel 3

2. 命令结束后，对每个角色 job 新生成的图片，用 Read 工具逐张实际打开查看，
   按 .claude/skills/short-drama-image-gen/references/review_checklist.md
   的标准验收（含"三视图专属检查"：三个视角是否同一个人、比例是否一致、
   是否真的给了三个视角、半成品不能拆着用）。不合格就把不合格原因写成
   更明确的 prompt/反面提示词，追加 count 重新生成（同一个 job id 会接着
   编号），按 checklist"何时停止重试"的标准（单个 job 连续 3 轮选不出可用
   图就停下来问用户）控制轮次。

3. 完成后返回：
   - 每个角色 job 最终生成了几张、选中哪一张（绝对路径）
   - 淘汰的版本及具体原因
   - 这一轮总共成功生成了多少张图（数你自己触发的 manifest 新增行数）
   不要修改 jobs_scenes.json 或场景相关的任何文件。
```

### Agent B（场景）prompt 模板

```
你负责本轮 AI 短剧出图任务里的"场景图"部分，不要碰角色相关文件。

1. 运行：
   python3 .claude/skills/short-drama-image-gen/scripts/generate_images.py \
     output/<故事名>/assets/jobs_scenes.json \
     --out-dir output/<故事名>/assets --parallel 3

2. 命令结束后，对每个场景 job 新生成的图片，用 Read 工具逐张实际打开查看，
   按 .claude/skills/short-drama-image-gen/references/review_checklist.md
   的标准验收（构图/画风统一/无水印/是否符合场景描述等，场景图不需要看
   "三视图专属检查"那一节）。不合格就调整 prompt 重新生成，按 checklist
   "何时停止重试"的标准控制轮次。

3. 完成后返回：
   - 每个场景 job 最终生成了几张、选中哪一张或哪几张（绝对路径）
   - 淘汰的版本及具体原因
   - 这一轮总共成功生成了多少张图
   不要修改 jobs_characters.json 或角色相关的任何文件。
```

## 第四步：合并结果

两个 subagent 都返回后，主 agent（你）负责：

- 把两份报告合并成一份汇报给用户：这一轮起了几个角色 job、几个场景 job、
  各自用的并行度、分别选出了什么、总共成功生成了多少张图。
- 检查两边有没有意外用了同一个 `job_id`（正常不会发生，角色和场景的命名
  规则本来就不同，见 `jobs_schema.md`），确认无冲突后，把两边选中的条目
  一起写进同一份 `output/<故事名>/assets/selected.md` 登记表。
- 两个 subagent 各自往同一个 `manifest.append.jsonl` 追加记录时，脚本内部
  用锁保证一次只有一个线程在写、每次追加完整一行，两个独立进程分别调用
  脚本互不冲突，不会出现半行数据或互相覆盖。
- 如果之前拆出了"依赖角色图的场景 job"，等角色三视图选定后，把它们的
  `ref_images` 填成选中的三视图路径，作为下一轮单独生成（这一轮不参与
  并行，因为它就是要等角色结果）。

## 什么时候不值得用并行模式

- 角色和场景加起来只有几个 job、预计几分钟能跑完顺序模式的场景，没必要
  为了并行多起一层 subagent 编排开销。
- 场景 job 大量依赖角色图（每个场景都要求带上某个角色、保持脸型一致），
  这种项目里"能并行的场景"所剩无几，直接走顺序模式更省事。
