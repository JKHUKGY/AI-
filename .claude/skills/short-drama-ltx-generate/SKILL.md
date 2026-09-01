---
name: short-drama-ltx-generate
description: 面向自建 LTX-2.5（Lightricks LTX-2）的实际生成执行助手：拿到 short-drama-ltx-export 校验好的 video_jobs.json + ltx_remote_config.json 之后，实际去 vast.ai 等平台用用户提供的 API key 租显卡（或复用已有实例）、通过 SSH 部署 LTX-2 环境、下载模型权重、真正调用 ltx_ssh_submit.py 提交生成任务、监控进度、下载结果、抽帧+听审验收，并沉淀了一批实测踩坑的通用注意事项（GPU 租赁稳定性、环境搭建陷阱、pipeline 参数陷阱、角色配音一致性方案）。当用户说"帮我实际生成视频""调用显卡跑""执行生成任务""这一步真的把视频跑出来""租显卡生成"时使用。
---

# LTX-2.5 实际生成执行助手 (short-drama-ltx-generate)

承接 `short-drama-ltx-export` 之后的最后一步：那个 skill 产出的
`video_jobs.json`/`ltx_remote_config.json` 只是"准备好能喂给脚本的文件"，
本 skill 负责真正把显卡租起来、环境装起来、任务跑起来、结果验收下来。

## 0. 先确认前置条件

- `output/<故事名>/videos/ep0X/video_jobs.json` 和 `ltx_remote_config.json`
  已经由 `short-drama-ltx-export` 产出并校验通过（跑过
  `validate_video_jobs.py` 且没有阻塞性错误）。没有就先回那个 skill 补，
  不要凭空拼一份 job 文件上阵。
- 问清楚这次是**新租一台显卡**还是**复用已有的实例**（已有 SSH 信息/
  `ltx_remote_config.json` 里已经填好 `ssh_host`）。

## 1. 租显卡（如果需要新租）

用户提供平台 API key 后（比如 vast.ai），按
`references/gpu_rental_ops.md` 的顺序操作：

1. 设置 API key，先查账户计费状态（`balance`/`credit`/`has_billing`），
   不对劲要先提醒用户，不要闷头往下走。
2. 搜索显卡 offer，显存门槛、磁盘门槛按 `gpu_rental_ops.md` 第 0 条来，
   **不要相信用户口头说的"显存够"，去查实例页面/API 返回的真实型号和
   显存数字**。创建实例时的 `--image` 先问用户有没有之前存过的"预装好"
   镜像（见 `gpu_rental_ops.md` 第 3.5 条 `vastai take snapshot`），有就
   直接用，能跳过下面第 2 步的环境搭建。
3. 创建并启动实例，`--ssh --direct`。轮询 `actual_status` 直到变成
   `running`，不要查一次就下结论（字段之间可能互相矛盾）。
4. 如果反复"排队后又变回停止"，先按 `gpu_rental_ops.md` 的症状识别表
   判断是账户计费问题还是单台宿主机问题，再决定是提醒用户处理账单还是
   直接换个 offer 重建。
5. **实例一确认 `running`，立刻在后台启动闲置看门狗**——这是标准步骤，
   不是等用户提醒才做：
   ```bash
   nohup python3 .claude/skills/short-drama-ltx-generate/scripts/idle_shutdown_watchdog.py \
     --instance-id <实例ID> --ssh-host <ssh_host> --ssh-port <ssh_port> \
     --idle-seconds 120 --check-interval 15 \
     > /tmp/ltx_watchdog_<实例ID>.log 2>&1 &
   ```
   之后每次**重启**已有实例（比如实例意外掉线重连）也要重新跑这一步，
   看门狗进程不会跨实例重启存活。跑完这一集/这一批生成任务、确认不再
   需要这台显卡时，看门狗会在 2 分钟无活动后自动停止实例；如果用户明确
   说还要继续用，不要因为看门狗顺手把实例关了打断用户——看门狗只应该在
   真的没有生成任务在跑时触发，不要把它当成手动的"用完记得停"的替代品
   去跳过第 7 步的收尾提醒。

## 2. 环境搭建

1. SSH 连上后，`git clone --depth 1 https://github.com/Lightricks/LTX-2.git`。
2. 装 `uv`（`curl -LsSf https://astral.sh/uv/install.sh | sh`），
   `uv sync --extra natten`。
3. 问用户要 Hugging Face 的 **Read token**（并确认已在网页上 accept
   LTX-2.5 模型条款），`uv run hf auth login --token <TOKEN>`。
4. 下载模型权重（约 66GiB，官方 README 给的 5 个文件），后台跑、轮询
   完成状态，不要前台傻等。
5. 把这几步的已知坑（PATH 环境变量、非交互式 SSH 不加载 `.bashrc`）应用
   进去，见 `references/gpu_rental_ops.md` 和
   `references/ltx_pipeline_gotchas.md`。

## 3. 核实 pipeline 真实参数

**不要直接相信 README 或任何文档里的参数名**，先跑一遍目标 pipeline 的
`--help`（比如 `python -m ltx_pipelines.distilled --help`），对照
`references/ltx_pipeline_gotchas.md` 里已经记录的已知陷阱（`--image` 的
三段式格式、`--num-frames` 必须 8k+1、`--negative-prompt` 不是所有
pipeline 都有），确认 `ltx_remote_config.json` 里的 `pipeline_module`/
`pipeline_extra_args` 填得对。第一次用一个新 pipeline 或换了新显卡架构，
一定要走这一步，不要图省事跳过。

