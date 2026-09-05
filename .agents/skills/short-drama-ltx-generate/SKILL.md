---
name: short-drama-ltx-generate
description: 面向自建 LTX-2.5（Lightricks LTX-2）的实际生成执行助手：拿到 short-drama-ltx-export 校验好的
  video_jobs.json + ltx_remote_config.json 之后，**真的去 RunPod 用用户的 API key 租显卡**（渠道只剩
  RunPod——AutoDL 和 vast.ai 2026-09-04 已删除，那两家销毁实例会连模型权重一起删；RunPod 的 Network Volume
  跟 Pod 生命周期解耦，卷还能在线扩容）、通过 SSH 部署 LTX-2 环境、下载模型权重、调用 ltx_ssh_submit.py 提交生成、监控进度、下载结果、抽帧验收。租卡默认用
  runpod_ops.py rent_cheapest 按"够用就行最便宜优先"挑卡并自动重试缺货。沉淀了一批实测踩坑注意事项：GPU 缺货要轮询重试、ssh
  保活、setsid 隔离进程组、python3 -u 不缓冲日志、按远端目录判进度、冷启动 14-23 分钟别误判成卡死。**内置"用完就关"的显卡收尾机制**：gpu_teardown.py
  一条命令 terminate Pod 并轮询确认真的停止计费（Network Volume 上的权重不受影响），ltx_ssh_submit.py --auto-stop
  让批量任务跑完/报错/被中断都自动关机，闲置看门狗作为"人忘了关"的兜底。**本 skill 目录下的 runpod_ops.py / gpu_teardown.py
  / idle_shutdown_watchdog.py 和 references/runpod_gpu_ops.md 是两条视频通道共用的 GPU 运维资产**，minimax-h3-generate
  直接引用它们、不复制。当用户说"帮我实际生成视频""调用显卡跑""执行生成任务""租显卡生成""RunPod 能不能用""不想每次重新下载模型""用完把显卡关掉""生成完自动关机""怎么确认显卡真的停了"时使用。**这一批要用
  MiniMax-H3 就去 minimax-h3-generate**——那条通道是 SGLang 常驻服务、走 HTTP，部署方式和显存门槛都完全不同。
---

## Codex 运行适配（迁移新增，以下原始正文保持不变）

- 在本项目根目录运行；此 skill 的 Codex 入口为 `.agents/skills/short-drama-ltx-generate/SKILL.md`，用 `$short-drama-ltx-generate` 调用。
- 原文中的 Read：文本用文件读取工具，图片用图片查看工具；Bash 用 shell，Write/Edit 用文件编辑工具，Glob/Grep 用文件搜索工具；WebFetch/WebSearch 用可用的网页检索工具。
- 原文提到其他 skill 时，读取同级 `../<skill-name>/SKILL.md`。Task/subagent/Generator/Reviewer 对应 Codex 的独立子代理能力；保留原来的职责隔离、轮次和预算，实际并发受宿主上限限制。能力缺失时报告限制，不声称已经执行。
- 原文相对于 skill 的 references/、scripts/ 路径仍相对于本目录。原文命令里的 `.claude/skills/` 脚本及文档路径在 Codex 执行时映射到 `.agents/skills/`；项目素材、输出和私有配置文件的路径保持原意。脚本内部实现及默认配置保持原样，源目录与目标目录共存。
- 原文的确认节点、输入要求和业务规则保持不变。本文只适配执行宿主，不自动执行生成、租卡或 API 调用。

<!-- ORIGINAL-BODY-START -->

# LTX-2.5 实际生成执行助手 (short-drama-ltx-generate)

承接 `short-drama-ltx-export` 之后的最后一步：那个 skill 产出的
`video_jobs.json`/`ltx_remote_config.json` 只是"准备好能喂给脚本的文件"，
本 skill 负责真正把显卡租起来、环境装起来、任务跑起来、结果验收下来。

## 0. 先确认前置条件

