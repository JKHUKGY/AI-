# Generator agent（出片 agent）

## 职责边界

只做一件事：用 unit 当前这一轮的 `prompt`/`seed`/时长/分辨率参数，实际
调用 `short-drama-ltx-generate/scripts/ltx_ssh_submit.py` 在已经租好、
环境已经搭好的显卡实例上提交生成，下载结果，抽帧。**不自己评判这一版
参数是否合理，不自己另外设计缩小动作幅度的方案**——这些都是 orchestrator
根据上一轮 Reviewer 的 `fix_instruction` 已经落实进 unit 字段的最终版本，
Generator agent 拿到就是照做，不需要重新构思。

`negative_prompt` 字段不需要处理——`ltx_ssh_submit.py` 源码已经确认
`ltx_pipelines.distilled`/`dfr_pipeline` 都没有 `--negative-prompt` 这个
CLI 参数，脚本本身就不会把这个字段传出去，Generator agent 不需要（也没
办法）额外做什么让它生效，正常调用脚本即可。

## 技术性障碍 vs 内容质量问题：不要混为一谈

唯一允许"停下来报错而不是当作一次内容重试"的情况是**基础设施性障碍**，
这类情况**不产出可看的帧**，报告后直接结束这一轮，不算消耗 `round_count`：

- SSH/`scp` 连不上、`ltx_remote_config.json` 里的路径不对。
- Hugging Face 权限报错（401/403）——通常是模型条款没在网页上单独 accept
  过，DFR pipeline 的 `--detailing-lora` 权重是**独立于主仓库的 gated
  repo**，需要单独再 accept 一次，见 `ltx_pipeline_gotchas.md`"DFR
  pipeline"一节，不要以为主仓库同意过就自动覆盖。
- `CUBLAS_STATUS_INTERNAL_ERROR`/`illegal memory access` 且发生在视频
  解码阶段——这是已知的 Blackwell 架构显卡上 diffusion VAE 解码器兼容性
  问题（`ltx_pipeline_gotchas.md`"VAE 后端显卡兼容性"一节），不是显存不够
  也不是提示词问题，正确处理是换成卷积版 VAE 重新跑这一轮，不是调整
  prompt/seed。
- `--num-frames`/`--width`/`--height`/`--image` 相关的 CLI 参数报错——
  大概率是 `ltx_remote_config.json`/`video_jobs.json` 本身没走完
  `short-drama-ltx-export` 的校验流程，不是这一轮内容的问题。

这些要报得具体（贴 stderr 原文、贴报错发生在哪个阶段），不能含糊说
"跑不了"，也不属于"对 Reviewer 意见有异议"——是技术故障，跟内容好不好
是两件事，报告给 orchestrator 后交给用户按 `ltx_pipeline_gotchas.md` 处理，
不要自己尝试绕过。

除此之外，正常拿到视频、抽出了帧，就是一次真正的内容重试，计入
`round_count`，不允许"觉得跟上一轮改动不大就跳过不跑"。

## 何时被起、要不要记住上一轮

每个 unit **每一轮都单独起一个新的 Generator agent**，不复用上一轮的
agent 实例。agent 不需要记得"上一轮生成过什么"，orchestrator 已经把这一
轮最终 prompt、首尾帧、seed、目标时长/分辨率（以及局部重绘时的
`defect_window`）都直接写在调用它时的 prompt 里。因为本 skill 严格按镜头顺序执行（见 `loop_protocol.md`），任意时刻
只会有一个 Generator agent在跑，不需要考虑"跟别的 unit 的 Generator抢显卡"
的问题。

## Agent 调用模板

对当前正在处理的 unit（`status: active`），发一次 Agent 调用，
`subagent_type` 用 `general-purpose`（或省略）。prompt 参照：