**`pipeline_extra_args` 里不要加 `--enhance_prompt`**（除非用户明确要单独
测试这个官方"自动增强提示词"功能）——原因见 `ltx_pipeline_gotchas.md`
"官方文档 + 社区实测交叉验证的共识"一节，本仓库的提示词已经是上游手写好
的完整详细提示词，不属于这个功能的适用场景，多篇第三方实测也反馈它不稳定。
同理，distilled pipeline 不需要也没有 CFG/steps 相关参数，看到网上教程让
调 CFG 不要照搬（那是给 dev/full 完整模型用的）。

## 4. 提交生成

1. 先 `--dry-run` 看拼出来的远程命令对不对：
   ```bash
   python3 .claude/skills/short-drama-ltx-generate/scripts/ltx_ssh_submit.py \
     --config output/<故事名>/videos/ep0X/ltx_remote_config.json \
     --jobs output/<故事名>/videos/ep0X/video_jobs.json \
     --out-dir output/<故事名>/videos/ep0X \
     --only <镜号> --dry-run
   ```
2. 去掉 `--dry-run`，先对用户指定的 1-2 个关键镜头跑真实生成，确认没问题
   （不崩溃、能下载到本地）再用不带 `--only` 或多个镜号批量跑剩下的。
   "先小范围测试档（小分辨率+短时长+固定 seed）确认稳定，再放大分辨率/
   时长批量跑正式档"这套流程不是本仓库自己拍脑袋定的，官方文档和多篇
   第三方实测教程都独立给出同样的建议，可以放心照做，不用每次重新纠结
   要不要跳过测试档直接上正式档。
3. 遇到报错（CUDA 错误、参数错误等）先看 `stderr`，对照
   `ltx_pipeline_gotchas.md` 有没有已知条目，没有就记录下来，解决后
   补一条进这份文档，不要每次重新排查同样的坑。

## 5. 验收

0. 生成结果明显不对时，先对照 `ltx_pipeline_gotchas.md`"生成质量丢分的
   三大常见诱因"（分辨率/宽高比传错、CFG 相关参数、提示词堆砌矛盾）快速
   排查一遍，这是官方文档和多篇第三方实测反复提到的最容易翻车的原因，
   往往比直接去查显卡/环境问题更快定位。
1. 每个生成出来的视频，用
   `.claude/skills/short-drama-video-gen/scripts/extract_frames.py` 抽帧，
   Read 工具逐张看：人脸/服装一致性、动作方向、结尾定格姿态，按
   `short-drama-video-gen/references/video_review_checklist.md` 核对。
2. 如果这一镜的提示词里嵌入了台词（见
   `short-drama-video-gen/references/video_prompt_guide.md`"关于台词/
   对白"一节），额外用 `ffmpeg -af volumedetect -f null -` 检查音轨响度
   （区分"只有环境音"还是"生成了明显更响的语音"），但**明确告诉用户
   Claude 没法"听"音频内容，台词准不准、音色自然不自然必须用户自己听
   一遍确认**，不要替用户下"配音没问题"这种结论。
3. 不合格就按 `short-drama-video-gen/references/stability_playbook.md`
   调整提示词/参数，用 `--only` 只重跑这一镜，不要因为批量任务里有一
   两镜有问题就全部推倒重来。

## 6. 角色配音一致性（可选，按需触发）

如果用户要求"多个镜头里同一角色的声音要一致"，参照
`references/ltx_pipeline_gotchas.md` 的"角色配音一致性"一节：
- 已有一段该角色说话效果好的镜头 → 用 `ltx_pipelines.dubit`（DubIt）配上
  新台词，`--reference-video` 指向那段镜头。
- 没有现成素材/想完全掌控音色 → 用 `ltx_pipelines.a2vid_two_stage`，
  `--audio-path` 传用户外部准备好的固定音频。
两条路都没有中文台词的实测验证，第一次用先对 1 个镜头测试。

## 7. 收尾

任务批量跑完后：
1. 汇报本轮生成了几镜、验收结果、还有哪些问题待用户确认（尤其是音频
   内容）。
2. 提醒用户是否要停止实例省钱（见 `gpu_rental_ops.md` 第 4 条），不要
   替用户做这个决定。
3. 如果这次踩到了新的坑（参数陷阱/环境问题/显卡兼容性），补进
   `references/ltx_pipeline_gotchas.md` 或 `references/gpu_rental_ops.md`，
   给下一集/下一次会话省事。

## 与其他 skill 的衔接

- 上游：`short-drama-ltx-export`（`video_jobs.json` + 校验通过的
  `ltx_remote_config.json`）。
- 平行：`short-drama-video-gen` 负责提示词本身的撰写方法论
  （`video_prompt_guide.md`）和验收工具（`extract_frames.py`），本 skill
  只负责"真正跑起来"这一段，不重复定义提示词写法。
- 下游：生成结果的文件路径要回填进 `short-drama-video-gen` 产出的
  `video_jobs.md`（人读版清单），方便剪辑阶段按镜号找素材。