- **确认这一批是 LTX-2.5**：读 `ltx_remote_config.json` 的 `model` 字段，
  应该是 `"ltx-2.5"`。是 `"minimax-h3"` 或者同目录有 `h3_remote_config.json`
  就**转去 `minimax-h3-generate`**——那条通道是 SGLang 常驻服务、走 HTTP，
  部署方式、显存门槛、验收方式（H3 要听声音）都完全不同。

- `video_jobs.json` 和 `ltx_remote_config.json` 已经由 `short-drama-ltx-export`
  产出并校验通过。没有就先回那个 skill 补，不要凭空拼一份 job 文件上阵。
- 问清楚这次是**新租一台显卡**还是**复用已有的实例**（已有 SSH 信息/
  `ltx_remote_config.json` 里已经填好 `ssh_host`）。

## 1. 租显卡（如果需要新租）

**渠道只有 RunPod 一个**（2026-09-04 起）。AutoDL 和 vast.ai 两条通道已经
删掉——那两家没有"存储和算力分开生命周期"的东西，销毁实例会连 67GB 权重
一起删，每次重租都要重下，实际用下来不划算。相关脚本和文档已经从本 skill
移除，别再去找 `autodl_ops.py` / `gpu_rental_ops.md`。

**先按模型确定显存门槛，然后租能满足门槛的最便宜的卡。**

以前默认奔着 80GB 大卡去，那是浪费——两个模型都有官方的低显存配方：

| 跑什么 | 显存门槛 | 依据 | 参考卡/价 |
|---|---|---|---|
| **LTX-2.5**（<217 帧） | **80GB（实测）** | 本仓库跑通整集的配置 | A100 80GB $1.19–1.59 |
| LTX-2.5 更低显存 + `--offload cpu` | ？ | ledger B7 只说 ≥217 帧要 offload，**低显存档没实测过** | 想省钱先拿一镜试，试完回填这一行 |

> 顺带一提：**MiniMax-H3 那条通道反而更便宜**——SGLang 有 1×RTX 4090 24GB
> 的实测配方（$0.34/hr）。需要省钱又能接受换模型时值得考虑，见
> `minimax-h3-generate`。

### 怎么租：一条命令挑最便宜的

```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/runpod_ops.py rent_cheapest \
  --min-memory-gb 24 \
  --network-volume-id <你的卷 id> \
  --image runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04 \
  --public-key "$(cat ~/.ssh/id_ed25519.pub)" \
  --dry-run          # 先看候选列表，确认了再去掉这个参数
```

它做三件事：拉全部型号 → 滤掉显存不够的 → **从最便宜的开始挨个试着建**，
建成即返回。`--max-price` 卡价格上限，`--rounds`/`--retry-interval` 控制重试。

**为什么要"挨个试"而不是只试最便宜那个**：`gputypes` 返回的 `stockStatus` 是
**全局聚合值**，跟具体数据中心对不上（Network Volume 在哪，Pod 就必须在哪）。
实测见过 `Medium` 的型号建不出来、`Low` 的反而成了；也见过一个数据中心四种
80GB+ 型号同时缺货、轮询 9 轮才抢到。脚本已经把这套重试逻辑包进去了，
**不要试一次失败就报告"租不到"**。

不是缺货的错误（参数错、额度不足、权限问题）脚本会直接退出，不会拿着同一个
坏参数把每个型号都糟蹋一遍。

### RunPod 渠道

按 `references/runpod_gpu_ops.md` 的顺序操作，用
`scripts/runpod_ops.py`（`gputypes`/`volume_create`/`volume_list`/
`volume_delete`/`create`/`status`/`snapshot`/`stop`/`start`/`terminate`
子命令，封装了 RunPod REST API v1 + GraphQL，RunPod 没有官方 CLI）。
**这个渠道的核心价值：存储（Network Volume）和算力（Pod）是分开生命周期的
两个资源**——Pod 可以随便 terminate，卷上的 67GB 权重不受影响，下次挂同一个
卷建新 Pod 直接能用：

1. Token 放进 `runpod_config.json`（`.gitignore` 已排除，不进仓库）。
2. `datacenters` 查数据中心 ID，`gputypes --min-memory-gb 80` 查显存达标的
   型号和价格（不需要先建实例），拿准确的 `id` 字符串给下一步用——**优先选
   `stockStatus: "High"` 的型号**，`Low`/`Medium` 大概率在具体数据中心创建
   时报 `"There are no instances currently available"`（实测确认过，换个
   `stockStatus` 更高的型号重试就行，不是账号或参数问题）。