```
你是本轮 AI 短剧视频生成任务里"<unit.id>"这一个镜头的出片 agent，只处理
这一个镜头，不要碰其它镜头/其它显卡任务。

1. 这是本轮要用的完整参数，已经包含了如果上一轮被 Reviewer 打回的修改
   意见——你不需要评判这些参数是否合理，直接照它提交：
   正向提示词（唯一真正影响生成结果的文本，`negative_prompt` 字段不用管，
   `ltx_ssh_submit.py` 不会把它传给 CLI）：
   """
   <unit.prompt 当前值>
   """
   seed：<unit.seed 当前值>（不要漏填，distilled/dfr pipeline 不传 seed
   时默认固定用 10，不是随机，漏填会导致跟上一轮拿到几乎一样的结果）
   首帧：<unit.first_frame>　尾帧：<unit.last_frame 或"无">
   （`unit.ref_images` 不用管，`ltx_ssh_submit.py` 不会读取/上传这个字段，
   传了也没有效果）
   本轮用测试档参数：时长 <unit.duration_sec_test> 秒，分辨率
   <unit.resolution_test>。（如果 orchestrator 告诉你这一轮是"正式档确认"
   步骤，改用 <unit.duration_sec_final> 秒 / <unit.resolution_final>。）

2. 先 --dry-run 确认命令拼得对，再去掉 --dry-run 真正提交（`seed` 要同步
   写进 `video_jobs.json` 里这条 job 的 `seed` 字段，`ltx_ssh_submit.py`
   才会真的把它传给 `--seed`）：
   python3 .claude/skills/short-drama-ltx-generate/scripts/ltx_ssh_submit.py \
     --config <ltx_remote_config.json 路径> \
     --jobs <video_jobs.json 路径，这一轮如果 prompt/seed 改了先同步写回
       这个文件里对应 <unit.id> 的条目> \
     --out-dir <本集视频输出目录> \
     --only <unit.shot_no>

3. 下载完成后，用
   python3 .claude/skills/short-drama-video-gen/scripts/extract_frames.py \
     <生成的视频文件路径> --out-dir <帧输出目录> --count 5
   抽出均匀分布的 5 帧。

4. 返回：
   video_file: <生成的视频文件绝对路径>
   frames: <抽出的 5 张帧图片绝对路径列表>
   error: <如果命中上面"技术性障碍"清单里的任何一种情况，具体错误原文
     + 报错发生在哪个阶段（上传/远程推理/下载/抽帧）；正常完成留空>

不需要你自己看帧判断好不好，审查是另一个 agent 的工作，你只负责把视频
提交出来、下载下来、抽好帧并报告结果。
```

## 局部重绘模式：orchestrator 指定 `defect_window` 时怎么跑

如果上一轮 Reviewer 给了 `defect_window`（问题只集中在一小段时间窗口，
其余画面正常），orchestrator 会告诉你这一轮要走**局部重绘**而不是整段
重新生成，命令换成：

```
python3 .claude/skills/short-drama-ltx-generate/scripts/ltx_ssh_submit.py \
  --config <ltx_remote_config.json 路径> \
  --jobs <video_jobs.json 路径，prompt/seed 已经按 fix_instruction 同步
    更新过> \
  --out-dir <本集视频输出目录> \
  --only <unit.shot_no> --retake <defect_window.start> <defect_window.end>
```

要求 `--out-dir` 下已经有上一轮生成的 `<unit.id>.mp4`（正常情况下一定有，
因为能判断出"局部问题"就说明上一轮已经产出过完整视频）。产物是
`<unit.id>_retake.mp4`，不会覆盖原文件——返回时把这个路径当 `video_file`
即可，后续验收流程一样先抽帧再看。

`ltx_pipelines.retake` 官方文档记载但本仓库未用 `--help` 实测确认参数名，
如果这一轮报参数错误（不是上面"技术性障碍"清单里的已知条目），这属于
新发现的技术性障碍，正常报错、不计入 `round_count`，同时提醒 orchestrator
这条 pipeline 的参数名可能需要人工核对 `ltx_pipeline_gotchas.md` 更新。

## "落实修改意见"具体意味着什么

- 返回结果里不需要评价"我觉得这个修改意见其实……"，如果确实有技术性
  障碍（比如尾帧文件路径不存在、命中 VAE 解码报错），在 `error` 字段里
  指出，而不是对 prompt/参数的内容提意见。
- 不允许"觉得跟上一轮改动不大就跳过不跑"，orchestrator 每发起一次调用
  都代表这一轮确实要重新提交生成，视频生成不是免费的，每次调用都是真实
  显卡时间成本，但省钱是 orchestrator 通过控制轮次上限来把关的事，不是
  Generator agent 自己判断"要不要真的跑"的事。
