---
name: minimax-h3-generate
description: 面向 MiniMax-H3（Lightricks LTX 之外的另一条自建图生视频通道）的实际生成执行助手：拿到 minimax-h3-export
  校验好的 h3_jobs.json + h3_remote_config.json 之后，**真的去 RunPod 租显卡**（渠道只有 RunPod）、SSH
  部署 SGLang Diffusion、下载 Ref2VA 权重、起常驻推理服务、通过 SSH 隧道用 h3_submit.py 走 HTTP 提交生成、监控、下载结果、抽帧+**听审**验收（H3
  原生出 32kHz 立体声，验收要听不只是看）、用完关机。**跟 LTX 通道最大的结构性差别**：H3 是常驻服务、权重只装一次，第 2 条往后没有装载开销，批量跑整集明显更省；而且显存门槛低得多——SGLang
  cookbook 有实测验证的 1×RTX 4090 24GB 单卡配方（BF16 峰值约 18GB，量化是可选项不是刚需）和 2×RTX 5090 无损配方，README
  里那条 --num-gpus 4 是追求速度的拓扑不是门槛。租卡默认用 runpod_ops.py rent_cheapest 按"够用就行最便宜优先"挑卡。显卡收尾复用
  short-drama-ltx-generate/scripts 里的 gpu_teardown.py，h3_submit.py --auto-stop 让批量任务跑完/报错/被中断都自动关机。当用户说"用
  MiniMax H3 生成""H3 怎么部署""起 SGLang 服务""H3 跑这一集""H3 要几张卡""H3 能不能用便宜显卡"时使用。跑 LTX-2.5
  用 short-drama-ltx-generate，不要用这个。
---

## Codex 运行适配（迁移新增，以下原始正文保持不变）

- 在本项目根目录运行；此 skill 的 Codex 入口为 `.agents/skills/minimax-h3-generate/SKILL.md`，用 `$minimax-h3-generate` 调用。
- 原文中的 Read：文本用文件读取工具，图片用图片查看工具；Bash 用 shell，Write/Edit 用文件编辑工具，Glob/Grep 用文件搜索工具；WebFetch/WebSearch 用可用的网页检索工具。
- 原文提到其他 skill 时，读取同级 `../<skill-name>/SKILL.md`。Task/subagent/Generator/Reviewer 对应 Codex 的独立子代理能力；保留原来的职责隔离、轮次和预算，实际并发受宿主上限限制。能力缺失时报告限制，不声称已经执行。
- 原文相对于 skill 的 references/、scripts/ 路径仍相对于本目录。原文命令里的 `.claude/skills/` 脚本及文档路径在 Codex 执行时映射到 `.agents/skills/`；项目素材、输出和私有配置文件的路径保持原意。脚本内部实现及默认配置保持原样，源目录与目标目录共存。
- 原文的确认节点、输入要求和业务规则保持不变。本文只适配执行宿主，不自动执行生成、租卡或 API 调用。

<!-- ORIGINAL-BODY-START -->

# MiniMax-H3 生成执行助手 (minimax-h3-generate)

> ⚠️ **本仓库一次都没有真的跑过 H3。** 下面每一条都来自官方文档
> （`MiniMaxAI/MiniMax-H3` README/docs、**SGLang Diffusion cookbook**、
> vLLM recipes、diffusers pipeline 文档），**不是实测结论**。
> 第一次实跑时遇到跟文档不符的，回来改掉这份文档。
> 完整的规格/配方/待验证清单见 `references/minimax_h3_ops.md`。

## 0′. 先确认走哪条通道

同一份 `h3_jobs.json` 有三条出片路径，**别默认就是租卡**：

| 通道 | 怎么跑 | 什么时候选它 |
|---|---|---|
| 自建 SGLang | 租卡 → 起常驻服务 → `scripts/h3_submit.py` | 要 **seed 可复现**、要整集批量摊薄租卡成本 |
| **官方云 API** | `scripts/h3_cloud_submit.py`，不租卡 | 只跑几条、要 **2K**、不想碰运维。规格和落差见 `references/minimax_cloud_api.md` |
| MiniMax Design | 官方客户端手动点（design.minimax.io） | 单镜试水、要人在环里反复调 |

