# 租显卡跑 LTX-2.5：RunPod 渠道（存储与算力分离，专门解决"每次都要重下模型"）

这是 vast.ai / AutoDL 之外的第三条 GPU 租赁渠道。跟前两条最大的区别：RunPod
的 **Network Volume（网络卷）跟 Pod（算力实例）是两个独立计费、独立生命周期
的资源**。Network Volume 建一次，之后不管起哪种 GPU 型号、Pod 被删了重建一个
新的，只要创建时指定同一个 `--network-volume-id`，挂载路径下（默认
`/workspace`）已经下载好的模型权重就还在，不需要重新下载——这是三条渠道里
唯一从架构上就不依赖"记得别 release/别销毁实例"这种操作习惯的方案。

**2026-09-02 用真实账号实测过一次完整流程**（建 Volume → 建 Pod → SSH/SCP →
terminate Pod → 用同一个 Volume 重建 Pod → 确认数据还在 → 清理），下面内容
已经不是纯理论，标 ⚠️ 的地方是**这一次实测顺带确认，但还需要更多次验证**或
**这一次没碰到、留给下次的点**，跟"完全没测过"的可信度不一样。

## 什么时候选 RunPod

- 需要**反复多次**跑生成任务（不只是这一集，后面还有好几集要跑），且不想
  每次都记得"关机不要释放"或者维护 vast.ai 的 Docker 镜像仓库——RunPod 的
  Network Volume 从设计上就不会因为一次操作失误（比如误 terminate 了 Pod）
  导致模型被删，只要没单独调用 volume 的删除操作，存储就在（**已实测确认**，
  见第 6 条）。
- 需要频繁更换 GPU 型号测试（比如先用小卡测参数、再换大卡跑正式档）——
  Network Volume 跟具体 Pod/GPU 型号解耦，换卡不影响已下载的模型。
- 不适合：只打算跑一次性任务、用完就彻底不用了——这种情况下 vast.ai 现租
  现走反而更省心，不需要额外维护一个 Network Volume。

## 0. 选卡门槛（跟 vast.ai/AutoDL 一致）

LTX-2.5 权重合计约 66GiB：

- 显存 ≥ 80GB（H100 80GB / A100 80GB 等）：完整精度直接跑。
- 显存 32-48GB：需要 `--quantization fp8-cast --offload cpu/disk`，同样不要
  轻信"应该够"，创建后用 `snapshot` 子命令核实真实型号/显存。
- Network Volume 大小：建议至少 100-120GB（66GB 模型 + 系统依赖 + 余量），
  RunPod 单个 Network Volume 上限 4000GB，远够用。实测 120GB 建volume 秒建好，
  没有额外等待时间。

## 1. 账号前置条件

- 控制台 → Settings → API Keys 生成一个 API Key，填进
  `runpod_config.json` 的 `api_key` 字段（这个文件要建在
  `.claude/skills/short-drama-ltx-generate/runpod_config.json`，已加入
  `.gitignore`，不会被提交）：
  ```json
  {"api_key": "rpa_xxxxxxxxxxxxxxxx"}
  ```
- 需要用户提供一段 SSH **公钥**内容（不是账号密码），传给
  `runpod_ops.py create --public-key`。**已实测确认**：官方镜像
  `runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04` 的启动脚本会
  读取 `PUBLIC_KEY` 环境变量自动配好 SSH，Pod 一进 `RUNNING` 状态、拿到公网
  IP 就能直接 `ssh root@<ip> -p <port>` 连上，不需要额外操作。⚠️ 其他基础
  镜像（比如直接用 `pytorch/pytorch` 官方镜像而不是 `runpod/pytorch`）有没有
  同样的启动脚本没测过，换镜像前先确认，没有的话得自己在 `dockerArgs`/`env`
  里想办法装好 sshd。

## 2. 查数据中心 / GPU 型号和价格

```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/runpod_ops.py datacenters
python3 .claude/skills/short-drama-ltx-generate/scripts/runpod_ops.py gputypes --min-memory-gb 80
```

`gputypes` 走 GraphQL（REST v1 没有公开的型号/价格列表端点），输出按价格从低
到高排序，`lowestPrice.stockStatus` 是 `Low`/`Medium`/`High`（也可能为
`null`，代表这个型号当前完全没货）。**⚠️ 实测确认一个重要坑**：`gputypes`
返回的 `stockStatus` 是全局聚合值，不代表某个具体数据中心有货——本仓库实测
`NVIDIA A100 80GB PCIe`（`stockStatus: "Low"`）在 `US-KS-2` 直接创建报
`"There are no instances currently available"`（HTTP 500），换成
`NVIDIA A100-SXM4-80GB`（`stockStatus: "High"`）同一数据中心立刻创建成功
（$1.59/hr）。**选卡策略：优先选 `stockStatus: "High"` 的型号，`Low`/`Medium`
大概率在具体数据中心创建时失败，失败了换下一个型号重试，不要死磕同一个**。