3. **只在第一次用这个 Network Volume 时**跑 `volume_create` 建一个（建议
   ≥100GB），记下返回的 volume id 长期复用——**不要每次都新建一个**，
   那样又变回每次重新下载了，建 Volume 前先 `volume_list` 确认有没有已经
   建过的可以直接用。
4. `create` 时用 `--network-volume-id` 挂上这个 Volume，`--public-key`
   传用户的 SSH 公钥内容（不是密码）；第一次下载模型权重的位置要放在
   Volume 挂载路径下（默认 `/workspace`），不要下到容器盘里，否则 Pod
   一删就白下载了。
5. `snapshot --pod-id <id>` 拿 SSH 信息和价格；`desiredStatus` 创建时就是
   `RUNNING`，但 `public_ip`/`ssh_port` 要再等 30-40 秒左右才会填上（实测
   轮询 3-4 次、每次间隔 10 秒），前几次是 null 属于正常现象，继续轮询，不要
   查一次就下结论。
6. 2026-09-02 已经用真实账号完整跑通一次（建 Volume → 建 Pod → SSH/SCP →
   `terminate` Pod → 用同一个 Volume 重建 Pod → 确认数据完好），
   `runpod_gpu_ops.md` 已经按实测结果更新，第 7 条列的是**这一次没碰到、
   留给下次验证**的点（比如 Community Cloud 公网 IP 稳定性）。遇到没写过的
   报错记得回去补一条。

7. **缺货是常态，要写重试循环**。2026-09-04 实测：同一个数据中心
   （Network Volume 在哪 Pod 就得在哪）四种 80GB+ 型号可以**同时全部缺货**，
   轮询 9 轮（每轮 4 个型号、间隔 30 秒）才抢到。而且 `gputypes` 返回的
   `stockStatus` 是全局聚合值，跟具体数据中心对不上——那次 `Medium` 的
   A100-SXM 创建失败、`Low` 的 A100 PCIe 反而成了。**按型号列表轮着试 +
   隔几十秒重试**，不要试一个失败就报告"租不到"。

### 别让显卡空转烧钱：两道防线

租显卡这一步最容易亏钱的地方不是"选贵了"，而是**跑完之后忘了关**。所以
下面两件事是两道独立的防线，**都要做，不是二选一**：

| 防线 | 脚本 | 什么时候动 | 定位 |
|------|------|-----------|------|
| 主动收工 | `scripts/gpu_teardown.py`（或 `ltx_ssh_submit.py --auto-stop`） | 这一批任务跑完就立刻关 | 正常流程，见下面「用完就关」 |
| 被动兜底 | `scripts/idle_shutdown_watchdog.py` | 连续 N 秒检测不到活动才关 | 只兜"人忘了/会话断了"，别当主流程用 |

**实例一确认 `running`，立刻在后台启动闲置看门狗**——这是标准步骤，
不是等用户提醒才做：
```bash
# RunPod（多传 --platform runpod --runpod-config；权重在 Network Volume 上时
# 建议 --stop-mode terminate，见下面「用完就关」里 RunPod 的计费差别）
nohup python3 .claude/skills/short-drama-ltx-generate/scripts/idle_shutdown_watchdog.py \
  --instance-id <pod_id> --ssh-host <ssh_host> --ssh-port <ssh_port> \
  --platform runpod --runpod-config .claude/skills/short-drama-ltx-generate/runpod_config.json \
  --stop-mode terminate \
  --idle-seconds 120 --check-interval 15 \
  > /tmp/ltx_watchdog_<pod_id>.log 2>&1 &
```
之后每次**重启**已有实例（比如实例意外掉线重连）也要重新跑这一步，
看门狗进程不会跨实例重启存活。看门狗的停机动作现在统一委托给
`gpu_teardown.py`（会轮询确认真的停了，确认不了就报警），所以
`--stop-mode` 的取值含义跟下面「用完就关」一节完全一致。