云 API 和 Design 都**不暴露 seed**，卡里的 seed 在那两条路上作废；
自建那条锁 768 短边是开源权重的限制，云端能开 2K。

## 0. 先确认前置条件

- `output/<故事名>/videos/ep0X/h3_jobs.json` 和 `h3_remote_config.json` 已经由
  `minimax-h3-export` 产出并校验通过。没有就先回那个 skill，不要凭空拼 job 文件。
- 问清楚这次是**新租一台显卡**还是**复用已有实例**（config 里已经填好
  `ssh_host` 且服务还活着）。

## 1. 租显卡

**渠道只有 RunPod。** 复用 `short-drama-ltx-generate/scripts/runpod_ops.py`
和 `references/runpod_gpu_ops.md`——那套 GPU 运维脚本是两条通道共用的，
故意不复制一份到这里，避免两边漂移。（脚本住在 `ltx-generate` 目录下是历史
原因，不代表它只服务 LTX。）

### 显存门槛：比 LTX 低得多

| 配置 | 显存 | 依据 | RunPod 价 |
|---|---|---|---|
| **1× RTX 4090** | **24GB** | SGLang cookbook 的 `1×RTX 4090 24GB` 配方，**BF16 峰值约 18GB** | **$0.34/hr** |
| 1× RTX 5090 | 32GB | 同族，更宽裕 | $0.69/hr |
| 2× RTX 5090 | 2×32GB | 官方标的"最快的 32GB 无损工作点" | $1.38/hr |
| 4×H100 / 4×H200 | 4×80GB | README 那条命令——**追求速度的拓扑，不是门槛** | 约 $6/hr |

⚠️ **别从 README 的 `--num-gpus 4` 外推门槛**。2026-09-04 在这上面连错两次
（先说"要 4 卡"、再说"便宜卡必须换 diffusers"），两次都是没去看 SGLang 自己的
cookbook。过程记录见 `references/minimax_h3_ops.md` 第 3 节开头。

⚠️ **宿主内存是隐藏门槛，而且没实测过。** 流式 offload 要把权重放宿主内存，
官方 2×5090 配方点名要 **384GiB 级**。租便宜卡时**先确认 Pod 的 RAM**，
别只看显存——便宜卡的 Pod 通常配的内存小得多。

```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/runpod_ops.py rent_cheapest \
  --min-memory-gb 24 --network-volume-id <卷 id> \
  --image runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04 \
  --public-key "$(cat ~/.ssh/id_ed25519.pub)" --dry-run
```

缺货是常态，脚本内置了"按价格从低到高挨个试 + 整轮重试"，**不要试一次失败
就报告租不到**。

## 2. 部署环境

### 2.1 下权重（只需要一次，之后靠 Network Volume 复用）

**本仓库只用 `ref2va`**（既定选择，见 `references/minimax_h3_ops.md` 第 0 节），
所以只下 Ref2VA，**不需要 FL2VA 那 144GB**：

```bash
hf download MiniMaxAI/MiniMax-H3 --include "Ref2VA/**" "model_index.json" \
  --local-dir /workspace/MiniMax-H3 --max-workers 4
```

⚠️ **通配符必须是 `Ref2VA/**`**。写 `Ref2VA/*` 会静默只下顶层几个小文件——
实测下完 9.9MB，`hf` 还打印 `✓ Downloaded`，很容易以为成功了。

验完整性别只看 `du`：

```bash
find /workspace/MiniMax-H3 -name '*.incomplete' | wc -l   # 必须是 0
```

`du -sh` 报 GiB、HF 页面标十进制 GB：**144.1GB ≈ 135GiB**，看到 135G 是对的。

实测约 **7GB/分钟**，144GB 约 25 分钟。**会抢 Network Volume 的 I/O**——
跟正在跑的生成任务并行会把生成拖慢 2–3 倍，能错开就错开。

### 2.2 装 SGLang 并起服务