拿到准确的 `id` 字符串（比如 `"NVIDIA A100-SXM4-80GB"`）和数据中心 `id`
（比如 `"US-KS-2"`）用于下一步——不要凭猜测/记忆拼这两个字符串，必须从这两条
命令的真实输出里复制。

## 3. 建 Network Volume（只需要建一次，之后长期复用）

```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/runpod_ops.py \
  volume_create --name ltx2-weights --size-gb 120 --datacenter-id US-KS-2
```

返回的 `id`（比如 `vr1dk0uvnx`）记下来，写进 `ltx_remote_config.json`
（或者单独记一份笔记），**下次直接复用，不要重新建**——先跑
`volume_list` 确认有没有已经建过的可以直接用，这是避免"每次重新下载"这个
初衷能不能落地的关键一步，建了新 Volume 却没复用等于白搭。

## 4. 建 Pod（挂载 Network Volume）

```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/runpod_ops.py \
  create --gpu-type-id "NVIDIA A100-SXM4-80GB" \
  --network-volume-id vr1dk0uvnx \
  --image runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04 \
  --name ltx-gpu --cloud-type SECURE \
  --public-key "$(cat ~/.ssh/id_ed25519.pub)"
```

- `--cloud-type SECURE`：**已实测**默认自带公网 IP，能直接 `ssh`/`scp`，
  推荐默认用这个。`COMMUNITY`（价格通常更低）本脚本已经自动带上
  `supportPublicIp: true`，但 ⚠️ 没有实测验证 Community Cloud 开了这个选项
  后是不是每台宿主机都真的能分到公网 IP，第一次用 Community Cloud 建议先
  `snapshot` 确认 `public_ip` 非空，为空的话只能走 RunPod 的 SSH 代理
  （`ssh <pod-id>-<hash>@ssh.runpod.io`），而**代理模式官方文档明确说明不
  支持 scp/sftp**，`ltx_ssh_submit.py` 依赖 scp 上传/下载文件，代理模式跑
  不通，遇到这种情况只能换回 SECURE。
- 报 `"There are no instances currently available"`（HTTP 500）就是这个
  数据中心这个型号暂时没货，换个 `stockStatus` 更高的型号重试（见第 2 条），
  不是账号或参数错了。
- Network Volume 所在的数据中心和 Pod 创建时选的 GPU 型号必须在同一个数据
  中心都有效——本仓库目前只实测过"先建 Volume 再按同一个 `dataCenterId`
  挑 GPU"这一种顺序，没测过"Volume 建好后发现这个数据中心所有大显存型号都
  没货"要怎么处理（大概率是换数据中心重建 Volume，因为 Volume 建好后
  ⚠️ 没找到官方支持"迁移到别的数据中心"的操作）。

## 5. 查连接信息 / 状态

```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/runpod_ops.py \
  snapshot --pod-id <pod_id>
```

**已实测确认的时序**：Pod 创建返回时 `desiredStatus` 就是 `RUNNING`，但
`publicIp`/`portMappings` 要再等 30-40 秒左右才会填上（本仓库实测轮询 3-4
次、每次间隔 10 秒），前几次查询会看到 `public_ip`/`ssh_port` 是空/null，
**这不代表出错，继续轮询就行**，不要查一次就下结论。`ssh_host`（格式
`root@<公网IP>`）、`ssh_port` 输出格式直接能填进 `ltx_remote_config.json`
的 `ssh_host`/`ssh_port` 字段（`ltx_ssh_submit.py` 平台无关，只认这两个
字段+`ssh_key`）。

模型权重要下载到 `/workspace`（Network Volume 挂载点），**不要下到别的
路径**——实测这个挂载点是网络文件系统（`df -h` 显示类似
`mfs#us-ks-2.runpod.net:9421` 这种远程挂载源，容量显示的是共享存储池的
总量，不是你申请的那个 Volume 的具体大小，属于正常现象，不代表你的 Volume
真的有那么大配额）。

## 6. 成本管理：`stop` vs `terminate` vs `volume_delete`