看门狗只是兜底：**别用"等看门狗超时"代替主动关机**——那 2 分钟等待期
一样在计费，而且看门狗只在当前会话/后台任务存活期间有效，会话一关它就
没了。反过来，如果用户明确说还要继续用这台机器，不要因为看门狗顺手把
实例关了打断用户（纯本地抽帧验收那段时间对看门狗来说就是闲置，把
`--idle-seconds` 调大到 3600 或那段时间先不挂看门狗）。

### 用完就关（`gpu_teardown.py`）

**确认这一批不再需要显卡，就立刻跑这一步，不要留给用户"记得去关"**：
```bash
# 平台/实例ID 直接从 ltx_remote_config.json 的 platform/instance_id 字段读
python3 .claude/skills/short-drama-ltx-generate/scripts/gpu_teardown.py \
  --config output/<故事名>/videos/ep0X/ltx_remote_config.json
```
它做三件事：挑对这个平台该用的停机动作 → 调接口 → **轮询确认状态真的变了**
（确认不了就非 0 退出 + 大字警告，让人去控制台补一刀，而不是打印一句
"已停止"让用户以为安全了），顺带把本机盯着这台实例的看门狗进程收掉。

也可以让提交脚本跑完自动关，连这一条命令都不用记：
```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/ltx_ssh_submit.py \
  --config ... --jobs ... --out-dir ... --auto-stop
```
`--auto-stop` 走 `finally`，**中途报错、Ctrl-C 中断也会关机**（"任务崩了
没人管、实例挂着通宵计费"是最贵的一种失败方式）；它要求 config 里有
`platform` 和 `instance_id` 字段，缺了会在**提交任务之前**就报错退出，
不会等几小时跑完才发现关不掉。

`--mode auto`（默认）在各平台上的选择，理由都是"钱和数据哪个更亏"：
- **RunPod → `terminate`**。`stop` 只停 GPU 计费，Pod 的磁盘按官方计费
  口径仍在收费，而容器盘本来就不跨 `stop`/`start` 持久（实测 `uv` 会没
  了），留着没好处；而 `terminate` **实测确认完全不影响 Network Volume**
  上的 67GB 权重，下次挂同一个 `network_volume_id` 建新 Pod 权重还在。
  例外：config 里没有 `network_volume_id`（权重可能在容器盘上）时会自动
  降级成 `stop` 并警告，不会替用户删掉 67GB 权重。
- **RunPod → `terminate`**（有 Network Volume 时）。销毁动作
  会连盘上的模型权重一起删，所以"用完就关"在这两家只能是停机。
- 销毁类动作（RunPod
  `volume_delete`）**不在这个脚本里**，是故意的：那要用户明确说"这台/这个
  卷不要了"才做，见第 7 步。

## 2. 环境搭建

> 两条视频通道的环境可以共存在同一个 Network Volume 上（LTX 约 67GB +
> H3 的 Ref2VA 约 144GB）。**卷不够就扩**——`runpod_ops.py` 没有扩容子命令，
> 直接调 REST：`PATCH /v1/networkvolumes/{id}` body `{"size": 300}`，
> **实测 Pod 在跑也能扩，只增不减**。

1. SSH 连上后，`git clone --depth 1 https://github.com/Lightricks/LTX-2.git`。
2. 装 `uv`（`curl -LsSf https://astral.sh/uv/install.sh | sh`），
   `uv sync --extra natten`。
3. 问用户要 Hugging Face 的 **Read token**（并确认已在网页上 accept
   LTX-2.5 模型条款），`uv run hf auth login --token <TOKEN>`。
4. 下载模型权重（约 66GiB，官方 README 给的 5 个文件），后台跑、轮询
   完成状态，不要前台傻等。
5. 把这几步的已知坑（PATH 环境变量、非交互式 SSH 不加载 `.bashrc`）应用
   进去，见 `references/runpod_gpu_ops.md` 和
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
4. **如果这一批跑完就确定不再需要这台显卡了**（比如整集镜头一次性批量
   提交、跑完只剩本地验收），直接给正式那一跑加 `--auto-stop`，让它跑完
   自己关，省掉"等验收完再想起来关机"的那段空转计费。如果跑完还要接着
   补跑镜头/做双 agent 循环，就别加，改成收尾时手动跑 `gpu_teardown.py`。
   `--auto-stop` 是在 `finally` 里调 `gpu_teardown.py`——**包括报错和被中断
   的情况**。