```bash
uv pip install "sglang[diffusion]" --prerelease=allow
```

**1× RTX 4090 24GB**（最便宜，先用无损 BF16，别急着量化）：

```bash
setsid nohup sglang serve --model-path /workspace/MiniMax-H3 \
  --model-variant ref2va \
  --attention-backend fa --performance-mode memory \
  --layerwise-offload-components dit,text_encoder \
  --dit-offload-prefetch-size 1 --dit-layerwise-resident-layers 0 \
  --enable-torch-compile false --port 30011 \
  > /workspace/sglang.log 2>&1 < /dev/null &
```

两条官方要点：

- **量化是可选的**。官方原话：drop `--quantization` for the BF16 baseline，
  "GPU peak stays about **18 GB either way**"。默认别量化。
  真要省再加 `--quantization kitchen_int8`（先 `pip install comfy-kitchen`）。
- **`vae` 千万别放进 `--layerwise-offload-components`**——官方明说那会在
  167 个解码 tile 上各重新流约 9GiB。

**2× RTX 5090**（官方标的最快 32GB 无损点，要 384GiB 级宿主内存）：

```bash
setsid nohup sglang serve --model-path /workspace/MiniMax-H3 \
  --model-variant ref2va \
  --num-gpus 2 --tp-size 2 --ulysses-degree 1 --encoder-parallel auto \
  --performance-mode memory \
  --layerwise-offload-components dit,text_encoder,vae \
  --dit-offload-prefetch-size 1 --dit-layerwise-resident-layers 20 \
  --enable-torch-compile false --port 30011 \
  > /workspace/sglang.log 2>&1 < /dev/null &
```

**不要开 `--enable-torch-compile`**：官方说当前 compile 路径会改变模型的数值
输出，所以没有任何一个推荐的无损预设隐式打开它。

⚠️ **必须 `setsid nohup`**，理由见第 4 节。装载要几十分钟，端口没通不代表
失败，轮询确认，别看一眼就判死。

### 2.3 连端口：SSH 隧道

Pod 的 30011 不一定对公网开放，最稳的是隧道：

```bash
ssh -N -L 30011:127.0.0.1:30011 -p <ssh_port> root@<ip> &
```

然后 `h3_submit.py --endpoint http://127.0.0.1:30011`。

## 3. 提交生成

```bash
# 先 dry-run 看请求体
python3 .claude/skills/minimax-h3-generate/scripts/h3_submit.py \
  --jobs output/<故事名>/videos/ep0X/h3_jobs.json \
  --out-dir output/<故事名>/videos/ep0X \
  --endpoint http://127.0.0.1:30011 --only <镜id> --dry-run

# 真跑：先 1-2 镜确认，再批量
setsid nohup python3 -u .claude/skills/minimax-h3-generate/scripts/h3_submit.py \
  --jobs ... --out-dir ... --endpoint http://127.0.0.1:30011 \
  --config output/<故事名>/videos/ep0X/h3_remote_config.json --auto-stop \
  > batch.log 2>&1 < /dev/null &
```

**H3 相对 LTX 的结构性优势**：LTX 每镜都要重装 67GB 权重（页缓存能救回一部分，
但换台机器第一条仍要 14–23 分钟）；H3 是常驻服务，**权重只装一次**，
第 2 条往后没有装载开销。批量跑整集这个差别很大。

**第一次真跑要做的一件事**：`h3_submit.py` 里的状态字符串
（`DONE_STATES` / `FAIL_STATES`）是照通用约定写的兜底集合，**没对着真实服务
确认过**。跑通第一条后把服务端实际返回的 `status` 值补进脚本。

## 4. 批量跑长任务的硬教训

这些坑是在 LTX 通道上踩出来的，但**除了第 ⑥ 条以外全都同样适用于 H3**。
完整版见 `short-drama-ltx-generate/SKILL.md` 第 4 节，这里只列要点：

1. **`setsid nohup` 隔离进程组**——否则你自己的监控命令超时被杀时，SIGINT
   会打到同进程组，把批次一起干掉，`--auto-stop` 的 `finally` 还会顺手把显卡
   关了。实测断在 29/35。