**先说结论（懒得看细节就看这一条）**：这个渠道上"用完就关"的正确动作是
**`terminate` Pod、保留 Network Volume**，一条命令就是：
```bash
python3 .claude/skills/short-drama-ltx-generate/scripts/gpu_teardown.py \
  --config output/<故事名>/videos/ep0X/ltx_remote_config.json
```
（config 里有 `platform: "runpod"` + `instance_id` + `network_volume_id`
时，`--mode auto` 自己就会选 terminate，并且调完接口会轮询到 `404 pod not
found` 才敢说"已停止"。）为什么不是 `stop`：`stop` 只停 GPU，Pod 的磁盘
按 RunPod 官方计费口径**仍然在收费**（本仓库没有逐条核对账单数字，但"停止的
Pod 仍收存储费"是官方计费说明写明的），而容器盘反正也不跨 `stop`/`start`
持久（下面实测踩坑那条），留着它既花钱又没保住什么东西。真正值钱的是
Network Volume 上那 67GB 权重，而它**实测确认不受 `terminate` 影响**。

三个操作影响范围完全不同，**不要混淆**：

- `stop`：只停止 Pod 计费。**⚠️ 已实测确认：容器盘（`--container-disk-gb`
  那部分，非 Network Volume 部分）在 `stop`→`start` 之间不持久**——本仓库
  实测踩坑：`uv`（用官方安装脚本装到默认位置 `~/.local/bin`）在 `stop`
  之后 `start` 回来就找不到了（`bash: uv: command not found`），需要重新
  `curl -LsSf https://astral.sh/uv/install.sh | sh` 装一遍（几秒钟，不算
  大成本，但每次重启后要记得做这一步，不要假设环境还在）。**只要 LTX-2
  仓库本体和 `.venv` 是 clone/建在 `/workspace`（Network Volume）里，`uv
  sync` 装的依赖包本身不受影响**，受影响的只是 `uv` 这个启动器程序自己
  装在了容器盘上；更省事的做法是用 `UV_INSTALL_DIR=/workspace/bin sh -c
  "$(curl -LsSf https://astral.sh/uv/install.sh)"` 把 `uv` 本身也装到
  Network Volume 上，这样重启后就不用重装了（本仓库第一次踩坑时还没试过
  这个办法，下次可以直接用）。
- `terminate`：删除 Pod 本体。**已实测确认核心结论：Network Volume 完全不
  受 `terminate` 影响**——本仓库实测流程：在 `/workspace` 写一个标记文件 →
  `terminate` 删掉 Pod（`status` 查询立刻返回 `404 pod not found`，确认
  Pod 真的没了）→ 用同一个 `--network-volume-id` 建一个全新 Pod（不同
  Pod ID）→ SSH 进去读那个标记文件，**内容完好无损**。这是 RunPod 相比
  vast.ai/AutoDL 的核心优势：不需要"记得只 stop 不要 release"，`terminate`
  也是安全的，不会丢模型。
- `volume_delete`：删除 Network Volume 本体，**不可逆**，只有确认整个项目
  都不会再用 LTX-2.5 才调用，等价于 vast.ai/AutoDL 里的 `release`。
- 实例一确认 `RUNNING`，同样应该接上闲置看门狗：
  ```bash
  nohup python3 .claude/skills/short-drama-ltx-generate/scripts/idle_shutdown_watchdog.py \
    --instance-id <pod_id> --ssh-host <ssh_host> --ssh-port <ssh_port> \
    --platform runpod --runpod-config .claude/skills/short-drama-ltx-generate/runpod_config.json \
    --idle-seconds 120 --check-interval 15 \
    > /tmp/ltx_watchdog_<pod_id>.log 2>&1 &
  ```
  闲置超时后的停机动作委托给 `gpu_teardown.py`，`--stop-mode` 默认是
  `stop`（最保守），**权重在 Network Volume 上时建议显式加
  `--stop-mode terminate`**，理由见本节开头。挂载的 Network Volume 在两种
  模式下都不受影响。**已实测确认看门狗在 RunPod 上能正常工作**（`--platform runpod`，
  批量生成 15 镜期间持续检测到 `uv run` 活动、正确没有误停）；但也实测
  踩到一个使用节奏上的坑：一整批生成任务跑完之后，如果接下来在本地做抽帧
  核对（`extract_frames.py`+`Read` 工具）这类**不涉及任何远程 SSH 命令**
  的验收工作，这段时间对看门狗来说就是纯闲置，持续超过 `--idle-seconds`
  一样会被停掉——这不是 bug，是看门狗按设计正确判断了"远程真的没在干活"，
  但会打断"验收完还有一两个镜头要补"这类场景。**建议**：如果批量任务跑完
  后还预期要看一会儿抽帧结果再决定要不要补跑镜头，要么把 `--idle-seconds`
  设得更大（比如 3600），要么干脆在做纯本地验收工作期间先不启动/先不担心
  看门狗，等真正确认这台 Pod 不再需要时手动跑 `gpu_teardown.py`，不要指望
  看门狗会"等你看完图"。**更省事的做法**：如果这一批跑完就确定不用了，
  提交时直接 `ltx_ssh_submit.py --auto-stop`，跑完（或中途报错/被中断）
  自动关机——验收阶段（抽帧、看图）本来就不需要显卡在线。

