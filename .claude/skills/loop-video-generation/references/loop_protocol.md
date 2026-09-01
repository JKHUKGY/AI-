# 单镜顺序循环，最多三轮

这是 orchestrator（跑本 skill 的你）要执行的调度算法，把
`units_queue.json` 里的镜头逐个跑完。跟 `loop-picture-generation` 的 4
槎位并行不同，这里**严格顺序处理**：同一时刻只有一个 unit 处于 `active`。

## 为什么不并行

出图并行是因为每一路调的是独立的 Codex CLI（各自的 ChatGPT 账号额度），
互不抢资源。视频生成不一样：所有 `ltx_ssh_submit.py` 调用都打到**同一台
租来的显卡实例**上，显存和算力是唯一的——同时提交多个生成任务只会互相
抢显存，大概率其中一个 OOM 失败，或者被 CUDA 排队变成事实上的串行执行，
既没有变快、又多了一层"看起来在并行但其实互相干扰"的排查成本。除非用户
明确说自己租了多台互相独立的显卡实例，否则不要尝试对这个 skill 做类似
`loop-picture-generation` 的多槎位改造。

## 开始循环前确认一次 pipeline 特性（避免把基础设施问题当成内容问题反复重试）

- 如果这一批用的是 `ltx_pipelines.dfr_pipeline`（生产质量档），确认
  `--detailing-lora` 权重已经下载好——这个仓库是**独立于主仓库的 gated
  repo**，需要用户在它自己的 Hugging Face 页面单独 accept 一次条款，跟
  主仓库 `Lightricks/LTX-2.5` 的授权是两回事（`ltx_pipeline_gotchas.md`
  "DFR pipeline"一节）。没确认过就先确认，避免第一个 unit 就因为 403
  卡住，被误判成"这个镜头有问题"。
- 确认远程环境用的是**卷积版 VAE**（`ltx-2.5-video-vae-conv-bf16.safetensors`）
  而不是 diffusion VAE，尤其是 Blackwell 架构显卡——不确认这一点，循环
  跑到某个 unit 突然 `CUBLAS_STATUS_INTERNAL_ERROR` 崩溃时会误以为是这
  个镜头的提示词/参数问题去调 `fix_instruction`，实际上跟内容毫无关系。
  这两条本该在 `short-drama-ltx-generate` 第 2-3 步就确认过，这里只是
  循环开始前的最后一道提醒，不要跳过。

## 循环

对队列里每个 `pending` 的 unit，按队列顺序依次执行（前一个 unit 结束
——`passed` 或 `capped`——才开始下一个）：

1. `status` 改 `active`，`round_count` 保持从上次中断处继续（正常情况下
   一个 unit 从 0 开始，`seed` 从一个固定初始值比如 `10` 开始）。
2. **Generator**：发一次 Agent 调用（参照 `references/generator_agent.md`
   的模板），用测试档参数（`duration_sec_test`/`resolution_test`）提交
   生成、下载、抽帧。第一轮（`round_count == 0`）一定是整段生成；如果是
   接着上一轮 `fail` 且上一轮 Reviewer 给了 `defect_window` 的重试，改用
   `generator_agent.md`"局部重绘模式"一节的 `--retake` 调用，不整段重来。
   等它返回。
   - 如果返回的是 `error`（技术性障碍，见 `generator_agent.md`"技术性
     障碍 vs 内容质量问题"一节），**不计入 `round_count`**，`status` 改
     `blocked`，把错误原文报给用户，按 `ltx_pipeline_gotchas.md` 的已知
     条目处理（比如换卷积版 VAE、补 HF 授权）后再回到这一步重跑，不要
     当成一次内容重试消耗轮次。
3. **Reviewer**：发一次 Agent 调用（参照 `references/reviewer_agent.md`
   的模板，记得告诉它这是第几轮），拿到 verdict。