### 批量跑长任务时的六条硬教训（2026-09-04 实测踩过）

《出狱后》v2 ep01 一次性提交 35 条时全踩了一遍，代价是 GPU 空转 21 分钟。
批量跑之前先把这六条摆好，不然会重复付同样的学费。

**① ssh 会话会在远端命令跑完之后不返回，脚本就无限干等**

实际发生的：`ep01_镜01.mp4` 远端 02:00 就生成好了，但 `ssh` 客户端没有退出，
`ltx_ssh_submit.py` 阻塞在这条已经死掉的通道上，到 02:21 还在等——期间
`nvidia-smi` 显示 GPU 0% / 0 MiB，远端没有任何 python 进程，**但计费一直在走**。

修法：给本机 `~/.ssh/config` 加保活，通道断了让 ssh 自己报错退出，
脚本就会把这一镜记成 error 然后继续下一镜，而不是永久卡住：

```
Host *
  ServerAliveInterval 30
  ServerAliveCountMax 4
  TCPKeepAlive yes
```

**② 要保住 Pod 续跑，只能 `kill -9`——普通 kill / Ctrl-C 会把显卡关掉**

`ltx_ssh_submit.py` 的 `--auto-stop` 写在 `finally` 里，**这是故意的**
（"任务崩了没人管、实例挂着通宵计费"比任何一次生成失败都贵）。所以：

- 想停下来**并且关机** → 普通 `kill` / `Ctrl-C`，让 `finally` 跑完
- 想停下来**但保住机器接着跑** → `kill -9`，绕过 `finally`

卡死要救场时是后者。救完记得自己在收尾时手动 `gpu_teardown.py`，
因为这一跑的 `--auto-stop` 已经被你跳过了。

**③ `nohup ... > log` 的日志会是 0 字节，必须加 `python3 -u`**

Python 的 stdout 在重定向到文件时是块缓冲的，一条 4KB 以内的进度日志能在
缓冲区里躺几十分钟。表现就是"任务在跑但日志一个字都没有"，完全没法判断
是正常还是卡死。批量跑一律 `python3 -u`。

**④ 判断进度别只看本地文件，要看远端 `/workspace/ltx_jobs/`**

本地文件是"生成完 + scp 下载完"才出现的，中间任何一环卡住本地就一直是 0。
远端产物目录才是真实进度：

```bash
ssh ... "ls -la --time-style=+%H:%M /workspace/ltx_jobs/*.mp4; \
         nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader"
```

**GPU 0% + 0 MiB + 远端没有 ltx 进程 + 本地长时间不动 = 卡死，不是在算**
（注意区分：装权重阶段 GPU 也是 0%，但那时候远端**有** python 进程、
`load average` 很高、显存会逐步涨上去）。

顺带一条好消息：`/workspace` 是 Network Volume，**产物跨 Pod 保留**。
卡死后已经生成好的片子可以直接 `scp` 拉回来，用 `--only` 跳过它续跑，
不用整批重来。

**⑤ 后台批次必须 `setsid` 隔离进程组，否则你自己的监控命令会把它打断**

2026-09-04 实测：批次用 `nohup ... &` 起在后台，然后在**同一个 shell 会话**里
跑轮询监控。监控命令超时被杀时，**SIGINT 打到了整个进程组**，`nohup` 只挡
SIGHUP、不挡 SIGINT，于是批次收到 KeyboardInterrupt → 走 `finally` →
`--auto-stop` 把显卡关了。表现是"跑得好好的，突然 ssh connection refused，
Pod 没了"，日志尾部能看到 `KeyboardInterrupt` 的 traceback。
那一次断在 29/35，最后 6 镜要另起一台机器补。

正确起法（自己开进程组，跟当前会话彻底脱钩）：

