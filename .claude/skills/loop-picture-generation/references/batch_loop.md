# 最多 4 槎位并行批处理循环

这是 orchestrator（跑本 skill 的你）要执行的调度算法，把
`units_queue.json` 里的所有 unit 跑完。核心目的：任何时刻最多 4 个 unit
同时占用槎位、同时有 `codex exec` 在跑；一个槎位空出来立刻补下一个 unit
进来，**不要**处理完固定一批 4 个才开始下一批——那样如果某个 unit 一轮就
过、另一个卡到 3 轮，先跑完的槎位会空等，白白浪费并行度。

## 状态

对应 `units_queue.json` 里每条 unit 的 `status` 字段，维护三类：

- `pending`：还没开始。
- `active`：当前占用槎位（最多同时 4 条是这个状态）。
- `passed` / `capped`：跑完了，已经离开槎位。

## 循环

1. **补槎位**：只要 `active` 数量 < 4 且还有 `pending`，就把 `pending`
   队首的 unit 挪进 `active`（`round_count` 保持 0，`prompt` 用原始版本）。
2. 如果 `active` 为空（说明 `pending` 也空了），结束，进入 `SKILL.md` 第
   4 步的汇总。
3. **本轮 Generator 批次**：`active` 里所有"这一轮要生成"的 unit（刚进
   `active`，或者上一轮 `fail` 且 `round_count < 3`），在同一条消息里为
   每个 unit 各发一次 Agent 调用（参照 `references/generator_agent.md` 的
   模板），数量 = 这一批要生成的 unit 数（≤4）。等这条消息里全部 Agent
   调用都返回。
4. **本轮 Reviewer 批次**：对上一步刚生成完的 unit，同一条消息里各发一次
   Agent 调用（参照 `references/reviewer_agent.md` 的模板，记得告诉它这是
   第几轮）。等全部返回。
5. **更新状态**：对每个刚拿到 verdict 的 unit：
   - `round_count += 1`。
   - `verdict: pass` → `status` 改 `passed`，`selected_file` 填
     Reviewer 给的文件，离开槎位。
   - `verdict: fail` 且 `round_count < 3` → 把 `fix_instruction` 拼进
     `prompt`（原 prompt 末尾追加"上一轮反馈：<fix_instruction>"这类
     明确表述），留在 `active`，等下一次循环的第 3 步再生成。
   - `verdict: fail` 且 `round_count == 3` → `status` 改 `capped`，
     `selected_file` 填 `best_of_all`，离开槎位。
6. 回到第 1 步。

## 一个 6 个 unit 的例子，说明为什么要"随时补槎位"

假设队列里有角色三视图 A、B，场景 C、D，关键帧 E、F 共 6 个 unit：

- 第一轮：`active = [A, B, C, D]`（先补满 4 个），E、F 还在 `pending`。
- 都跑完一轮 review：A `pass`、C `pass`、B `fail`（round_count=1）、D
  `fail`（round_count=1）。
- 这时**不是**"等这一批 4 个全部结束才拉下一批"，而是 A、C 空出来的槎位
  立刻补 E、F 进来：`active` 变成 `[B(第2轮), D(第2轮), E(第1轮), F(第1轮)]`，
  B、D 用刚更新过的 prompt 继续第 2 轮，E、F 是全新开始第 1 轮——四个槎位
  继续同时跑，不会出现"E、F 干等 B、D 跑完 3 轮才能开始"的空转。

## 什么时候不值得维护 4 槎位

- 队列里总共只有 1-3 个 unit：直接按各自的进度并行发 Agent 调用即可，不
  需要套这套补槎位逻辑（本来就不存在"槎位不够用"的情况）。
- Generator agent 报出疑似限流的错误（`short-drama-image-gen/references/api_setup.md`
  描述的那类连续非零退出/超时）：把并发槎位数从 4 调小到 2 甚至 1，跟
  `short-drama-image-gen/references/parallel_mode.md` 里"先从小并发试跑"
  的建议一致，不要在明显限流的情况下硬撑 4 并发。