4. **更新状态**：
   - `round_count += 1`（只有走到这一步、真的拿到 verdict 才算一轮）。
   - `verdict: fail` 且 `round_count < 3` → 把 `fix_instruction` 落实进
     `prompt`（**不落在 `negative_prompt`/`ref_images`**，这两个字段对
     这个 pipeline 都不生效）；如果 Reviewer 判断是"随机采样运气差"，换
     一个新的 `seed` 值（不要沿用上一轮的 seed，否则同一个 prompt+同一个
     seed 会拿到几乎一样的结果）；必要时按 `stability_playbook.md` 拆段。
     如果 Reviewer 给了 `defect_window`，记进 `history` 这一条，下一次
     第 2 步走局部重绘；没给就走整段重来。
   - **局部重绘（`--retake`）用完之后仍要判断一次**：Reviewer 复核局部
     重绘的产物时，只需要看这个时间窗口本身有没有修好、跟前后片段的
     衔接是否自然，不需要重新走一遍情节吻合度的全套判断（那部分在上一
     轮已经判过、且没受影响）；复核 `fail` 就还是按上面的规则处理，
     `round_count` 照常累加。
   - `verdict: fail` 且 `round_count == 3` → `status` 改 `capped`，记下
     `best_of_all` 和 `downgrade_suggestion`，这个 unit 结束，进入下一个
     unit。
   - `verdict: pass` → 进入第 5 步的正式档确认，不直接标记 `passed`。
5. **正式档确认**（测试档 `pass` 之后，不算独立的"重试轮"，是把已经验证
   过的参数升级到目标分辨率/时长这一步）：再发一次 Generator 调用，改用
   `duration_sec_final`/`resolution_final`，**`prompt`/`seed` 保持跟测试档
   `pass` 那一轮完全一致**（升级分辨率/时长本身就可能带来变化，不要在同
   一步里又顺手换 seed，那样出问题时分不清是"分辨率/时长切换"还是"运气
   不好"造成的）；抽帧后再发一次
   Reviewer 调用做轻量复核（这次不需要重新逐条判断情节吻合度，主要看
   "分辨率/时长切换本身有没有引入新问题"，比如更长时长下动作后段是否
   失控）。
   - 复核 `pass` → `status` 改 `passed`，`final_confirmed: true`，
     `selected_file` 填这次的正式档视频路径，unit 结束。
   - 复核 `fail` → 这一步的失败计入 `round_count`（`+1`），如果因此
     达到 3 就按上面 `capped` 的规则处理；没达到 3 就把这次复核暴露的
     问题当 `fix_instruction`，回到第 2 步用测试档参数重新验证一遍再升级，
     不要直接在正式档上反复重试（浪费更多显卡时间）。
6. 取队列里下一个 `pending` unit，回到第 1 步；队列空了，进入
   `SKILL.md` 第 4 步的汇总。

## 一个例子

队列里有镜3、镜7、镜11 三个 unit：

- 镜3：测试档第 1 轮就 `pass`，正式档确认也 `pass` → `passed`，
  总共 2 次生成调用。
- 镜7：测试档第 1 轮 `fail`（背景闪烁），落实 `fix_instruction` 后第 2
  轮 `pass`，正式档确认 `pass` → `passed`，总共 3 次生成调用。
- 镜11：测试档 3 轮都 `fail`（同一角色反复换脸）→ `capped`，Reviewer
  给出 `best_of_all` 和 `downgrade_suggestion`（建议降级成 B 级纯运镜），
  总共 3 次生成调用，交给用户决定。
- 镜9：测试档第 1 轮整段生成后 `fail`，Reviewer 判断"只有 1.5-2.5 秒背景
  闪烁了一下，其余都正常"，给了 `defect_window: {start: 1.5, end: 2.5}`；
  第 2 轮走 `--retake 1.5 2.5` 只重绘这一小段（不是整段重来），复核
  `pass`，正式档确认也 `pass` → `passed`，总共 1 次整段生成 + 1 次局部
  重绘 + 1 次正式档确认，比整段重来 3 次省下不少显卡时间。

镜3 处理完才开始镜7，镜7 处理完才开始镜11——全程只有一个 Generator/
Reviewer 在跑，显卡上始终只有一个生成任务，不存在互相抢资源的情况。