```bash
setsid nohup python3 -u .../ltx_ssh_submit.py ... > batch.log 2>&1 < /dev/null &
```

**判断标准**：看到 `Connection refused` + `snapshot` 返回 `desired_status: null`
就是 Pod 已经没了，先去 `batch.log` 尾部找 `KeyboardInterrupt`——是的话就是
这条，不是远端故障。已经生成的部分照样在 Network Volume 上，
`--only` 补跑缺的那几镜即可（用 `video_jobs.json` 对本地 `*.mp4` 取差集）。

**⑥ 冷启动那一条特别慢，别误判成卡死**

权重 67GB 从 Network Volume 第一次读进来实测要 **14-23 分钟**（换了台新 Pod
就得重来一次）。之后靠系统页缓存，同一台机器上后续每镜约 3 分钟。
所以"第一条特别久、后面突然快起来"是正常的。

---

## 5. 验收

0. 生成结果明显不对时，先对照 `ltx_pipeline_gotchas.md`"生成质量丢分的
   四大常见诱因"（分辨率/宽高比传错、CFG 相关参数、提示词堆砌矛盾、画面
   看起来"没在动"只有镜头本身在推拉摇移）快速排查一遍，这是官方文档和
   多篇第三方实测反复提到、外加本仓库 ep01 镜1 实测确认过的最容易翻车的
   原因，往往比直接去查显卡/环境问题更快定位。
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
1. **先关显卡，再写汇报**。验收（抽帧、Read 看图、写总结）都是本地工作，
   不需要显卡在线，让实例挂着等你写完汇报就是纯烧钱。所以确认这一批
   生成任务已经跑完、结果都下载到本地了，第一件事是跑
   `gpu_teardown.py --config .../ltx_remote_config.json`（或者一开始就用
   `--auto-stop` 让它自己关掉了），确认输出里有 `✅ 已确认停止计费`
   再继续。**这一步不需要问用户"要不要关"**——用完就关是默认行为，
   下次要用重新起一台（RunPod 挂同一个 Network Volume 不用重新下权重）。
   只有两种情况不关：用户明确说了接下来还要继续跑，或者还有镜头等着补跑。
2. 汇报本轮生成了几镜、验收结果、还有哪些问题待用户确认（尤其是音频
   内容），并在汇报里写清楚**显卡已经关了/为什么还开着**、这一轮大概花了
   多少钱（实例单价 × 开机时长）。
3. **销毁类动作要用户明确点头才做**：RunPod
   `release`、RunPod `volume_delete` 会把盘上的模型权重一起删掉（下次要
   重新下 67GB），跟"关机省钱"是两件事，不要顺手做。判断依据见
   `runpod_gpu_ops.md` 第 6 条。
4. 如果这次踩到了新的坑（参数陷阱/环境问题/显卡兼容性/新的价格参考点），
   补进 `references/ltx_pipeline_gotchas.md`、`references/runpod_gpu_ops.md`、
   `references/runpod_gpu_ops.md`，给
   下一集/下一次会话省事——RunPod 那份文档目前标了不少 ⚠️ 未实测点，第一次
   真实用完之后尤其应该回去把能确认的条目改成实测结论。

## 与其他 skill 的衔接

- 上游：`short-drama-ltx-export`（`video_jobs.json` + 校验通过的
  `ltx_remote_config.json`）。
- 平行：`short-drama-video-gen` 负责提示词本身的撰写方法论
  （`video_prompt_guide.md`）和验收工具（`extract_frames.py`），本 skill
  只负责"真正跑起来"这一段，不重复定义提示词写法。
- 下游：生成结果的文件路径要回填进 `short-drama-video-gen` 产出的
  `video_jobs.md`（人读版清单），方便剪辑阶段按镜号找素材。
- 如果想要"出片 agent + 审查 agent 互相制衡"、审查时不拿分镜表字面描述
  当标准而是对照原剧本情节判断、并且单镜最多三轮自动打回重做的更严格
  执行方式，本 skill 第 1-3 步（租显卡/环境/核实参数）做完之后，可以改用
  `loop-video-generation` 替代第 4-5 步（提交生成+验收）。