## 7. 已知不确定点汇总（比第一版少了很多，但还没清零）

- Community Cloud + `supportPublicIp` 是否稳定分到公网 IP。
- 非官方镜像（不是 `runpod/pytorch:*`）是否需要自己处理 `PUBLIC_KEY` 注入/
  起 sshd。
- 容器盘（非 Network Volume 部分）在 `stop`/`start` 之间是否真的持久化
  （不影响核心流程，因为模型权重本来就该放 Network Volume）。
- Network Volume 建好后，如果所在数据中心后续所有大显存型号都没货，除了
  换数据中心重建 Volume（意味着要重新下载模型）还有没有别的办法（比如
  Volume 迁移）。
- 停止的 Pod 到底按什么价收磁盘费（官方口径明确"收"，但本仓库没有拿账单
  逐条核对过金额）——这也是为什么 `gpu_teardown.py` 在 RunPod 上默认直接
  `terminate` 而不是纠结这个数字。
- `gpu_teardown.py` 的 terminate 分支已经用真实账号验证过底层动作
  （第 6 条那次 `terminate` → 重建 → 数据完好的实测就是走 REST DELETE
  `/pods/<id>`，跟脚本调的是同一个接口），但"脚本自己走一遍 auto→terminate
  →轮询到 404"这条完整路径还没在真实运行中的 Pod 上跑过；`stop` 分支和
  轮询确认逻辑已经在 EXITED 状态的 Pod 上实测通过。

## ⚠️ 2026-09-03 两个真实事故（第一次拿本仓库正式跑生成时踩的）

### 事故 1：`ssh_host` 必须写成 `root@IP`，不能靠 `ssh_user` 字段

`ltx_ssh_submit.py` **没有 `ssh_user` 这个字段**，它把 config 里的 `ssh_host`
原样当 SSH 目标用。按常规写成 `{"ssh_user":"root","ssh_host":"216.81.245.7"}`
的话，脚本会用**本地用户名**去连（`codespace@216.81.245.7`），所有 job 报
`Permission denied (publickey,password)`、退出码 255。

RunPod 官方镜像 `runpod/pytorch:*` 的账号是 `root`，所以正确写法是：

```json
{ "ssh_host": "root@216.81.245.7", "ssh_port": 36189 }
```

### 事故 2：看门狗把正在生成的 Pod 销毁了（已修）

用 `ltx_batch.py`（一次加载权重跑多个单元）跑 16 个生成单元时，看门狗在
第 12 分钟判定"闲置 1820 秒"，调用 `gpu_teardown.py --mode terminate`
把 Pod 销毁了，批量任务从中间被砍断。

三条检测全部漏判：

| 检测项 | 为什么没救回来 |
|---|---|
| `ps aux \| grep ltx_pipelines` | 批量脚本的进程名是 **`ltx_batch.py`**，不含 `ltx_pipelines`，不匹配 |
| GPU 利用率 > 0 | **瞬时采样**。LTX 生成期间大量时间在加载权重/VAE 解码/写盘，`nvidia-smi` 读到 0% 很常见（手动查证过：跑着的时候读到 `0 %, 0 MiB`） |
| loadavg > 0.5 | GPU 推理时 CPU 负载压不过这个阈值 |

**已修**：`ACTIVE_PROC_PATTERN` 加了 `ltx_batch`。

**但这条修复不解决根本问题**——看门狗的定位是"兜住人忘了关"，它的活动检测
是**关键字白名单**，任何新跑法都要记得往里加。所以：

> **正式跑批量生成时，不要指望看门狗认得出来。** 要么在提交前把
> `--idle-seconds` 调到远大于预计生成时长（16 个单元 × 89 帧 ≈ 20-35 分钟，
> 就该给 `--idle-seconds 5400`），要么这段时间干脆不挂看门狗、改用
> `ltx_ssh_submit.py --auto-stop` 让提交脚本自己跑完关机。

**数据没丢**：mp4 写在 `/workspace/ltx_jobs`，那是 Network Volume 的挂载点，
`terminate` 不影响卷上的数据——重新建 Pod 挂同一个 `network_volume_id`
就能把已完成的片段取回来。这次事故实际损失只有那 34 分钟的机时（≈$0.79）
和被砍断的那部分生成。