2. **想保住 Pod 续跑只能 `kill -9`**——普通 kill / Ctrl-C 会走 `finally`
   触发 `--auto-stop` 关机。这是**故意设计**（忘关机比任何一次生成失败都贵）。
3. **`python3 -u`**——不然 `nohup > log` 的日志是块缓冲，长时间 0 字节，
   完全没法判断是在跑还是卡死。
4. **ssh 保活**——`~/.ssh/config` 加 `ServerAliveInterval 30`，否则远端跑完了
   ssh 通道不返回，脚本能干等几十分钟、GPU 空转烧钱。
5. **进度看远端目录，不是本地文件**。本地文件是"生成完 + 下载完"才出现的。
6. **冷启动慢**——这一条 H3 跟 LTX**不一样**：LTX 是每镜都可能慢，
   H3 只有起服务那一次慢，之后每条都快。看到"起服务半天没反应"是正常的。

## 5. 验收：**要听，不只是看**

这是 H3 跟 LTX 验收流程最大的差别——**H3 原生出 32kHz 立体声**，
台词是它自己读出来的。所以除了常规的抽帧看画面，还要：

- **听台词**：有没有漏字、吞字、读错；语气跟 `delivery_en` 写的对不对得上
- **看口型**：嘴型跟台词同步吗（H3 号称口型是对的，**没实测过**）
- **听音色跨镜一致性**：同一个角色在不同镜里是不是同一个声音
  （LTX 那边是 ledger A5「跨镜音色不保证一致」，H3 会不会更好未知）
- **旁白镜要确认嘴是闭着的**——提示词里写了闭嘴声明，成片有没有照做

画面侧的检查项跟 LTX 通用，见
`short-drama-video-gen/references/video_review_checklist.md`。

**重点关注两条 LTX 的老毛病 H3 有没有**（这是换模型最大的潜在收益）：

- ledger **A9「人物自己转向镜头」**——LTX 上改提示词拦不住的硬故障，
  根因是首帧被 `--image ... 1.0` 焊死。H3 的 ref2va 图是"参考"不是焊死的帧，
  机制不同，**很可能绕开**。第一批出来务必专门看这一条。
- ledger **A8「推拉运镜冲过头」**——H3 的运镜是受控词表 + 幅度 + 速度，
  理论上比 LTX 的散文运镜更可控。

发现新故障就往
`short-drama-video-gen/references/model_capability_ledger.md` 里加条目，
标清楚是 H3 的还是 LTX 的——**两个模型的能力清单不要混在一起**。

## 6. 收尾：用完就关

复用 `short-drama-ltx-generate/scripts/gpu_teardown.py`：

```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/gpu_teardown.py \
  --config output/<故事名>/videos/ep0X/h3_remote_config.json
```

RunPod 上默认 `terminate` Pod——Network Volume 上的权重不受影响，
下次挂同一个卷建新 Pod 直接能用，比只 `stop` 省（停止的 Pod 磁盘仍在计费）。

`h3_submit.py --auto-stop` 已经把这一步包进 `finally`，**包括报错和被中断的
情况**。跑完还要接着补镜头就别加 `--auto-stop`，改成收尾时手动跑。

## 与其他 skill 的衔接

- 上游 `minimax-h3-export`：装配 + 校验，产出 `h3_jobs.json` /
  `h3_remote_config.json`
- 更上游 `short-drama-video-gen`：维护模型无关的 `shot_cards.json` 和
  `build_h3_prompt.py`
- 平行的 `short-drama-ltx-generate`：LTX-2.5 通道。**GPU 运维脚本
  （`runpod_ops.py` / `gpu_teardown.py` / `idle_shutdown_watchdog.py`）
  和 `references/runpod_gpu_ops.md` 是两条通道共用的**，住在那边，
  本 skill 直接引用不复制。
- `loop-video-generation`：双 agent 循环，接管"提交+验收+重试"，
  三种结论（pass / retry_l1 / escalate_l2）对两个模型都适用。
